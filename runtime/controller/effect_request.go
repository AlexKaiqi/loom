package controller

import (
	"context"
	"errors"
	"loom/runtime/rpc"
	"loom/runtime/store"
)

func (c *run) acceptedEffect(effect store.Effect) (Object, error) {
	request, err := artifact(c.work, effect.Request)
	if err != nil {
		return nil, err
	}
	destination := copyObject(object(effect.Request["execution_scope"]))
	destination["environment"] = effect.Request["environment"]
	if effect.Request["environment"] == "sandbox" {
		destination["target"] = effect.Request["target"]
		destination["provider_scope"] = effect.Request["provider_scope"]
		destination["userspace_bindings_ref"] = effect.Request["userspace_bindings_ref"]
		db, err := store.OpenDB(c.work.DBPath)
		if err != nil {
			return nil, err
		}
		var allocation string
		if reused, ok := effect.Request["allocation_id"].(string); ok {
			allocation = reused
		} else {
			err = db.QueryRow("SELECT id FROM allocations WHERE effect_id=?", effect.ID).Scan(&allocation)
		}
		db.Close()
		if err != nil {
			return nil, err
		}
		destination["allocation_id"], destination["binding_generation"] = allocation, "1"
	}
	body := Object{"effect_id": effect.ID, "request_ref": request, "destination_binding": destination}
	fact, err := c.work.Events.AppendOwned("runtime", "effect-accepted:"+effect.ID, "effect.accepted", body)
	if err != nil {
		return nil, err
	}
	body["accepted_fact_id"], body["accepted"] = fact.FactID, true
	return body, nil
}
func (c *run) requestTool(ctx context.Context, key, kind, environment, target string, ref store.RecordRef) (any, error) {
	if key == "" {
		return nil, &rpc.Error{Kind: "invalid_request"}
	}
	if kind != "tool.exec" {
		return nil, &rpc.Error{Kind: "capability_missing"}
	}
	raw, err := c.readPolicyRecord(ref)
	if err != nil {
		return nil, err
	}
	args, err := store.DecodeObject(string(raw))
	if err != nil {
		return nil, &rpc.Error{Kind: "invalid_request"}
	}
	for name := range args {
		if name != "script" && name != "timeout" {
			return nil, &rpc.Error{Kind: "invalid_request"}
		}
	}
	args["environment"] = environment
	if target != "" {
		args["target"] = target
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.modelEffect != nil {
		return nil, &rpc.Error{Kind: "not_ready"}
	}
	if c.repairMode && environment != "work" {
		return nil, &rpc.Error{Kind: "not_ready"}
	}
	_, executionErr := c.executeTool(ctx, "harness:"+key, args)
	if executionErr != nil && !errors.Is(executionErr, store.ErrUnknownEffect) {
		// A changed key must not be acknowledged as the old request. Other failures
		// after acceptance remain visible through the saved Effect, never replayed.
		if errors.Is(executionErr, store.ErrConflict) {
			return nil, &rpc.Error{Kind: "identity_conflict"}
		}
	}
	effect, err := c.work.Control.EffectByKey(c.round.ID, "harness:"+key)
	if err != nil {
		return nil, err
	}
	if effect == nil {
		return nil, executionErr
	}
	return c.acceptedEffect(*effect)
}
