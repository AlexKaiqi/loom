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
	add("register", "register PATH", 1, func(_ *cobra.Command, args []string, a *authority.Authority) (any, error) {
		w, err := work.Open(args[0])
		if err != nil {
			return nil, err
		}
		if err = a.Register(w); err != nil {
			return nil, err
		}
		return map[string]any{"registered": w.ID}, nil
	})
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
	for _, name := range []string{"status", "events", "run", "resume", "query-remote"} {
		n, usage := 1, name+" PATH"
		if name == "query-remote" {
			n, usage = 3, name+" PATH ROUND_ID EFFECT_ID"
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
			if name == "query-remote" {
				r.ResolveSandbox = host.ResolveSavedSandbox
				return r.QueryRemote(cmd.Context(), w, args[1], args[2])
			}
			deployment, err := host.ResolveModel(w.Definition.Model)
			if err != nil {
				return nil, err
			}
			r.Model = deployment.Model
			r.APIKey = deployment.APIKey
			r.ModelCommand = deployment.Worker
			r.Sandbox, err = host.ResolveSandbox(w.Definition.Sandbox)
			if err != nil {
				return nil, err
			}
			return r.Run(cmd.Context(), w, name == "resume")
		})
		if name != "query-remote" {
			operation.Use = name + " [PATH]"
			operation.Args = cobra.MaximumNArgs(1)
		}
	}
	add("restore-userspace", "restore-userspace PATH DESTINATION", 2, func(_ *cobra.Command, args []string, a *authority.Authority) (any, error) {
		w, err := open(a, args[0])
		if err != nil {
			return nil, err
		}
		if err = w.RestoreUserspace(args[1]); err != nil {
			return nil, err
		}
		path, _ := filepath.Abs(args[1])
		return map[string]any{"restored": path, "granted": false}, nil
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
