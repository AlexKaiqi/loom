package rpc

import (
	"encoding/json"
	"errors"
)

// Session is constructed by the controller after durable ownership has been
// claimed. The peer can read these values but cannot grant itself a new binding.
type Session struct {
	LogDirectory         string   `json:"-"`
	WorkID               string   `json:"work_id,omitempty"`
	RoundID              string   `json:"round_id,omitempty"`
	Epoch                string   `json:"epoch,omitempty"`
	HarnessRef           string   `json:"harness_ref,omitempty"`
	Operations           []string `json:"operations"`
	RequiredCapabilities []string `json:"-"`
	Capabilities         []string `json:"-"`
	RecordDirectory      string   `json:"record_directory,omitempty"`
}

func (s Session) authorize(method string, raw json.RawMessage) error {
	if s.WorkID == "" {
		return nil
	} // Component-local transport tests have no Work.
	permitted := false
	for _, op := range s.Operations {
		if op == method {
			permitted = true
		}
	}
	if !permitted {
		return &Error{Kind: "permission_denied"}
	}
	var p map[string]json.RawMessage
	if err := json.Unmarshal(raw, &p); err != nil {
		return &Error{Kind: "invalid_request"}
	}
	for key, want := range map[string]string{"work_id": s.WorkID, "round_id": s.RoundID, "epoch": s.Epoch, "harness_ref": s.HarnessRef} {
		if body, ok := p[key]; ok {
			var value string
			if err := json.Unmarshal(body, &value); err != nil || value != want {
				return &Error{Kind: "stale_epoch"}
			}
		}
	}
	return nil
}

// AuthorizePayload checks the effective body after an optional immutable
// reference has been resolved. A reference cannot conceal a conflicting epoch.
func (s Session) AuthorizePayload(method string, value any) error {
	raw, err := json.Marshal(value)
	if err != nil {
		return err
	}
	return s.authorize(method, raw)
}

type Error struct {
	Kind       string
	Diagnostic string
}

func (e *Error) Error() string { return e.Kind + ": " + e.Diagnostic }
func publicKind(err error) string {
	var protocol *Error
	if errors.As(err, &protocol) {
		return protocol.Kind
	}
	return "internal_error"
}
