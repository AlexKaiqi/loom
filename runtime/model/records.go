package model

import (
	"encoding/json"
	"errors"
	"loom/runtime/rpc"
	"loom/runtime/store"
)

const bulkThreshold = 256 << 10

func referenceContext(records store.Records, p Object) (Object, error) {
	context, ok := p["context"]
	if !ok {
		return p, nil
	}
	raw, err := json.Marshal(context)
	if err != nil {
		return nil, err
	}
	if len(raw) <= bulkThreshold {
		return p, nil
	}
	ref, err := records.Put(raw, "application/json")
	if err != nil {
		return nil, err
	}
	result := Object{}
	for k, v := range p {
		if k != "context" {
			result[k] = v
		}
	}
	result["context_ref"] = ref
	return result, nil
}
func dereference(records store.Records, raw json.RawMessage, target any) error {
	var envelope struct {
		Ref *store.RecordRef `json:"payload_ref"`
	}
	// Arrays are legitimate native results and cannot be reference envelopes.
	if len(raw) > 0 && raw[0] == '{' {
		if err := json.Unmarshal(raw, &envelope); err != nil {
			return err
		}
	}
	if envelope.Ref != nil {
		var fields map[string]json.RawMessage
		if err := json.Unmarshal(raw, &fields); err != nil || len(fields) != 1 {
			return &rpc.Error{Kind: "invalid_request", Diagnostic: "ambiguous model record envelope"}
		}
		if envelope.Ref.MediaType != "application/json" {
			return errors.New("unexpected model record media type")
		}
		body, err := records.Get(*envelope.Ref)
		if err != nil {
			return err
		}
		raw = body
	}
	return rpc.Decode(raw, target)
}
