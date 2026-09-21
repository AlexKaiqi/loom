package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/pelletier/go-toml/v2"
	"github.com/spf13/cobra"
	"loom/runtime/authority"
	"loom/runtime/config"
	"loom/runtime/controller"
	"loom/runtime/onboarding"
	"loom/runtime/store"
	"loom/runtime/work"
)

type humanOutput string
type addCommand func(string, string, int, func(*cobra.Command, []string, *authority.Authority) (any, error)) *cobra.Command

func usageCommands(root *cobra.Command, add addCommand, configPath *string, open func(*authority.Authority, string) (*work.Work, error)) {
	setup := onboarding.Setup{SandboxFactories: sandboxFactories()}
	setupCmd := &cobra.Command{Use: "setup", Short: "Configure model and remote Sandbox once", Args: cobra.NoArgs, RunE: func(cmd *cobra.Command, _ []string) error {
		setup.ConfigPath = *configPath
		setup.Input = cmd.InOrStdin()
		setup.Output = cmd.OutOrStdout()
		return setup.Run(cmd.Context())
	}}
	flags := setupCmd.Flags()
	flags.StringVar(&setup.Provider, "provider", "", "Pi provider name")
	flags.StringVar(&setup.Model, "model", "", "model ID in Pi catalog")
	flags.StringVar(&setup.ModelFile, "model-file", "", "custom portable native Pi model JSON")
	flags.StringVar(&setup.ModelEndpoint, "model-endpoint", "", "override model API base URL")
	flags.StringVar(&setup.SandboxProvider, "sandbox-provider", "", "versioned task provider (ssh-process/v1 or opensandbox/v1)")
	flags.StringVar(&setup.SandboxOptions, "sandbox-options", "", "provider options JSON file without credentials (omit to use installed preset)")
	flags.StringVar(&setup.SandboxEndpoint, "sandbox-endpoint", "", "remote Sandbox endpoint")
	flags.StringVar(&setup.ModelKeyEnv, "model-key-env", "", "existing model credential environment variable")
	flags.StringVar(&setup.SandboxKeyEnv, "sandbox-key-env", "", "existing Sandbox credential environment variable")
	flags.StringVar(&setup.ModelKeyFile, "model-key-file", "", "existing private model credential file")
	flags.StringVar(&setup.SandboxKeyFile, "sandbox-key-file", "", "existing private Sandbox credential file")
	root.AddCommand(setupCmd)
	var harness, definition, userspace string
	newCmd := add("new", "new PATH --userspace DIRECTORY", 1, func(cmd *cobra.Command, args []string, a *authority.Authority) (any, error) {
		useDefaults := definition == ""
		if harness == "" {
			assets, err := onboarding.Assets()
			if err != nil {
				return nil, err
			}
			harness = filepath.Join(assets, "harnesses/kernel")
		}
		if definition == "" {
			definition = onboarding.DefaultDefinition(*configPath)
		}
		def, err := work.ReadDefinition(definition)
		if err != nil {
			return nil, fmt.Errorf("Work defaults unavailable; run loom setup or pass --definition: %w", err)
		}
		if _, err = config.Load(*configPath); err != nil {
			return nil, err
		}
		if len(def.Userspaces) > 0 && userspace == "" {
			return nil, errors.New("choose task files explicitly with --userspace DIRECTORY")
		}
		if len(def.Userspaces) == 0 && userspace != "" {
			return nil, errors.New("selected definition does not declare Userspace")
		}
		if userspace != "" {
			if _, err = authority.StatIdentity(userspace); err != nil {
				return nil, fmt.Errorf("task directory is not available: %w", err)
			}
			workPath, err := filepath.Abs(args[0])
			if err != nil {
				return nil, err
			}
			taskPath, err := filepath.EvalSymlinks(userspace)
			if err != nil {
				return nil, err
			}
			taskPath, err = filepath.Abs(taskPath)
			if err != nil {
				return nil, err
			}
			if authority.Overlaps(workPath, taskPath) {
				return nil, errors.New("Work and task-files directories must not overlap")
			}
			if useDefaults {
				if len(def.Userspaces) != 1 {
					return nil, errors.New("default new requires exactly one task resource; use an explicit definition for multiple resources")
				}
				name, err := a.NameResource(taskPath)
				if err != nil {
					return nil, err
				}
				for alias, resource := range def.Userspaces {
					resource.Resource = name
					def.Userspaces[alias] = resource
				}
				raw, err := toml.Marshal(def)
				if err != nil {
					return nil, err
				}
				file, err := os.CreateTemp("", "loom-new-definition-")
				if err != nil {
					return nil, err
				}
				defer os.Remove(file.Name())
				if _, err = file.Write(raw); err != nil {
					file.Close()
					return nil, err
				}
				if err = file.Close(); err != nil {
					return nil, err
				}
				definition = file.Name()
			}
		}
		w, err := work.Create(args[0], harness, definition)
		if err != nil {
			return nil, err
		}
		assets, err := onboarding.Assets()
		if err != nil {
			return nil, err
		}
		template, err := os.ReadFile(filepath.Join(assets, "templates/default/surface/main.md"))
		if err != nil {
			return nil, err
		}
		if err = work.Save(filepath.Join(w.Surface, "main.md"), template); err != nil {
			return nil, err
		}
		if _, err = w.Snapshot("initial Work template"); err != nil {
			return nil, err
		}
		if err = a.Register(w); err != nil {
			return nil, fmt.Errorf("Work created at %s; registration failed: %w", w.Path, err)
		}
		if userspace != "" {
			if err = a.Grant(w, userspace); err != nil {
				return nil, fmt.Errorf("Work created at %s; task directory was not granted: %w", w.Path, err)
			}
		}
		return humanOutput(fmt.Sprintf("Created %s\nNext: cd %q && loom ask \"Your objective\"", w.Path, w.Path)), nil
	})
	newCmd.Short = "Create a Work using configured defaults and the bundled Harness"
	newCmd.Flags().StringVar(&harness, "harness", "", "external Harness directory (default: installed kernel)")
	newCmd.Flags().StringVar(&definition, "definition", "", "portable Work requirements (default: setup template)")
	newCmd.Flags().StringVar(&userspace, "userspace", "", "existing external task-files directory")
	var requestID string
	ask := add("ask", "ask [PATH] TEXT", 1, func(cmd *cobra.Command, args []string, a *authority.Authority) (any, error) {
		path, text := ".", args[0]
		if len(args) == 2 {
			path, text = args[0], args[1]
		}
		if strings.TrimSpace(text) == "" {
			return nil, errors.New("message cannot be empty")
		}
		w, err := open(a, path)
		if err != nil {
			return nil, err
		}
		if requestID == "" {
			requestID, err = store.ID()
			if err != nil {
				return nil, err
			}
		}
		r := &controller.Runtime{Authority: a}
		// Stable event kind keeps request-id retries independent of prior facts.
		admitted, err := r.Admit(cmd.Context(), w, requestID, "work.message", map[string]any{"text": text})
		if err != nil {
			return nil, err
		}
		fmt.Fprintf(cmd.ErrOrStderr(), "Accepted request %s (event %d). Retry with --request-id %s.\n", requestID, admitted.Seq, requestID)
		pending, err := w.Events.Pending()
		if err != nil {
			return nil, err
		}
		waiting := false
		for _, p := range pending {
			if p.Seq == admitted.Seq {
				waiting = true
			}
		}
		if !waiting {
			return humanOutput("This request was already handled; no model or tool was called again."), nil
		}
		rounds, err := w.Control.Rounds()
		if err != nil {
			return nil, err
		}
		for _, round := range rounds {
			if round.State != "handed_off" {
				if round.State == "blocked" || round.State == "recovering" {
					return humanOutput(fmt.Sprintf("Message queued. The current Round requires recovery. Run loom recover %q and inspect loom status %q; resume only when its state is ready.", w.Path, w.Path)), nil
				}
				return humanOutput("Message queued. Finish or explicitly resume the current Round, then run the pending work."), nil
			}
		}
		if err = bindRuntime(r, w, *configPath); err != nil {
			return nil, err
		}
		result, err := r.Run(cmd.Context(), w, false)
		if err != nil {
			return nil, err
		}
		answer, err := assistantText(w, result)
		if err != nil {
			return nil, err
		}
		if answer == "" {
			answer = "Round handed off. Inspect Surface and saved resource copies for the result."
		}
		return humanOutput(answer + "\n\nSurface: " + w.Surface), nil
	})
	ask.Args = cobra.RangeArgs(1, 2)
	ask.Short = "Submit a natural-language message and run pending work"
	ask.Flags().StringVar(&requestID, "request-id", "", "stable identity for retrying the same message")
}
func bindRuntime(r *controller.Runtime, w *work.Work, path string) error {
	host, err := config.Load(path)
	if err != nil {
		return err
	}
	r.Execution = host.Execution
	r.Configure = hostBinding(host)
	return nil
}

