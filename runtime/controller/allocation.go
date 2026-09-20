package controller

import (
	"context"
	"encoding/json"
	"errors"
	"loom/runtime/contracts"
	"loom/runtime/rpc"
	"loom/runtime/store"
	"loom/runtime/work"
	"os"
)

func (c *run) acquireAllocation(ctx context.Context, key, target string) (any, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if key == "" || target == "" {
		return nil, &rpc.Error{Kind: "invalid_request"}
	}
	prior, err := c.work.Control.EffectByKey(c.round.ID, "allocation:"+key)
	if err != nil {
		return nil, err
	}
	if prior != nil {
		if prior.Request["target"] != target {
			return nil, &rpc.Error{Kind: "identity_conflict"}
		}
		allocations, err := c.work.Control.Allocations(c.round.ID)
		if err != nil {
			return nil, err
		}
		for _, a := range allocations {
			if a.EffectID == prior.ID {
				return a, nil
			}
		}
		return nil, &rpc.Error{Kind: "outcome_unknown"}
	}
	executor := c.runtime.Targets[target]
	provider, ok := executor.(contracts.AllocationProvider)
	if !ok {
		return nil, &rpc.Error{Kind: "capability_missing"}
	}
	if err = c.runtime.Authority.Authorize(c.work); err != nil {
		return nil, err
	}
	if err = c.clearEffects(); err != nil {
		return nil, err
	}
	allocations, err := c.work.Control.Allocations(c.round.ID)
	if err != nil {
		return nil, err
	}
	for _, a := range allocations {
		if a.Target == target && a.ReleaseState != "confirmed" {
			return nil, &rpc.Error{Kind: "not_ready"}
		}
	}
	ws, err := c.taskWorkspace(target)
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(ws.directory)
	effect, err := c.work.Control.PrepareEffect(c.round.ID, "allocation:"+key, "allocation.acquire", Object{"target": target, "provider_scope": provider.Binding(), "userspace_bindings_ref": ws.bindings})
	if err != nil {
		return nil, err
	}
	id, err := c.saveAllocation(effect.ID, ws, provider.Binding())
	if err != nil {
		return nil, err
	}
	if err = c.work.Control.AttemptEffect(effect.ID, c.round.Owner); err != nil {
		return nil, err
	}
	observed, err := provider.Acquire(ctx, effect.ID, target)
	if err != nil {
		_ = c.work.Control.UnknownEffect(effect.ID, "allocation request outcome unknown; inspect original binding")
		return Object{"allocation_id": id, "effect_id": effect.ID, "accepted": true, "state": "unknown"}, nil
	}
	native, e := asObject(observed)
	if e != nil {
		return nil, e
	}
	if err = c.work.Control.ObserveAllocation(id, "allocation.acquired", native, observed.ID); err != nil {
		return nil, err
	}
	if observed.ID == "" {
		return nil, &rpc.Error{Kind: "outcome_unknown"}
	}
	if err = c.work.Control.CompleteEffect(effect.ID, native); err != nil {
		return nil, err
	}
	return Object{"allocation_id": id, "effect_id": effect.ID, "accepted": true, "binding": provider.Binding(), "state": "allocated", "execution_ready": false}, nil
}
func (c *run) clearEffects() error {
	effects, err := c.work.Control.Effects(c.round.ID)
	if err != nil {
		return err
	}
	for _, e := range effects {
		if e.Resolution == "unresolved" || e.ContentDelivery == "pending" || e.ContentDelivery == "unknown" || e.ContentDelivery == "failed" {
			return store.ErrUnknownEffect
		}
	}
	return nil
}
func (r *Runtime) allocationProvider(a store.Allocation) (contracts.TaskExecutor, contracts.AllocationProvider, error) {
	raw, err := json.Marshal(a.Binding["provider_scope"])
	if err != nil {
		return nil, nil, err
	}
	var binding contracts.Binding
	if err = json.Unmarshal(raw, &binding); err != nil {
		return nil, nil, err
	}
	var executor contracts.TaskExecutor
	if r.ResolveSandbox != nil {
		executor, err = r.ResolveSandbox(binding)
	} else {
		executor = r.Targets[a.Target]
	}
	if err != nil {
		return nil, nil, err
	}
	if executor == nil || executor.Binding() != binding {
		return nil, nil, &rpc.Error{Kind: "permission_denied"}
	}
	provider, ok := executor.(contracts.AllocationProvider)
	if !ok {
		return nil, nil, &rpc.Error{Kind: "capability_missing"}
	}
	return executor, provider, nil
}
func (c *run) reusableAllocation(target string) (*store.Allocation, contracts.TaskExecutor, error) {
	list, err := c.work.Control.Allocations(c.round.ID)
	if err != nil {
		return nil, nil, err
	}
	effects, err := c.work.Control.Effects(c.round.ID)
	if err != nil {
		return nil, nil, err
	}
	acquired := map[string]bool{}
	for _, e := range effects {
		acquired[e.ID] = e.Kind == "allocation.acquire" && e.Status == "completed"
	}
	for _, a := range list {
		if a.Target == target && a.ReleaseState != "confirmed" && acquired[a.EffectID] {
			if a.SandboxID == "" {
				return nil, nil, &rpc.Error{Kind: "not_ready"}
			}
			executor, _, err := c.runtime.allocationProvider(a)
			return &a, executor, err
		}
	}
	return nil, nil, nil
}
func (r *Runtime) Allocation(ctx context.Context, w *work.Work, roundID, id, operation string) (any, error) {
	if err := r.Authority.Authorize(w); err != nil {
		return nil, err
	}
	list, err := w.Control.Allocations(roundID)
	if err != nil {
		return nil, err
	}
	var selected *store.Allocation
	for _, a := range list {
		if a.ID == id {
			copy := a
			selected = &copy
			break
		}
	}
	if selected == nil {
		return nil, &rpc.Error{Kind: "permission_denied"}
	}
	a := *selected
	if a.ReleaseState == "confirmed" {
		return a, nil
	}
	_, provider, err := r.allocationProvider(a)
	if err != nil {
		return nil, err
	}
	native, err := provider.InspectAllocation(ctx, a.EffectID, a.SandboxID)
	if err != nil {
		return nil, err
	}
	body, err := asObject(native)
	if err != nil {
		return nil, err
	}
	if err = w.Control.ObserveAllocation(a.ID, "allocation.inspected", body, native.ID); err != nil {
		return nil, err
	}
	effects, err := w.Control.Effects(roundID)
	if err != nil {
		return nil, err
	}
	for _, e := range effects {
		if e.ID == a.EffectID && e.Kind == "allocation.acquire" && e.Status != "completed" && native.ID != "" && native.State != "absent" {
			if err = w.Control.CompleteEffect(e.ID, body); err != nil {
				return nil, err
			}
		}
	}
	if operation == "inspect" {
		return Object{"allocation": a, "observation": native}, nil
	}
	if operation != "release" {
		return nil, errors.New("invalid allocation operation")
	}
	for _, e := range effects {
		if e.Kind == "tool.exec" && (e.ID == a.EffectID || e.Request["allocation_id"] == a.ID) && (e.Resolution == "unresolved" || e.ContentDelivery != "confirmed") {
			return nil, &rpc.Error{Kind: "not_ready", Diagnostic: "necessary execution result or content is not saved"}
		}
	}
	if native.ID == "" {
		return nil, &rpc.Error{Kind: "outcome_unknown"}
	}
	if err = w.Control.ObserveAllocation(a.ID, "allocation.release_requested", Object{"sandbox_id": native.ID}, native.ID); err != nil {
		return nil, err
	}
	var releaseErr error
	if native.State != "absent" {
		releaseErr = provider.Release(ctx, native.ID)
	}
	if err = w.Control.AllocationReleaseObserved(a.ID, releaseErr == nil); err != nil {
		return nil, err
	}
	if releaseErr != nil {
		return nil, releaseErr
	}
	return Object{"allocation_id": a.ID, "release_state": "confirmed"}, nil
}
func (c *run) releaseAllocations(ctx context.Context) error {
	list, err := c.work.Control.Allocations(c.round.ID)
	if err != nil {
		return err
	}
	for _, a := range list {
		if a.ReleaseState != "confirmed" {
			if _, err = c.runtime.Allocation(ctx, c.work, c.round.ID, a.ID, "release"); err != nil {
				return err
			}
		}
	}
	return nil
}
