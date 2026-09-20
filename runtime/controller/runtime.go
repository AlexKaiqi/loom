// Package controller owns durable custody and authorization. Pi owns local
// model/tool iteration; Harness owns policy; OpenSandbox owns remote execution.
package controller

import (
	"context"
	"errors"
	"loom/runtime/authority"
	sandbox "loom/runtime/contracts"
	"loom/runtime/execution"
	"loom/runtime/store"
	"loom/runtime/work"
	"strings"
)

type Object = map[string]any
type Runtime struct {
	Configure      func(*Runtime, *work.Work) error
	ActivateModel  func(*Runtime) error
	Execution      *execution.Config
	Authority      *authority.Authority
	Model          Object
	APIKey         string
	ModelCommand   []string
	Targets        map[string]sandbox.TaskExecutor
	ResolveSandbox func(sandbox.Binding) (sandbox.TaskExecutor, error)
}

func (r *Runtime) Admit(ctx context.Context, w *work.Work, requestID, kind string, payload Object) (store.Event, error) {
	if err := r.Authority.Authorize(w); err != nil {
		return store.Event{}, err
	}
	if kind == "" || strings.HasPrefix(kind, "system.") {
		return store.Event{}, errors.New("invalid application input kind")
	}
	return w.Events.Admit("host", requestID, kind, payload)
}
func (r *Runtime) Relay(ctx context.Context, sender, receiver *work.Work, requestID, kind string, payload Object) (store.Event, error) {
	if err := r.Authority.RelayAllowed(sender, receiver); err != nil {
		return store.Event{}, err
	}
	source := "work:" + sender.ID
	if kind == "" || strings.HasPrefix(kind, "system.") {
		return store.Event{}, errors.New("invalid application event kind")
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
	allocations := map[string][]store.Allocation{}
	for _, round := range rounds {
		effects[round.ID], err = w.Control.Effects(round.ID)
		if err != nil {
			return nil, err
		}
		allocations[round.ID], err = w.Control.Allocations(round.ID)
		if err != nil {
			return nil, err
		}
	}
	return Object{"definition": w.Definition, "work_id": w.ID, "pending": pending, "rounds": rounds, "effects": effects, "allocations": allocations}, nil
}
func (r *Runtime) QueryRemote(ctx context.Context, w *work.Work, roundID, effectID string) (Object, error) {
	effect, executor, sid, eid, err := r.originalExecution(w, roundID, effectID)
	if err != nil {
		return nil, err
	}
	observation, err := executor.Query(ctx, sid, eid, executor.Binding())
	if err != nil {
		return nil, err
	}
	if err = w.Control.ObserveEffect(effect.ID, "remote_query", observation); err != nil {
		return nil, err
	}
	return observation, nil
}
