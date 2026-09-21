// Loom's control entry point is a native Go executable. External workers and
// the remote Sandbox are configured components, not language runtime shims.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"

	"github.com/spf13/cobra"
	"loom/runtime/authority"
	"loom/runtime/config"
	"loom/runtime/controller"
	"loom/runtime/rpc"
	"loom/runtime/work"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	cmd := command()
	if err := cmd.ExecuteContext(ctx); err != nil {
		fmt.Fprintln(os.Stderr, "loom:", err)
		os.Exit(1)
	}
}
func command() *cobra.Command {
	home, _ := os.UserHomeDir()
	var authorityPath, configPath string
	root := &cobra.Command{Use: "loom", Short: "Durable control Runtime", SilenceErrors: true, SilenceUsage: true}
	root.AddCommand(facilityCommand())
	root.PersistentFlags().StringVar(&authorityPath, "authority", filepath.Join(home, ".local/state/loom/authority.sqlite"), "host authority database")
	root.PersistentFlags().StringVar(&configPath, "config", filepath.Join(home, ".config/loom/config.toml"), "deployment configuration")
	add := func(name, usage string, n int, fn func(*cobra.Command, []string, *authority.Authority) (any, error)) *cobra.Command {
		cmd := &cobra.Command{Use: usage, Args: cobra.ExactArgs(n), RunE: func(cmd *cobra.Command, args []string) error {
			a, err := authority.Open(authorityPath)
			if err != nil {
				return errors.New("cannot open host authority database")
			}
			result, err := fn(cmd, args, a)
			if err != nil {
				return publicError(err)
			}
			if human, ok := result.(humanOutput); ok {
				_, err = fmt.Fprintln(cmd.OutOrStdout(), string(human))
				return err
			}
			out := json.NewEncoder(cmd.OutOrStdout())
			out.SetIndent("", "  ")
			out.SetEscapeHTML(false)
			return out.Encode(result)
		}}
		root.AddCommand(cmd)
		return cmd
	}
	open := func(a *authority.Authority, path string) (*work.Work, error) {
		w, err := work.Open(path)
		if err != nil {
			return nil, err
		}
		if err = a.Authorize(w); err != nil {
			return nil, err
		}
		return w, nil
	}
	usageCommands(root, add, &configPath, open)
	eventCommands(root, &authorityPath, &configPath)
	var harness, definition string
	create := add("create", "create PATH --harness DIR --definition FILE", 1, func(cmd *cobra.Command, args []string, a *authority.Authority) (any, error) {
		w, err := work.Create(args[0], harness, definition)
		if err != nil {
			return nil, err
		}
		if err = a.Register(w); err != nil {
			return nil, err
		}
		return map[string]any{"work_id": w.ID, "path": w.Path}, nil
	})
	create.Flags().StringVar(&harness, "harness", "", "fixed external Harness directory")
	_ = create.MarkFlagRequired("harness")
	create.Flags().StringVar(&definition, "definition", "", "portable Work requirements (TOML)")
	_ = create.MarkFlagRequired("definition")
	add("select-harness", "select-harness PATH", 1, func(_ *cobra.Command, args []string, a *authority.Authority) (any, error) {
		w, err := open(a, args[0])
		if err != nil {
			return nil, err
		}
		ref, err := w.SelectHarness()
		if err != nil {
			return nil, err
		}
		return map[string]any{"selected_harness_ref": ref, "activation": "next Round"}, nil
	})
	add("register", "register PATH", 1, func(_ *cobra.Command, args []string, a *authority.Authority) (any, error) {
		w, err := work.Initialize(args[0])
		if err != nil {
			return nil, err
		}
		if err = a.Register(w); err != nil {
			return nil, err
		}
		return map[string]any{"registered": w.ID}, nil
	})
	add("grant-resource", "grant-resource PATH ALIAS DIRECTORY", 3, func(_ *cobra.Command, args []string, a *authority.Authority) (any, error) {
		w, err := open(a, args[0])
		if err != nil {
			return nil, err
		}
		if err = a.GrantResource(w, args[1], args[2]); err != nil {
			return nil, err
		}
		grant, err := a.Resource(w, args[1])
		return grant, err
	})
	var restoreTarget string
	restoreResource := add("restore-resource", "restore-resource PATH ALIAS DESTINATION", 3, func(_ *cobra.Command, args []string, a *authority.Authority) (any, error) {
		w, err := open(a, args[0])
		if err != nil {
			return nil, err
		}
		// Materialize retained Work bytes into a new directory. Registration
		// authorizes reading that history; a grant to the original live source is
		// neither needed nor recreated when moving the Work to another host.
		destination, err := filepath.Abs(args[2])
		if err != nil {
			return nil, err
		}
		if err = w.RestoreResource(args[1], restoreTarget, destination); err != nil {
			return nil, err
		}
		return map[string]any{"restored": destination, "target": restoreTarget, "authorized": false}, nil
	})
	restoreResource.Flags().StringVar(&restoreTarget, "target", "", "copy version to restore; omitted selects initial resource version")
	add("grant", "grant PATH DIRECTORY", 2, func(_ *cobra.Command, args []string, a *authority.Authority) (any, error) {
		w, err := open(a, args[0])
		if err != nil {
			return nil, err
		}
		if err = a.Grant(w, args[1]); err != nil {
			return nil, err
		}
		path, _ := filepath.Abs(args[1])
		return map[string]any{"granted": path}, nil
	})
	for _, name := range []string{"admit", "relay"} {
		var payloadPath, requestID string
		n, usage := 2, "admit PATH KIND --payload FILE --request-id ID"
		if name == "relay" {
			n, usage = 3, "relay PATH RECEIVER KIND --payload FILE --request-id ID"
		}
		cmd := add(name, usage, n, func(cmd *cobra.Command, args []string, a *authority.Authority) (any, error) {
			w, err := open(a, args[0])
			if err != nil {
				return nil, err
			}
			data, err := os.ReadFile(payloadPath)
			if err != nil {
				return nil, errors.New("cannot read payload file")
			}
			var payload map[string]any
			if err = rpc.Decode(data, &payload); err != nil || payload == nil {
				return nil, errors.New("payload must be a JSON object")
			}
			r := &controller.Runtime{Authority: a}
			if name == "admit" {
				return r.Admit(cmd.Context(), w, requestID, args[1], payload)
			}
			receiver, err := work.Open(args[1])
			if err != nil {
				return nil, err
			}
			return r.Relay(cmd.Context(), w, receiver, requestID, args[2], payload)
		})
		cmd.Flags().StringVar(&payloadPath, "payload", "", "JSON object file")
		cmd.Flags().StringVar(&requestID, "request-id", "", "source request identity")
		_ = cmd.MarkFlagRequired("payload")
		_ = cmd.MarkFlagRequired("request-id")
	}
	for _, name := range []string{"status", "events", "run", "resume", "recover", "query-remote", "cancel-effect", "inspect-allocation", "release-allocation"} {
		n, usage := 1, name+" PATH"
		if name == "query-remote" || name == "cancel-effect" || name == "inspect-allocation" || name == "release-allocation" {
			n, usage = 3, name+" PATH ROUND_ID EFFECT_ID"
			if name == "inspect-allocation" || name == "release-allocation" {
				usage = name + " PATH ROUND_ID ALLOCATION_ID"
			}
		}
		operation := add(name, usage, n, func(cmd *cobra.Command, args []string, a *authority.Authority) (any, error) {
			if len(args) == 0 {
				args = []string{"."}
			}
			w, err := open(a, args[0])
			if err != nil {
				return nil, err
			}
			r := &controller.Runtime{Authority: a}
			if name == "status" {
				return r.Query(w)
			}
			if name == "events" {
				return w.Events.Events(0)
			}
			host, err := config.Load(configPath)
			if err != nil {
				return nil, err
			}
			if name == "recover" {
				r.ResolveSandbox = sandboxResolver(host).ResolveSavedSandbox
				r.Execution = host.Execution
				return r.Recover(cmd.Context(), w)
			}
			if name == "query-remote" || name == "cancel-effect" || name == "inspect-allocation" || name == "release-allocation" {
				r.ResolveSandbox = sandboxResolver(host).ResolveSavedSandbox
				if name == "inspect-allocation" {
					return r.Allocation(cmd.Context(), w, args[1], args[2], "inspect")
				}
				if name == "release-allocation" {
					return r.Allocation(cmd.Context(), w, args[1], args[2], "release")
				}
				if name == "cancel-effect" {
					return r.CancelRemote(cmd.Context(), w, args[1], args[2])
				}
				return r.QueryRemote(cmd.Context(), w, args[1], args[2])
			}
			r.Execution = host.Execution
			r.Configure = hostBinding(host)
			return r.Run(cmd.Context(), w, name == "resume")
		})
		if name != "query-remote" && name != "cancel-effect" && name != "inspect-allocation" && name != "release-allocation" {
			operation.Use = name + " [PATH]"
			operation.Args = cobra.MaximumNArgs(1)
		}
	}

	add("history", "history PATH", 1, func(_ *cobra.Command, args []string, a *authority.Authority) (any, error) {
		w, e := open(a, args[0])
		if e != nil {
			return nil, e
		}
		return w.Control.Checkpoints()
	})
	add("inspect", "inspect PATH CHECKPOINT DIRECTORY", 3, func(_ *cobra.Command, args []string, a *authority.Authority) (any, error) {
		w, e := open(a, args[0])
		if e != nil {
			return nil, e
		}
		if e = w.Inspect(args[1], args[2]); e != nil {
			return nil, e
		}
		return map[string]any{"directory": args[2], "executable": false}, nil
	})
	add("fork", "fork PATH CHECKPOINT DIRECTORY", 3, func(_ *cobra.Command, args []string, a *authority.Authority) (any, error) {
		w, e := open(a, args[0])
		if e != nil {
			return nil, e
		}
		child, e := w.Fork(args[1], args[2])
		if e != nil {
			return nil, e
		}
		if e = a.Register(child); e != nil {
			return nil, e
		}
		return map[string]any{"work_id": child.ID, "path": child.Path, "resource_grants_inherited": false}, nil
	})
	add("export", "export PATH ARCHIVE", 2, func(_ *cobra.Command, args []string, a *authority.Authority) (any, error) {
		w, err := open(a, args[0])
		if err != nil {
			return nil, err
		}
		if err = a.Export(w, args[1]); err != nil {
			return nil, err
		}
		path, _ := filepath.Abs(args[1])
		return map[string]any{"exported": path}, nil
	})
	add("import", "import ARCHIVE PATH", 2, func(_ *cobra.Command, args []string, a *authority.Authority) (any, error) {
		w, err := work.Import(args[0], args[1])
		if err != nil {
			return nil, err
		}
		return map[string]any{"work_id": w.ID, "path": w.Path, "authorized": false}, nil
	})

	add("allow-read", "allow-read SOURCE_WORK READER_WORK ALIAS", 3, func(_ *cobra.Command, args []string, a *authority.Authority) (any, error) {
		source, e := open(a, args[0])
		if e != nil {
			return nil, e
		}
		reader, e := open(a, args[1])
		if e != nil {
			return nil, e
		}
		if e = a.GrantRead(source, reader, args[2]); e != nil {
			return nil, e
		}
		return map[string]any{"source_work_id": source.ID, "reader_work_id": reader.ID, "alias": args[2], "access": "read", "scope": "surface"}, nil
	})
	add("revoke-read", "revoke-read READER_WORK ALIAS", 2, func(_ *cobra.Command, args []string, a *authority.Authority) (any, error) {
		reader, e := open(a, args[0])
		if e != nil {
			return nil, e
		}
		if e = a.RevokeRead(reader, args[1]); e != nil {
			return nil, e
		}
		return map[string]any{"revoked": args[1]}, nil
	})
	add("allow-relay", "allow-relay PATH RECEIVER", 2, func(_ *cobra.Command, args []string, a *authority.Authority) (any, error) {
		sender, err := open(a, args[0])
		if err != nil {
			return nil, err
		}
		receiver, err := work.Open(args[1])
		if err != nil {
			return nil, err
		}
		if err = a.AllowRelay(sender, receiver); err != nil {
			return nil, err
		}
		return map[string]any{"relay_granted": true}, nil
	})
	return root
}

// Public component errors never carry transport payloads. Database/file/parser
// errors are bounded to avoid exposing arbitrary imported contents.
func publicError(err error) error {
	if errors.Is(err, rpc.ErrTransport) {
		return rpc.ErrTransport
	}
	return err
}

func onlyResource(w *work.Work) (string, error) {
	if len(w.Definition.Userspaces) != 1 {
		return "", errors.New("command requires exactly one resource; select an alias explicitly")
	}
	for alias := range w.Definition.Userspaces {
		return alias, nil
	}
	return "", errors.New("no resource")
}
