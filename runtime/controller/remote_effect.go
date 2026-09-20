package controller

import (
	"context"
	"encoding/json"
	"errors"

	"loom/runtime/contracts"
	"loom/runtime/rpc"
	"loom/runtime/store"
	"loom/runtime/work"
)

func (r *Runtime) originalExecution(w *work.Work, roundID, effectID string) (store.Effect, contracts.TaskExecutor, string, string, error) {
	var effect store.Effect
	if err := r.Authority.Authorize(w); err != nil {
		return effect, nil, "", "", err
	}
	if r.ResolveSandbox == nil {
		return effect, nil, "", "", &rpc.Error{Kind: "capability_missing"}
	}
	effects, err := w.Control.Effects(roundID)
	if err != nil {
		return effect, nil, "", "", err
	}
	for _, e := range effects {
		if e.ID != effectID {
			continue
		}
		effect = e
		if e.Kind != "tool.exec" || e.Request["environment"] != "sandbox" {
			return effect, nil, "", "", &rpc.Error{Kind: "capability_missing"}
		}
		sid, _ := e.Receipt["sandbox_id"].(string)
		eid, _ := e.Receipt["execution_id"].(string)
		if sid == "" || eid == "" {
			return effect, nil, "", "", &rpc.Error{Kind: "outcome_unknown"}
		}
		var binding contracts.Binding
		body, err := json.Marshal(e.Receipt["binding"])
		if err != nil {
			return effect, nil, "", "", err
		}
		if err = json.Unmarshal(body, &binding); err != nil || binding.ServiceID == "" || binding.Endpoint == "" {
			return effect, nil, "", "", errors.New("invalid saved execution binding")
		}
		executor, err := r.ResolveSandbox(binding)
		if err == nil && (executor == nil || executor.Binding() != binding) {
			return effect, nil, "", "", &rpc.Error{Kind: "permission_denied", Diagnostic: "saved execution destination changed"}
		}
		return effect, executor, sid, eid, err
	}
	return effect, nil, "", "", &rpc.Error{Kind: "permission_denied"}
}

func (r *Runtime) CancelRemote(ctx context.Context, w *work.Work, roundID, effectID string) (Object, error) {
	effect, executor, sid, eid, err := r.originalExecution(w, roundID, effectID)
	if err != nil {
		return nil, err
	}
	if effect.Cancellation == "stop_confirmed" {
		return Object{"effect_id": effect.ID, "accepted": true, "cancellation": "stop_confirmed"}, nil
	}
	if err = w.Control.RequestCancellation(effect.ID); err != nil {
		return nil, err
	}
	observation, callErr := executor.Cancel(ctx, sid, eid, executor.Binding())
	confirmed := callErr == nil
	if callErr != nil {
		observation = Object{"observation": "unknown", "reason": "cancellation transport did not confirm stop"}
	}
	if err = w.Control.ObserveCancellation(effect.ID, confirmed, observation); err != nil {
		return nil, err
	}
	state := "unknown"
	if confirmed {
		state = "stop_confirmed"
	}
	return Object{"effect_id": effect.ID, "accepted": true, "cancellation": state}, nil
}
