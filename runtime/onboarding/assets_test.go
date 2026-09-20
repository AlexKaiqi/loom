package onboarding

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"loom/runtime/config"
	"loom/runtime/work"
)

func TestModelWorkerSourceAndInstalledDeployment(t *testing.T) {
	root := t.TempDir()
	t.Setenv("LOOM_INSTALL_ROOT", "")
	worker, err := ModelWorker(root)
	if err != nil || !reflect.DeepEqual(worker, []string{"node", filepath.Join(root, "services/model/worker.mjs")}) {
		t.Fatalf("source deployment = %v, %v", worker, err)
	}
	t.Setenv("LOOM_INSTALL_ROOT", root)
	if _, err = ModelWorker(root); err == nil {
		t.Fatal("installed setup accepted a missing deployed component")
	}
	if err = os.MkdirAll(filepath.Join(root, "bin"), 0700); err != nil {
		t.Fatal(err)
	}
	launcher := filepath.Join(root, "bin/loom-model")
	if err = os.WriteFile(launcher, []byte("#!/bin/sh\nexit 0\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = ModelWorker(root); err == nil {
		t.Fatal("installed setup accepted a non-executable component")
	}
	if err = os.Chmod(launcher, 0700); err != nil {
		t.Fatal(err)
	}
	worker, err = ModelWorker(root)
	if err != nil || !reflect.DeepEqual(worker, []string{"loom-model"}) {
		t.Fatalf("installed deployment = %v, %v", worker, err)
	}
}

func TestExplicitOperatorWorkerIsPreserved(t *testing.T) {
	t.Setenv("LOOM_INSTALL_ROOT", t.TempDir())
	t.Setenv("LOOM_WORKER_TEST_KEY", "synthetic-test-key")
	argv := []string{"/operator/custom-node", "/operator/custom-worker.mjs", "--explicit"}
	host := config.Config{Models: map[string]config.ModelService{"primary": {
		Endpoint: "https://example.invalid/v1", APIKeyEnv: "LOOM_WORKER_TEST_KEY", Worker: argv,
	}}}
	deployment, err := host.ResolveModel(work.ModelDefinition{Service: "primary", Parameters: map[string]any{
		"id": "explicit", "api": "openai-completions", "provider": "configured",
	}})
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(deployment.Worker, argv) {
		t.Fatalf("operator worker replaced with installed default: %v", deployment.Worker)
	}
}
