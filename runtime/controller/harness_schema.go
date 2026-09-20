package controller

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"loom/runtime/store"
	"reflect"
	"sort"
	"strings"
)

type harnessParams struct {
	Protocol             string          `json:"protocol_version"`
	Schema               int             `json:"schema_version"`
	WorkID               string          `json:"work_id"`
	RoundID              string          `json:"round_id"`
	Epoch                string          `json:"epoch"`
	ContentVersion       string          `json:"content_version"`
	HarnessRef           string          `json:"harness_ref"`
	Path                 string          `json:"path"`
	Data                 string          `json:"data_base64"`
	MediaType            string          `json:"media_type"`
	Ref                  store.RecordRef `json:"record_ref"`
	ProjectionRef        store.RecordRef `json:"projection_ref"`
	RequestKey           string          `json:"request_key"`
	CheckpointID         string          `json:"checkpoint_id"`
	PreviousCheckpointID string          `json:"previous_checkpoint_id"`
	ResourceCopies       []Object        `json:"resource_copies"`
	HandledInputs        []string        `json:"handled_input_ids"`
	Intent               string          `json:"intent"`
	Kind                 string          `json:"kind"`
	Environment          string          `json:"environment"`
	Target               string          `json:"target"`
	PayloadRef           store.RecordRef `json:"payload_ref"`
	Offset               string          `json:"offset"`
	Length               int             `json:"length"`
	ViewID               string          `json:"view_id"`
	Scope                string          `json:"scope"`
	FactID               string          `json:"fact_id"`
	ID                   string          `json:"id"`
	SourceWorkID         string          `json:"source_work_id"`
	Kinds                []string        `json:"kinds"`
	Start                string          `json:"start"`
}

// The dispatch fields and generated authoring schemas share one method table.
// These describe syntax only; epoch, record custody and resource authorization
// are independently enforced against the bound session and persistent state.
var harnessFields = map[string]string{
	"record.put": "path data_base64 media_type", "record.get": "record_ref offset length",
	"fact.read": "view_id fact_id", "view.open": "view_id scope",
	"subscription.put": "id source_work_id kinds start", "subscription.remove": "id",
	"effect.request": "request_key kind environment target payload_ref", "effect.inspect": "id", "effect.cancel": "id",
	"projection.publish": "content_version view_id record_ref",
	"model.start":        "request_key projection_ref", "model.resume": "request_key checkpoint_id",
	"checkpoint.commit":  "content_version previous_checkpoint_id resource_copies",
	"round.handoff":      "checkpoint_id handled_input_ids intent",
	"allocation.acquire": "request_key target", "allocation.inspect": "id", "allocation.release": "id",
}

const commonHarnessFields = "protocol_version schema_version work_id round_id epoch harness_ref"

func decodeHarnessParams(method string, raw []byte, result *harnessParams) error {
	fields, ok := harnessFields[method]
	if !ok {
		return errors.New("unknown Harness operation")
	}
	allowed := map[string]bool{}
	for _, field := range strings.Fields(commonHarnessFields + " " + fields) {
		allowed[field] = true
	}
	var object map[string]json.RawMessage
	if err := json.Unmarshal(raw, &object); err != nil {
		return err
	}
	for key, value := range object {
		if !allowed[key] || bytes.Equal(bytes.TrimSpace(value), []byte("null")) {
			return errors.New("unsupported operation field")
		}
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	decoder.UseNumber()
	if err := decoder.Decode(result); err != nil {
		return err
	}
	if err := decoder.Decode(new(any)); err != io.EOF {
		return errors.New("trailing request bytes")
	}
	return nil
}

func syntaxType(t reflect.Type) Object {
	switch t.Kind() {
	case reflect.String:
		return Object{"type": "string"}
	case reflect.Int, reflect.Int64:
		return Object{"type": "integer"}
	case reflect.Slice:
		return Object{"type": "array", "items": syntaxType(t.Elem())}
	case reflect.Map:
		return Object{"type": "object"}
	case reflect.Struct:
		fields := Object{}
		required := []string{}
		for i := 0; i < t.NumField(); i++ {
			f := t.Field(i)
			name := strings.Split(f.Tag.Get("json"), ",")[0]
			fields[name] = syntaxType(f.Type)
			required = append(required, name)
		}
		return Object{"type": "object", "properties": fields, "required": required, "additionalProperties": false}
	}
	return Object{}
}

func harnessSchemas() Object {
	fields := Object{}
	t := reflect.TypeFor[harnessParams]()
	for i := 0; i < t.NumField(); i++ {
		f := t.Field(i)
		fields[f.Tag.Get("json")] = syntaxType(f.Type)
	}
	result := Object{}
	for method, specific := range harnessFields {
		props := Object{}
		for _, name := range strings.Fields(commonHarnessFields + " " + specific) {
			props[name] = fields[name]
		}
		result[method] = Object{"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "properties": props, "required": []string{"protocol_version", "schema_version"}, "additionalProperties": false}
	}
	return result
}

func operationNames() []string {
	names := make([]string, 0, len(harnessFields))
	for name := range harnessFields {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}
