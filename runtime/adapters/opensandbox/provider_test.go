package opensandbox

import (
	"encoding/json"
	"testing"
)

func TestProviderRestoresExactBindingAndRejectsIncompleteOptions(t *testing.T) {
	c, err := New(Config{ServiceID: "remote", Endpoint: "https://remote.example", APIKey: "private", Image: testImage})
	if err != nil {
		t.Fatal(err)
	}
	original := c.Binding()
	restored, err := Open(original, "new-credential")
	if err != nil || restored.Binding() != original {
		t.Fatal("saved binding drift", err)
	}
	for _, key := range []string{"image", "profile", "cpu", "memory", "lease_seconds", "request_timeout_seconds"} {
		var options map[string]any
		if err := json.Unmarshal([]byte(original.OptionsJSON), &options); err != nil {
			t.Fatal(err)
		}
		delete(options, key)
		raw, _ := json.Marshal(options)
		binding := original
		binding.OptionsJSON = string(raw)
		if _, err := Open(binding, "private"); err == nil {
			t.Fatal("missing option defaulted", key)
		}
	}
	for _, raw := range []string{`null`, `{}`, `{"unknown":true}`, original.OptionsJSON + `{}`} {
		binding := original
		binding.OptionsJSON = raw
		if _, err := Open(binding, "private"); err == nil {
			t.Fatal("invalid options accepted", raw)
		}
	}
	wrong := original
	wrong.Provider = "opensandbox/v2"
	if _, err := Open(wrong, "private"); err == nil {
		t.Fatal("unknown version accepted")
	}
}
