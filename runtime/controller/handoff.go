package controller

import (
	"context"
	"errors"
)

func (c *run) handoffRequested() bool {
	c.api.mu.Lock()
	defer c.api.mu.Unlock()
	return c.api.handoff != nil
}
func (c *run) handoffBasis() (Object, error) {
	basis, err := c.work.Control.HandoffBasis(c.round.ID)
	if err != nil {
		return nil, err
	}
	version, err := c.work.CurrentContent()
	if err != nil {
		return nil, err
	}
	basis["content_version"] = version
	return basis, nil
}
func (c *run) finish(ctx context.Context) (Object, error) {
	if !c.handoffRequested() {
		if err := c.work.Control.Owned(func() error { _, err := c.work.Snapshot("handoff sources"); return err }); err != nil {
			return nil, err
		}
		basis, err := c.handoffBasis()
		if err != nil {
			return nil, err
		}
		var accepted Object
		if err = c.policy.Call(ctx, "policy.finish", basis, &accepted); err != nil {
			return nil, err
		}
	}
	c.api.mu.Lock()
	cp := c.api.handoff
	c.api.mu.Unlock()
	if cp == nil {
		return nil, errors.New("not_ready: Harness did not request round.handoff")
	}
	c.policy.Close()
	if err := c.releaseAllocations(ctx); err != nil {
		return nil, err
	}
	if err := c.domain.close(); err != nil {
		return nil, err
	}
	if err := c.work.Control.CompleteHandoff(c.round.ID); err != nil {
		return nil, err
	}
	rounds, err := c.work.Control.Rounds()
	if err != nil {
		return nil, err
	}
	for _, r := range rounds {
		if r.ID == c.round.ID {
			cp = r.Checkpoint
		}
	}
	state := "handed_off"
	if cp["handoff_intent"] == "continue" {
		state = "ready"
	}
	return Object{"round_id": c.round.ID, "state": state, "revision": cp["content_ref"], "checkpoint_id": cp["checkpoint_id"]}, nil
}