func hostBinding(host *config.Config) func(*controller.Runtime, *work.Work) error {
	return func(r *controller.Runtime, w *work.Work) error {
		deployment, err := host.DescribeModel(w.Definition.Model)
		if err != nil {
			return err
		}
		r.Model, r.APIKey, r.ModelCommand = deployment.Model, deployment.APIKey, deployment.Worker
		r.ActivateModel = func(active *controller.Runtime) error {
			resolved, err := host.ResolveModel(w.Definition.Model)
			if err != nil {
				return err
			}
			active.Model, active.APIKey, active.ModelCommand = resolved.Model, resolved.APIKey, resolved.Worker
			return nil
		}
		r.Targets, err = sandboxResolver(host).ResolveTargets(w.Definition.Targets)
		r.ResolveSandbox = sandboxResolver(host).ResolveSavedSandbox
		return err
	}
}

func assistantText(w *work.Work, result map[string]any) (string, error) {
	reference, ok := result["messages"].(map[string]any)
	if !ok {
		return "", errors.New("completed Round is missing its native result reference")
	}
	name, ok := reference["path"].(string)
	if !ok {
		return "", errors.New("invalid native result reference")
	}
	data, err := os.ReadFile(filepath.Join(w.Path, filepath.FromSlash(name)))
	if err != nil {
		return "", err
	}
	var messages []map[string]any
	if err = json.Unmarshal(data, &messages); err != nil {
		return "", err
	}
	answer := ""
	for _, m := range messages {
		if m["role"] == "assistant" {
			parts, _ := m["content"].([]any)
			texts := []string{}
			for _, p := range parts {
				part, _ := p.(map[string]any)
				if part["type"] == "text" {
					if text, ok := part["text"].(string); ok {
						texts = append(texts, text)
					}
				}
			}
			answer = strings.Join(texts, "\n")
		}
	}
	return answer, nil
}
