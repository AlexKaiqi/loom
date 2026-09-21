package onboarding

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"loom/runtime/contracts"
)

func TestCustomProviderOptionsDoNotInheritContainerPreset(t *testing.T) {
	root := t.TempDir()
	for _, name := range []string{"services/model", "bin", "deploy"} {
		if err := os.MkdirAll(filepath.Join(root, name), 0700); err != nil {
			t.Fatal(err)
		}
	}
	for _, name := range []string{"config.example.toml", "work.example.toml"} {
		raw, err := os.ReadFile(filepath.Join("../../deploy", name))
		if err != nil {
			t.Fatal(err)
		}
		if err = os.WriteFile(filepath.Join(root, "deploy", name), raw, 0600); err != nil {
			t.Fatal(err)
		}
	}
	for name, raw := range map[string]string{"services/model/worker.mjs": "", "bin/loom-model": "#!/bin/sh\nexit 0\n", "model.json": `{"id":"fixture","api":"openai-completions","provider":"fixture"}`, "options.json": `{"pool":"prepared"}`} {
		if err := os.WriteFile(filepath.Join(root, name), []byte(raw), 0700); err != nil {
			t.Fatal(err)
		}
	}
	t.Setenv("LOOM_INSTALL_ROOT", root)
	stop := errors.New("observed constructor; no remote effects")
	called := false
	s := Setup{ConfigPath: filepath.Join(root, "host.toml"), ModelFile: filepath.Join(root, "model.json"), ModelEndpoint: "https://model.invalid/v1",
		SandboxProvider: "fixture-process/v1", SandboxEndpoint: "unix:///run/fixture.sock", SandboxOptions: filepath.Join(root, "options.json"),
		ModelKeyEnv: "MODEL_KEY", SandboxKeyEnv: "SANDBOX_KEY", Input: strings.NewReader(""), Output: io.Discard,
		SandboxFactories: map[string]contracts.ProviderFactory{"fixture-process/v1": func(binding contracts.Binding, _ string) (contracts.TaskExecutor, error) {
			called = true
			var options map[string]any
			if err := json.Unmarshal([]byte(binding.OptionsJSON), &options); err != nil {
				t.Fatal(err)
			}
			if len(options) != 1 || options["pool"] != "prepared" || binding.Endpoint != "unix:///run/fixture.sock" {
				t.Fatal("vendor defaults or transport restriction leaked", binding)
			}
			return nil, stop
		}},
	}
	if err := s.Run(context.Background()); !errors.Is(err, stop) || !called {
		t.Fatal("constructor not reached", err)
	}
	if _, err := os.Stat(s.ConfigPath); !os.IsNotExist(err) {
		t.Fatal("rejected setup published configuration")
	}
}
