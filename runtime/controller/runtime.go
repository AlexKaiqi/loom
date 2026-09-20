// Package controller owns durable custody and authorization. Pi owns local
// model/tool iteration; Harness owns policy; OpenSandbox owns remote execution.
package controller

import (
	"context"
	"encoding/json"
	"errors"
	"loom/runtime/authority"
	"loom/runtime/policy"
	"loom/runtime/sandbox"
	"loom/runtime/store"
	"loom/runtime/work"
	"path/filepath"
)

type Object = map[string]any
type Runtime struct {
	Authority      *authority.Authority
	Model          Object
	APIKey         string
	ModelCommand   []string
	Sandbox        *sandbox.Client
	ResolveSandbox func(sandbox.Binding) (*sandbox.Client, error)
}

func (r *Runtime) Admit(ctx context.Context, w *work.Work, requestID, kind string, payload Object) (store.Event, error) {
	if err := r.Authority.Authorize(w); err != nil {
		return store.Event{}, err
	}
	p, err := policy.Open(ctx, filepath.Join(w.Path, "harness"))
	if err != nil {
		return store.Event{}, err
	}
	defer p.Close()
	if err = p.Admit(ctx, kind, payload, "host"); err != nil {
		return store.Event{}, err
	}
	return w.Events.Admit("host", requestID, kind, payload)
}
func (r *Runtime) Relay(ctx context.Context, sender, receiver *work.Work, requestID, kind string, payload Object) (store.Event, error) {
	if err := r.Authority.RelayAllowed(sender, receiver); err != nil {
		return store.Event{}, err
	}
	p, err := policy.Open(ctx, filepath.Join(receiver.Path, "harness"))
	if err != nil {
		return store.Event{}, err
	}
	defer p.Close()
	source := "work:" + sender.ID
	if err = p.Admit(ctx, kind, payload, source); err != nil {
		return store.Event{}, err
	}
	return receiver.Events.Admit(source, requestID, kind, payload)
}
func (r *Runtime) Query(w *work.Work) (Object, error) {
	if err := r.Authority.Authorize(w); err != nil {
		return nil, err
	}
	rounds, err := w.Control.Rounds()
	if err != nil {
		return nil, err
	}
	pending, err := w.Events.Pending()
	if err != nil {
		return nil, err
	}
	effects := map[string][]store.Effect{}
	for _, round := range rounds {
		effects[round.ID], err = w.Control.Effects(round.ID)
		if err != nil {
			return nil, err
		}
	}
	return Object{"definition": w.Definition, "work_id": w.ID, "pending": pending, "rounds": rounds, "effects": effects}, nil
}
func (r *Runtime) QueryRemote(ctx context.Context, w *work.Work, roundID, effectID string) (Object, error) {
	if err := r.Authority.Authorize(w); err != nil {
		return nil, err
	}
	if r.ResolveSandbox == nil {
		return nil, errors.New("sandbox is not configured")
	}
	effects, err := w.Control.Effects(roundID)
	if err != nil {
		return nil, err
	}
	for _, e := range effects {
		if e.ID == effectID && e.Kind == "sandbox.shell" {
			sid, _ := e.Receipt["sandbox_id"].(string)
			eid, _ := e.Receipt["execution_id"].(string)
			if sid != "" && eid != "" {
				var binding sandbox.Binding
				data, err := json.Marshal(e.Receipt["binding"])
				if err != nil {
					return nil, err
				}
				if err = json.Unmarshal(data, &binding); err != nil {
					return nil, errors.New("invalid saved remote service binding")
				}
				if binding.ServiceID == "" || binding.Endpoint == "" {
					return nil, errors.New("remote execution has no saved service binding")
				}
				client, err := r.ResolveSandbox(binding)
				if err != nil {
					return nil, err
				}
				return client.Query(ctx, sid, eid, binding)
			}
		}
	}
	return nil, errors.New("no saved remote execution identity; automatic replay forbidden")
}
