package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	sandbox "loom/runtime/adapters/opensandbox"
	"loom/runtime/work"
)

func TestNamedBindingsDoNotSupplyWorkSemantics(t *testing.T) {
	t.Setenv("CONFIG_TEST_KEY", "host-secret")
	c := Config{Models: map[string]ModelService{"chosen": {Endpoint: "https://example.test/v1", APIKeyEnv: "CONFIG_TEST_KEY", Worker: []string{"node", "worker.mjs"}, HeadersEnv: map[string]string{"X-Key": "CONFIG_TEST_KEY"}}, "unused": {APIKeyEnv: "MISSING_UNUSED_KEY"}}}
	def := work.ModelDefinition{Service: "chosen", Parameters: map[string]any{"id": "work-model", "api": "openai-completions", "provider": "work-provider"}}
	got, err := c.ResolveModel(def)
	if err != nil {
		t.Fatal(err)
	}
	if got.Model["id"] != "work-model" || got.Model["baseUrl"] != "https://example.test/v1" || got.APIKey != "host-secret" {
		t.Fatal("incorrect resolution")
	}
	if def.Parameters["headers"] != nil || def.Parameters["baseUrl"] != nil {
		t.Fatal("host values contaminated Work")
	}
	def.Service = "missing"
	if _, err = c.ResolveModel(def); err == nil {
		t.Fatal("missing binding accepted")
	}
}

