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
		c.turnNumber++
		effect, err := c.work.Control.PrepareEffect(c.round.ID, fmt.Sprintf("model:%d", c.turnNumber), "model", Object{"request": reference})
		if err != nil {
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
	case "message_end":
		message := object(event["message"])
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
