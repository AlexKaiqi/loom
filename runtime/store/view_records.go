package store

import (
	"encoding/json"
	"errors"
	"path/filepath"
)

// Only the typed ToolResult details from the trusted tool bridge confer linked
// record access. A JSON object in user text or model tool arguments is data and
// cannot manufacture a grant to a hidden record by naming its digest.
func toolRecordRefs(fact Event) ([]RecordRef, error) {
	if fact.Source != "model-adapter" || fact.Kind != "tool.result" {
		return nil, nil
	}
	message, _ := fact.Payload["message"].(map[string]any)
	details, _ := message["details"].(map[string]any)
	values := []any{}
	for _, stream := range []string{"stdout", "stderr"} {
		v, _ := details[stream].(map[string]any)
		if v["record_ref"] != nil {
			values = append(values, v["record_ref"])
		}
	}
	if artifacts, ok := details["artifacts"].([]any); ok {
		for _, item := range artifacts {
			v, _ := item.(map[string]any)
			if v["record_ref"] != nil {
				values = append(values, v["record_ref"])
			}
		}
	}
	refs := []RecordRef{}
	for _, value := range values {
		raw, err := json.Marshal(value)
		if err != nil {
			return nil, err
		}
		var ref RecordRef
		if err = json.Unmarshal(raw, &ref); err != nil {
			return nil, err
		}
		if err = ref.Validate(); err != nil {
			return nil, err
		}
		refs = append(refs, ref)
	}
	return refs, nil
}
func materializeLinkedRecords(records Records, fact Event, destination string) error {
	refs, err := toolRecordRefs(fact)
	if err != nil {
		return err
	}
	for _, ref := range refs {
		raw, err := records.Get(ref)
		if err != nil {
			return err
		}
		got, err := (Records{Directory: filepath.Join(destination, "records")}).Put(raw, ref.MediaType)
		if err != nil {
			return err
		}
		if got != ref {
			return errors.New("linked ToolResult record changed")
		}
	}
	return nil
}
