package controller

import (
	"encoding/json"
	"loom/runtime/policy"
	"loom/runtime/store"
	"os"
	"path/filepath"
	"testing"
)

func TestHarnessRejectsUndeclaredAndCrossMethodFieldsBeforeCustody(t *testing.T) {
	c := apiFixture(t)
	before, err := os.ReadDir(c.work.ArtifactsDir())
	if err != nil {
		t.Fatal(err)
	}
	for _, params := range []Object{
		{"media_type": "text/plain", "data_base64": "eA==", "new_authority": true},
		{"media_type": "text/plain", "data_base64": "eA==", "environment": "work"},
		{"media_type": "text/plain", "data_base64": nil},
	} {
		_, err := apiCall(c, "record.put", params)
		requireAPIKind(t, err, "invalid_request")
	}
	entries, err := os.ReadDir(c.work.ArtifactsDir())
	if err != nil && !os.IsNotExist(err) {
		t.Fatal(err)
	}
	if len(entries) != len(before) {
		t.Fatal("rejected request published a record")
	}
	requireAPIKind(t, harnessError("checkpoint.commit", store.ErrUnknownEffect), "outcome_unknown")
	requireAPIKind(t, harnessError("checkpoint.commit", store.ErrConflict), "baseline_conflict")
	requireAPIKind(t, harnessError("subscription.put", store.ErrConflict), "identity_conflict")
}

func TestGeneratedInterfaceMatchesBoundVersionWithoutGrantingBashControl(t *testing.T) {
	c := apiFixture(t)
	c.round.HarnessRef = "fixed-harness"
	c.policy = &policy.Client{Manifest: policy.Manifest{Tools: []policy.Tool{{Name: "bash", Capability: "tool.exec", Parameters: Object{"type": "object"}}}}}
	directory := t.TempDir()
	if err := c.writeInterface(directory, os.Getuid(), os.Getgid()); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(directory, "interface.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var observed Object
	if err = json.Unmarshal(raw, &observed); err != nil {
		t.Fatal(err)
	}
	if observed["harness_ref"] != "fixed-harness" || observed["round_id"] != c.round.ID {
		t.Fatal("interface not bound to current Round")
	}
	permissions := observed["role_permissions"].(map[string]any)
	if len(permissions["bash"].([]any)) != 0 {
		t.Fatal("Bash received control capability")
	}
	schemas := observed["operations"].(map[string]any)
	if len(schemas) != len(harnessOperations) {
		t.Fatal("schema operations differ from channel authorization")
	}
	for _, op := range harnessOperations {
		schema := schemas[op].(map[string]any)
		if schema["additionalProperties"] != false {
			t.Fatal("unknown fields allowed", op)
		}
	}
	if _, exists := schemas["effect.succeeded"]; exists {
		t.Fatal("strategy can confirm external success")
	}
	if err = c.writeInterface(directory, os.Getuid(), os.Getgid()); err == nil {
		t.Fatal("published interface overwritten")
	}
}
