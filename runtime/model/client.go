// Package model transports native Pi data. It contains no provider adaptation
// or model/tool loop: services/model owns both through upstream Pi.
package model

import (
	"context"
	"encoding/json"
	"errors"
	"loom/runtime/rpc"
	"time"
)

type Object = map[string]any
type Callbacks struct {
	Event    func(Object) error
	Tool     func(context.Context, string, Object, string) (Object, error)
	Continue func(context.Context, Object) (bool, error)
	Prepare  func(context.Context, Object) (Object, error)
}
type Request struct {
	Context, Model, Options Object
	APIKey                  string
	Tools                   []Object
	MaxTurns                int
	Timeout                 time.Duration
}

func Run(ctx context.Context, command []string, request Request, callbacks Callbacks) ([]Object, error) {
	if request.Timeout <= 0 || request.MaxTurns <= 0 || request.Context == nil {
		return nil, errors.New("invalid model plan limits or context")
	}
	handle := func(ctx context.Context, method string, raw json.RawMessage) (any, error) {
		var p Object
		if err := rpc.Decode(raw, &p); err != nil {
			return nil, err
		}
		switch method {
		case "agent.event":
			return nil, callbacks.Event(p)
		case "tool.execute":
			name, _ := p["name"].(string)
			id, _ := p["toolCallId"].(string)
			args, _ := p["arguments"].(map[string]any)
			if id == "" || args == nil {
				return nil, errors.New("invalid tool request")
			}
			return callbacks.Tool(ctx, name, args, id)
		case "agent.shouldStop":
			cont, err := callbacks.Continue(ctx, p)
			return !cont, err
		case "agent.prepareTurn":
			return callbacks.Prepare(ctx, p)
		default:
			return nil, errors.New("unknown model callback")
		}
	}
	client, err := rpc.Start(ctx, command, "", handle)
	if err != nil {
		return nil, err
	}
	defer client.Close()
	ctx, cancel := context.WithTimeout(ctx, request.Timeout+time.Second)
	defer cancel()
	native := Object{}
	for key, val := range request.Context {
		native[key] = val
	}
	native["tools"] = request.Tools
	var messages []Object
	err = client.Call(ctx, "agent.run", Object{"protocol": 1, "context": native, "model": request.Model, "apiKey": request.APIKey, "options": request.Options, "maxTurns": request.MaxTurns, "timeoutMs": request.Timeout.Milliseconds(), "hooks": []string{"shouldStop", "prepareTurn"}}, &messages)
	return messages, err
}