func TestReleaseFacilityBindingDoesNotRewriteServiceConfiguration(t *testing.T) {
	root := t.TempDir()
	services := filepath.Join(root, "host.toml")
	body := []byte("[models.primary]\nendpoint='https://example.test/v1'\nworker=['loom-model']\n")
	if err := os.WriteFile(services, body, 0600); err != nil {
		t.Fatal(err)
	}
	old := filepath.Join(root, "old.toml")
	next := filepath.Join(root, "new.toml")
	if err := os.WriteFile(old, []byte("launcher='/old/nsjail'\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(next, []byte("launcher='/new/nsjail'\n"), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("LOOM_EXECUTION_CONFIG", old)
	first, err := Load(services)
	if err != nil {
		t.Fatal(err)
	}
	t.Setenv("LOOM_EXECUTION_CONFIG", next)
	second, err := Load(services)
	if err != nil {
		t.Fatal(err)
	}
	if first.Execution.Binary != "/old/nsjail" || second.Execution.Binary != "/new/nsjail" {
		t.Fatal("deployment binding drifted")
	}
	got, err := os.ReadFile(services)
	if err != nil || string(got) != string(body) {
		t.Fatal("upgrade rewrote service configuration", err)
	}
	t.Setenv("LOOM_EXECUTION_CONFIG", filepath.Join(root, "missing"))
	if _, err = Load(services); err == nil {
		t.Fatal("missing deployment binding ignored")
	}
}
func TestQueryUsesSavedBindingWithoutModelCredentials(t *testing.T) {
	t.Setenv("CONFIG_TEST_KEY", "host-secret")
	c := Config{Sandboxes: map[string]SandboxService{"remote": {Endpoint: "http://127.0.0.1:1/", APIKeyEnv: "CONFIG_TEST_KEY"}}}
	binding := sandbox.Binding{ServiceID: "remote", Endpoint: "http://127.0.0.1:1", Image: "fixture@sha256:" + strings.Repeat("a", 64), Profile: "code", CPU: "2", Memory: "1Gi", LeaseSeconds: 120, RequestTimeoutSeconds: 5}
	got, err := c.ResolveSavedSandbox(binding)
	if err != nil {
		t.Fatal(err)
	}
	if got.Binding() != binding {
		t.Fatal("saved execution requirements changed")
	}
	binding.Endpoint = "http://127.0.0.1:2"
	if _, err = c.ResolveSavedSandbox(binding); err == nil {
		t.Fatal("saved destination drift accepted")
	}
	binding.Endpoint = "http://127.0.0.1:1"
	binding.LeaseSeconds = 0
	if _, err = c.ResolveSavedSandbox(binding); err == nil {
		t.Fatal("missing limits silently defaulted")
	}
}
func TestOldDefaultsAndSecretBearingEndpointsReject(t *testing.T) {
	path := filepath.Join(t.TempDir(), "host.toml")
	if err := os.WriteFile(path, []byte("schema_version=2\n[harness]\npath='harness'\nargv=['unused']\n[surface]\npath='surface'\n[model]\nworker=['node']\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := Load(path); err == nil {
		t.Fatal("old host defaults accepted")
	}
	for _, s := range []string{"https://secret@example.test/v1", "https://example.test/v1?key=secret", "file:///tmp/x"} {
		if endpoint(s) == nil {
			t.Fatal("unsafe endpoint accepted")
		}
	}
}

func TestPrivateKeyFileRemainsHostOnly(t *testing.T) {
	key := filepath.Join(t.TempDir(), "model.key")
	if err := os.WriteFile(key, []byte("private-test-token\n"), 0600); err != nil {
		t.Fatal(err)
	}
	c := Config{Models: map[string]ModelService{"chosen": {Endpoint: "https://example.test/v1", APIKeyFile: key, Worker: []string{"explicit-worker"}}}}
	def := work.ModelDefinition{Service: "chosen", Parameters: map[string]any{"id": "test", "api": "openai-completions", "provider": "test"}}
	d, err := c.ResolveModel(def)
	if err != nil || d.APIKey != "private-test-token" {
		t.Fatal("private credential was not resolved", err)
	}
	if d.Worker[0] != "explicit-worker" || len(def.Parameters) != 3 || len(d.Model) != 4 {
		t.Fatal("credential or deployment data leaked into portable model or argv")
	}
	if err = os.Chmod(key, 0644); err != nil {
		t.Fatal(err)
	}
	if _, err = c.ResolveModel(def); err == nil || strings.Contains(err.Error(), "private-test-token") {
		t.Fatal("readable credential file accepted or disclosed")
	}
}

func TestCredentialReferencesRejectAmbiguityAndUnsafeFiles(t *testing.T) {
	dir := t.TempDir()
	key := filepath.Join(dir, "key")
	if err := os.WriteFile(key, []byte("not-an-error-message"), 0600); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(dir, "link")
	if err := os.Symlink(key, link); err != nil {
		t.Fatal(err)
	}
	empty := filepath.Join(dir, "empty")
	if err := os.WriteFile(empty, []byte(" \n"), 0600); err != nil {
		t.Fatal(err)
	}
	for _, reference := range [][2]string{{"TEST_KEY", key}, {"", "relative.key"}, {"", link}, {"", dir}, {"", empty}, {"", filepath.Join(dir, "missing")}} {
		if _, err := credential(reference[0], reference[1]); err == nil || strings.Contains(err.Error(), "not-an-error-message") {
			t.Fatalf("unsafe reference accepted or disclosed: %v", reference)
		}
	}
}

func TestModelDescriptionDoesNotReadCredentialsBeforeDispatch(t *testing.T) {
	t.Setenv("LOOM_UNAVAILABLE_MODEL_KEY", "")
	c := Config{Models: map[string]ModelService{"model": {Endpoint: "https://example.test/v1", APIKeyEnv: "LOOM_UNAVAILABLE_MODEL_KEY", Worker: []string{"node", "worker.mjs"}, HeadersEnv: map[string]string{"X-Private": "LOOM_UNAVAILABLE_MODEL_KEY"}, Parameters: map[string]any{"contextWindow": 32768}}}}
	def := work.ModelDefinition{Service: "model", Parameters: map[string]any{"id": "test", "api": "openai-completions", "provider": "fixture"}}
	description, err := c.DescribeModel(def)
	if err != nil || description.APIKey != "" || description.Model["headers"] != nil || description.Model["contextWindow"] != float64(32768) {
		t.Fatal("credential-free description failed", err)
	}
	if _, err = c.ResolveModel(def); err == nil {
		t.Fatal("actual dispatch resolved without required credentials")
	}
}
