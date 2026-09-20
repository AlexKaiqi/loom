package opensandbox

import (
	"encoding/json"
	"testing"
)

func TestReadinessRequiresMeasuredCapabilitiesAndPermissions(t *testing.T) {
	valid := map[string]any{
		"platform": "linux", "architecture": "aarch64", "shell": "GNU bash, version 5.2",
		"tools": map[string]string{"python": "3.13.2"}, "uid": 65534, "gid": 65534,
		"process_capabilities": map[string]string{"CapEff": "0000000000000000", "CapPrm": "0000000000000000", "CapInh": "0000000000000000", "CapBnd": "0000000000000000", "CapAmb": "0000000000000000"},
		"no_new_privileges":    true, "network": "denied", "workspace": "/workspace/task", "readonly_paths": []string{"reference"},
	}
	data, err := json.Marshal(valid)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = parseReadiness(string(data), []string{"reference"}); err != nil {
		t.Fatal(err)
	}
	for key, value := range map[string]any{"platform": "darwin", "architecture": "", "shell": "", "tools": map[string]string{}, "uid": 0, "gid": 0, "process_capabilities": map[string]string{}, "no_new_privileges": false, "network": "allowed", "workspace": "/tmp", "readonly_paths": []string{}} {
		t.Run(key, func(t *testing.T) {
			var damaged map[string]any
			if err := json.Unmarshal(data, &damaged); err != nil {
				t.Fatal(err)
			}
			damaged[key] = value
			raw, err := json.Marshal(damaged)
			if err != nil {
				t.Fatal(err)
			}
			if _, err = parseReadiness(string(raw), []string{"reference"}); err == nil {
				t.Fatal("accepted missing or mismatched evidence")
			}
		})
	}
	for _, raw := range []string{"{}", "null", "garbage", string(data) + string(data)} {
		if _, err = parseReadiness(raw, []string{"reference"}); err == nil {
			t.Fatal("accepted incomplete readiness evidence", raw)
		}
	}
}
