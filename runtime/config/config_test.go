package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"loom/runtime/sandbox"
	"loom/runtime/work"
)

func TestNamedBindingsDoNotSupplyWorkSemantics(t *testing.T) {
	t.Setenv("CONFIG_TEST_KEY", "host-secret")
	c := Config{Models: map[string]ModelService{"chosen": {Endpoint: "https://example.test/v1", APIKeyEnv: "CONFIG_TEST_KEY", Worker: []string{"node", "worker.mjs"}, HeadersEnv: map[string]string{"X-Key": "CONFIG_TEST_KEY"}}, "unused": {APIKeyEnv: "MISSING_UNUSED_KEY"}}}
	def := work.ModelDefinition{Service: "chosen", Definition: map[string]any{"id": "work-model", "api": "openai-completions", "provider": "work-provider"}}
	got, err := c.ResolveModel(def)
	if err != nil {
		t.Fatal(err)
	}
	if got.Model["id"] != "work-model" || got.Model["baseUrl"] != "https://example.test/v1" || got.APIKey != "host-secret" {
		t.Fatal("incorrect resolution")
	}
	if def.Definition["headers"] != nil || def.Definition["baseUrl"] != nil {
		t.Fatal("host values contaminated Work")
	}
	def.Service = "missing"
	if _, err = c.ResolveModel(def); err == nil {
		t.Fatal("missing binding accepted")
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
	if err := os.WriteFile(path, []byte("[model]\nworker=['node']\n"), 0600); err != nil {
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
	def := work.ModelDefinition{Service: "chosen", Definition: map[string]any{"id": "test", "api": "openai-completions", "provider": "test"}}
	d, err := c.ResolveModel(def)
	if err != nil || d.APIKey != "private-test-token" {
		t.Fatal("private credential was not resolved", err)
	}
	if d.Worker[0] != "explicit-worker" || len(def.Definition) != 3 || len(d.Model) != 4 {
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
