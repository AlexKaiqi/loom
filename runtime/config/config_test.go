package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"context"
	"loom/runtime/contracts"
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

type fixtureExecutor struct{ binding contracts.Binding }

func (f *fixtureExecutor) Binding() contracts.Binding { return f.binding }
func (*fixtureExecutor) Execute(context.Context, contracts.Request, func(contracts.Checkpoint) error) (contracts.Result, error) {
	return contracts.Result{}, nil
}
func (*fixtureExecutor) Query(context.Context, string, string, contracts.Binding) (map[string]any, error) {
	return nil, nil
}
func (*fixtureExecutor) Cancel(context.Context, string, string, contracts.Binding) (map[string]any, error) {
	return nil, nil
}
func (*fixtureExecutor) Release(context.Context, string) error { return nil }

func TestProviderInversionAndSavedBindingWithoutModelCredentials(t *testing.T) {
	t.Setenv("CONFIG_TEST_KEY", "host-secret")
	c := Config{Sandboxes: map[string]SandboxService{"remote": {Provider: "process-test/v1", Endpoint: "https://original.example/", APIKeyEnv: "CONFIG_TEST_KEY"}}, Profiles: map[string]SandboxProfile{"code": {Service: "remote", Options: map[string]any{"pool": "prepared", "isolation": "process"}}}}
	calls := 0
	factory := func(b contracts.Binding, key string) (contracts.TaskExecutor, error) {
		calls++
		if key != "host-secret" {
			t.Fatal("credential missing")
		}
		return &fixtureExecutor{b}, nil
	}
	resolver := c.SandboxResolver(map[string]contracts.ProviderFactory{"process-test/v1": factory})
	targets, err := resolver.ResolveTargets(map[string]work.TargetDefinition{"code": {Profile: "code"}})
	if err != nil {
		t.Fatal(err)
	}
	binding := targets["code"].Binding()
	if binding.Provider != "process-test/v1" || binding.OptionsJSON != `{"isolation":"process","pool":"prepared"}` {
		t.Fatal(binding)
	}
	c.Profiles["code"] = SandboxProfile{Service: "replacement", Options: map[string]any{"pool": "other"}}
	executor, err := resolver.ResolveSavedSandbox(binding)
	if err != nil || executor.Binding() != binding {
		t.Fatal("saved requirements changed", err)
	}
	original := binding
	for _, mutate := range []func(*contracts.Binding){
		func(b *contracts.Binding) { b.Provider = "other/v1" },
		func(b *contracts.Binding) { b.Provider = "" },
		func(b *contracts.Binding) { b.ServiceID = "missing" },
		func(b *contracts.Binding) { b.Endpoint = "https://replacement.example" },
		func(b *contracts.Binding) { b.OptionsJSON = "null" },
		func(b *contracts.Binding) { b.OptionsJSON = "" },
	} {
		binding = original
		mutate(&binding)
		before := calls
		if _, err = resolver.ResolveSavedSandbox(binding); err == nil || calls != before {
			t.Fatal("bad binding reached factory", binding, err)
		}
	}
	// Rebinding the same service name cannot redirect an old operation.
	c.Sandboxes["remote"] = SandboxService{Provider: "other/v1", Endpoint: original.Endpoint}
	if _, err = resolver.ResolveSavedSandbox(original); err == nil {
		t.Fatal("provider drift accepted")
	}
	c.Sandboxes["remote"] = SandboxService{Provider: original.Provider, Endpoint: original.Endpoint}
	if _, err = c.SandboxResolver(nil).ResolveSavedSandbox(original); err == nil {
		t.Fatal("unregistered provider accepted")
	}
	if _, err = c.SandboxResolver(map[string]contracts.ProviderFactory{original.Provider: func(b contracts.Binding, _ string) (contracts.TaskExecutor, error) {
		b.OptionsJSON = "{}"
		return &fixtureExecutor{b}, nil
	}}).ResolveSavedSandbox(original); err == nil {
		t.Fatal("factory binding drift accepted")
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
