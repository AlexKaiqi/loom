package controller

import (
	"context"
	"errors"
	"loom/runtime/model"
	"loom/runtime/policy"
	"loom/runtime/rpc"
	"loom/runtime/store"
	"loom/runtime/work"
	"math"
	"path/filepath"
	"sync"
	"time"
)

type run struct {
	runtime               *Runtime
	work                  *work.Work
	policy                *policy.Client
	round                 store.Round
	mu                    sync.Mutex
	modelEffect           *store.Effect
	turnNumber            int
	lastTurn, lastRequest Object
	continueDecision      *bool
}

func (r *Runtime) Run(ctx context.Context, w *work.Work, resume bool) (result Object, err error) {
	if err = r.Authority.Authorize(w); err != nil {
		return nil, err
	}
	p, err := policy.Open(ctx, filepath.Join(w.Path, "harness"))
	if err != nil {
		return nil, err
	}
	defer p.Close()
	if len(p.Manifest.Tools) > 0 {
		if r.Sandbox == nil {
			return nil, errors.New("sandbox is not configured for declared tools")
		}
	}
	owner, err := store.ID()
	if err != nil {
		return nil, err
	}
	round, err := r.Authority.Claim(w, owner, resume)
	if err != nil {
		return nil, err
	}
	current := &run{runtime: r, work: w, policy: p, round: round}
	effects, err := w.Control.Effects(round.ID)
	initialCount := len(effects)
	settled := false
	defer func() {
		if settled || err == nil {
			return
		}
		if current.modelEffect != nil {
			_ = w.Control.UnknownEffect(current.modelEffect.ID, "model transport stopped without durable terminal result")
		}
		after, readErr := w.Control.Effects(round.ID)
		if resume && readErr == nil && len(after) == initialCount {
			_ = w.Control.PauseRound(round.ID, "local continuation failure before a new dispatch", round.Checkpoint)
			return
		}
		rejected, rejectErr := w.Control.RejectIfUndispatched(round.ID)
		if rejectErr != nil || !rejected {
			_ = w.Control.PauseRound(round.ID, "Round stopped; inspect durable effects before any continuation", nil)
		} else if errors.Is(err, rpc.ErrTransport) {
			// Only a durable rejection proves no model/tool dispatch occurred.
			// Never echo worker error payloads, which may contain credentials.
			err = errors.New("worker failed before model/tool dispatch; input remains pending. Check Harness configuration and limits")
		}
	}()
	if err != nil {
		return nil, err
	}
	for _, effect := range effects {
		if effect.Kind == "model" {
			current.turnNumber++
		}
	}
	visible, err := surface(w)
	if err != nil {
		return nil, err
	}
	facts, err := w.Events.Events(0)
	if err != nil {
		return nil, err
	}
	captured := []store.Event{}
	for _, fact := range facts {
		if fact.Seq <= round.InputSeq {
			captured = append(captured, fact)
		}
	}
	var plan Object
	if resume {
		plan = object(round.Checkpoint["plan"])
	} else {
		err = p.Call(ctx, "policy.start", Object{"facts": captured, "surface": visible, "model_semantics": w.Definition.Model.Definition, "timestamp": time.Now().UnixMilli()}, &plan)
	}
	if err != nil {
		return nil, err
	}
	if plan == nil {
		return nil, errors.New("policy did not supply a plan")
	}
	selected, err := r.bindModel(object(plan["model"]))
	if err != nil {
		return nil, err
	}

	seconds, err := number(plan["timeout"])
	if err != nil || seconds <= 0 || seconds > float64((1<<63-1)/int64(time.Second)-1) || math.IsNaN(seconds) || math.IsInf(seconds, 0) {
		return nil, errors.New("policy timeout must be positive and fit a duration")
	}
	maxTurns, err := number(plan["max_turns"])
	if err != nil || maxTurns < 1 || math.IsNaN(maxTurns) || math.IsInf(maxTurns, 0) || maxTurns != float64(int(maxTurns)) {
		return nil, errors.New("policy max_turns must be a positive integer")
	}
	options := object(plan["options"])
	if options == nil {
		options = Object{}
	}
	messages, err := model.Run(ctx, r.ModelCommand, model.Request{Context: object(plan["context"]), Model: selected, Options: options, APIKey: r.APIKey, Tools: p.NativeTools(), MaxTurns: int(maxTurns), Timeout: time.Duration(seconds * float64(time.Second))}, model.Callbacks{Event: current.event, Tool: current.tool, Continue: current.continueTurn, Prepare: current.prepareTurn})
	if err != nil {
		return nil, err
	}
	if current.modelEffect != nil {
		return nil, store.ErrUnknownEffect
	}
	reference, err := artifact(w, messages)
	if err != nil {
		return nil, err
	}
	var assistant Object
	for _, m := range messages {
		if m["role"] == "assistant" {
			assistant = m
		}
	}
	if assistant == nil {
		return nil, errors.New("model returned no assistant result")
	}
	switch assistant["stopReason"] {
	case "error", "aborted", "length", "pending", "deferred":
		return nil, errors.New("model did not provide a complete result; retained for inspection")
	}
	if current.lastTurn != nil {
		more, err := current.finalContinuation(ctx)
		if err != nil {
			return nil, err
		}
		if more {
			update, err := current.prepareTurn(ctx, current.lastTurn)
			if err != nil {
				return nil, err
			}
			next := copyObject(plan)
			next["context"] = current.lastTurn["context"]
			next["model"] = current.lastRequest["model"]
			next["options"] = copyObject(object(current.lastRequest["options"]))
			for _, key := range []string{"context", "model"} {
				if value, ok := update[key]; ok {
					next[key] = value
				}
			}
			// Host transport headers may be reattached for immediate Pi dispatch,
			// but never enter the durable continuation checkpoint.
			if native := object(next["model"]); native != nil {
				saved := copyObject(native)
				delete(saved, "headers")
				next["model"] = saved
			}
			if thinking, ok := update["thinkingLevel"]; ok {
				options := object(next["options"])
				if thinking == "off" {
					delete(options, "reasoning")
				} else {
					options["reasoning"] = thinking
				}
			}
			if err = w.Control.PauseRound(round.ID, "confirmed model turn budget boundary", Object{"plan": next}); err != nil {
				return nil, err
			}
			settled = true
			return nil, errors.New("policy requires continuation; explicit resume is available")
		}
	}
	revision, err := w.Snapshot("Round " + round.ID)
	if err != nil {
		return nil, err
	}
	if err = w.Control.FinishRound(round.ID, revision); err != nil {
		return nil, err
	}
	settled = true
	return Object{"round_id": round.ID, "state": "completed", "revision": revision, "messages": reference}, nil
}
func (c *run) continueTurn(ctx context.Context, turn Object) (bool, error) {
	var answer bool
	err := c.policy.Call(ctx, "policy.continue", Object{"turn": turn}, &answer)
	if err == nil {
		c.mu.Lock()
		c.continueDecision = &answer
		c.mu.Unlock()
	}
	return answer, err
}
func (c *run) finalContinuation(ctx context.Context) (bool, error) {
	c.mu.Lock()
	decision := c.continueDecision
	c.mu.Unlock()
	if decision != nil {
		return *decision, nil
	}
	return c.continueTurn(ctx, c.lastTurn)
}
func (c *run) prepareTurn(ctx context.Context, turn Object) (Object, error) {
	var update Object
	err := c.policy.Call(ctx, "policy.prepare", Object{"turn": turn}, &update)
	if err != nil {
		return nil, err
	}
	if update != nil && update["model"] != nil {
		update["model"], err = c.runtime.bindModel(object(update["model"]))
	}
	return update, err
}
