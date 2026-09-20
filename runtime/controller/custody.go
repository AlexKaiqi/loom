package controller

import (
	"errors"
	"fmt"
	"loom/runtime/store"
)

func (c *run) event(event Object) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	reference, err := artifact(c.work, event)
	if err != nil {
		return err
	}
	switch event["type"] {
	case "model_request":
		if c.modelEffect != nil {
			return store.ErrUnknownEffect
		}
		prior, e := c.work.Control.Effects(c.round.ID)
		if e != nil {
			return e
		}
		for _, effect := range prior {
			if effect.Resolution == "unresolved" || effect.ContentDelivery == "pending" || effect.ContentDelivery == "unknown" || effect.ContentDelivery == "failed" {
				return store.ErrUnknownEffect
			}
		}
		c.turnNumber++
		effect, err := c.work.Control.PrepareEffect(c.round.ID, fmt.Sprintf("model:%d", c.turnNumber), "model", Object{"request": reference, "projection_ref": c.projectionRef})
		if err != nil {
			return err
		}
		if err = c.work.Control.AttemptEffect(effect.ID, c.round.Owner); err != nil {
			return err
		}
		c.modelEffect = &effect
		c.lastRequest = event
	case "turn_checkpoint":
		c.continueDecision = nil
		c.lastTurn = object(event["turn"])
		if c.lastTurn == nil {
			return errors.New("invalid native turn checkpoint")
		}
		invalidContinuation := false
		switch object(c.lastTurn["message"])["stopReason"] {
		case "error", "aborted", "length", "pending", "deferred":
			invalidContinuation = true
		}
		if c.basePlan != nil && !invalidContinuation {
			next := copyObject(c.basePlan)
			c.copyProjectionMetadata(next)
			next["repair_attempts"] = c.repairAttempts
			if c.repairMode {
				next["execution_mode"] = "context_repair"
			} else {
				delete(next, "execution_mode")
			}
			// Save the native closed exchange itself. Re-rendering after recovery
			// happens through the selected strategy before the next dispatch.
			continuation := copyObject(object(c.lastTurn["context"]))
			// The original native turn retains its actual feedback. A future
			// request starts from the raw strategy prompt and forms fresh feedback.
			continuation["systemPrompt"] = c.projectedContext["systemPrompt"]
			next["context"] = continuation
			if request := object(c.lastRequest["model"]); request != nil {
				native := copyObject(request)
				delete(native, "headers")
				delete(native, "baseUrl")
				next["model"] = native
			}
			next["options"] = c.lastRequest["options"]
			version := ""
			err = c.work.Control.Owned(func() error { var e error; version, e = c.work.Snapshot("native turn checkpoint"); return e })
			if err != nil {
				return err
			}
			if err = c.work.Control.SaveContinuation(c.round.ID, Object{"plan": next, "native_turn": c.lastTurn, "projection_ref": c.projectionRef, "content_ref": version}); err != nil {
				return err
			}
		}
	case "message_end":
		message := object(event["message"])
		kind := "model.message"
		if message["role"] == "toolResult" {
			kind = "tool.result"
		}
		if message["role"] == "assistant" || message["role"] == "toolResult" {
			key := fmt.Sprintf("message:%s:%d:%v:%v", c.round.ID, c.turnNumber, message["role"], message["toolCallId"])
			payload := Object{"message": message, "status": "native_result", "round_id": c.round.ID}
			if kind == "tool.result" {
				details := object(message["details"])
				if details != nil {
					payload["exit_code"] = details["exit_code"]
					if message["isError"] == true {
						payload["error"] = Object{"stderr": details["stderr"], "stdout": details["stdout"], "output_stream": details["output_stream"]}
					}
				}
			}
			if _, err = c.work.Events.Append("model-adapter", key, kind, payload); err != nil {
				return err
			}
		}

		if message["role"] == "assistant" {
			if c.modelEffect == nil {
				return errors.New("assistant result without model intent")
			}
			if err = c.work.Control.CompleteEffect(c.modelEffect.ID, Object{"artifact": reference, "stopReason": message["stopReason"]}); err != nil {
				return err
			}
			c.modelEffect = nil
		}
	}
	return nil
}
