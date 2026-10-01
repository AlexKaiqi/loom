// Package model invokes one model request. Provider adaptation belongs to model-service.
package model

import (
	"context"
	"encoding/json"
	"errors"
	"loom/runtime/recordwire"
	"loom/runtime/rpc"
	"loom/runtime/store"
	"time"
)

type Object = map[string]any
type Request struct {
	Session                 rpc.Session
	Context, Model, Options Object
	APIKey                  string
	Timeout                 time.Duration
}

func Invoke(ctx context.Context, command []string, request Request) (Object, error) {
	if request.Timeout <= 0 || request.Context == nil || request.Session.RecordDirectory == "" {
		return nil, errors.New("model context, timeout and record directory required")
	}
	records := store.Records{Directory: request.Session.RecordDirectory}
	request.Session.RequiredCapabilities = append(request.Session.RequiredCapabilities, "record.file/1")
	client, err := rpc.Start(ctx, command, "", nil, "model", request.Session)
	if err != nil {
		return nil, err
	}
	defer client.Close()
	ctx, cancel := context.WithTimeout(ctx, request.Timeout+time.Second)
	defer cancel()
	params, err := recordwire.Context(records, Object{"protocol_version": "loom/1", "schema_version": 1,
		"model": request.Model, "context": request.Context, "options": request.Options, "apiKey": request.APIKey, "timeoutMs": request.Timeout.Milliseconds()})
	if err != nil {
		return nil, err
	}
	var raw json.RawMessage
	if err = client.Call(ctx, "model.complete", params, &raw); err != nil {
		return nil, err
	}
	var result Object
	err = recordwire.Decode(records, raw, &result)
	return result, err
}
