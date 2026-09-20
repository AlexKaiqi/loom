package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"path/filepath"
)

// Bind is a controller capability, never a value supplied by Harness. A fresh
// epoch is required for every ownership transfer, including the same owner ID.
func (c *Control) Bind(r Round) *Control {
	return &Control{Path: c.Path, RoundID: r.ID, Owner: r.Owner, Epoch: r.Epoch}
}
func (c *Control) Guard(db interface {
	QueryRowContext(context.Context, string, ...any) *sql.Row
}, roundID string) error {
	if c.Owner == "" {
		return nil
	} // host management entry point
	if roundID != c.RoundID {
		return fmt.Errorf("%w: stale_epoch", ErrConflict)
	}
	var n int
	err := db.QueryRowContext(context.Background(), "SELECT count(*) FROM rounds WHERE id=? AND owner=? AND epoch=? AND state='running'", c.RoundID, c.Owner, c.Epoch).Scan(&n)
	if err != nil {
		return err
	}
	if n != 1 {
		return fmt.Errorf("%w: stale_epoch", ErrConflict)
	}
	return nil
}
func (c *Control) Owned(fn func() error) error {
	return Immediate(c.Path, func(db *sql.Conn) error {
		if err := c.Guard(db, c.RoundID); err != nil {
			return err
		}
		return fn()
	})
}

// SaveContinuation fixes a closed native turn while the Round is still running.
// It never discards the previous checkpoint when a later dispatch is uncertain.
func (c *Control) SaveContinuation(id string, data Object) error {
	return c.saveContinuation(id, data, "native_turn")
}

// SaveModelAdvance accepts a Harness's published input. It saves responsibility
// before the model process is started, without claiming any native completion.
func (c *Control) SaveModelAdvance(id string, data Object) error {
	return c.saveContinuation(id, data, "model_ready")
}

func (c *Control) saveContinuation(id string, data Object, phase string) error {
	return Immediate(c.Path, func(db *sql.Conn) error {
		if err := c.Guard(db, id); err != nil {
			return err
		}
		r, err := scanRound(db.QueryRowContext(context.Background(), "SELECT * FROM rounds WHERE id=? AND state='running'", id))
		if err != nil {
			return err
		}
		unknown, err := unresolved(db, id)
		if err != nil {
			return err
		}
		if unknown {
			return ErrUnknownEffect
		}
		ref, err := c.saveCheckpoint(db, r, data, phase)
		if err != nil {
			return err
		}
		raw, err := (Records{Directory: filepath.Join(filepath.Dir(c.Path), "records")}).Get(ref)
		if err != nil {
			return err
		}
		return requireOne(db.ExecContext(context.Background(), "UPDATE rounds SET checkpoint=? WHERE id=?", string(raw), id))
	})
}

// BeginRecovery revokes publication and dispatch before attempting to fence
// processes. It does not turn timeout, crash or successful cancellation into a
// statement that an already attempted operation did not execute.
func (c *Control) BeginRecovery(owner string) (Round, error) {
	var r Round
	if owner == "" {
		return r, errors.New("recovery owner required")
	}
	err := Immediate(c.Path, func(db *sql.Conn) error {
		ctx := context.Background()
		var err error
		r, err = scanRound(db.QueryRowContext(ctx, "SELECT * FROM rounds WHERE state!='handed_off'"))
		if err != nil {
			return err
		}
		if err = requireOne(db.ExecContext(ctx, "UPDATE rounds SET state='recovering',owner=?,epoch=epoch+1 WHERE id=? AND owner=? AND epoch=?", owner, r.ID, r.Owner, r.Epoch)); err != nil {
			return err
		}
		r.Owner, r.State = owner, "recovering"
		r.Epoch++
		return nil
	})
	return r, err
}

// EndRecovery may be called only after the deployment's fencing proof has been
// saved. Prepared permits are proven unused; attempted permits remain unknown.
func (c *Control) EndRecovery(r Round) error {
	return Immediate(c.Path, func(db *sql.Conn) error {
		ctx := context.Background()
		var state, owner string
		var epoch int64
		if err := db.QueryRowContext(ctx, "SELECT state,owner,epoch FROM rounds WHERE id=?", r.ID).Scan(&state, &owner, &epoch); err != nil {
			return err
		}
		if state != "recovering" || owner != r.Owner || epoch != r.Epoch {
			return fmt.Errorf("%w: stale_epoch", ErrConflict)
		}
		if r.Checkpoint["phase"] == "handoff_pending" {
			return c.completeHandoff(db, r)
		}
		if _, err := db.ExecContext(ctx, "INSERT INTO effect_observations(effect_id,kind,body) SELECT id,'dispatch_permit_unused','{}' FROM effects WHERE round_id=? AND dispatch_state='prepared' AND resolution='unresolved'", r.ID); err != nil {
			return err
		}
		if _, err := db.ExecContext(ctx, "UPDATE effects SET status='completed',resolution='confirmed_not_executed',content_delivery='not_required' WHERE round_id=? AND dispatch_state='prepared' AND resolution='unresolved'", r.ID); err != nil {
			return err
		}
		if _, err := db.ExecContext(ctx, "UPDATE allocations SET release_state='confirmed' WHERE COALESCE(sandbox_id,'')='' AND effect_id IN(SELECT id FROM effects WHERE round_id=? AND dispatch_state='prepared' AND resolution='confirmed_not_executed')", r.ID); err != nil {
			return err
		}
		unknown, err := unresolved(db, r.ID)
		if err != nil {
			return err
		}
		var attempts int
		if err = db.QueryRowContext(ctx, "SELECT count(*) FROM effects WHERE round_id=? AND dispatch_state='attempted'", r.ID).Scan(&attempts); err != nil {
			return err
		}
		next, message := "blocked", "execution fenced; original effects or native continuation need reconciliation"
		if !unknown && (attempts == 0 || checkpointCoversAttempts(r.Checkpoint, attempts)) {
			next, message = "ready", "execution fenced; confirmed continuation available"
		}
		return requireOne(db.ExecContext(ctx, "UPDATE rounds SET state=?,error=? WHERE id=? AND owner=? AND epoch=? AND state='recovering'", next, message, r.ID, r.Owner, r.Epoch))
	})
}

func checkpointCoversAttempts(cp Object, count int) bool {
	effects, ok := cp["effects"].([]any)
	if !ok {
		return false
	}
	saved := 0
	for _, raw := range effects {
		e, ok := raw.(map[string]any)
		if !ok {
			return false
		}
		if e["dispatch_state"] == "attempted" {
			if e["resolution"] != "native_result" || e["status"] != "completed" {
				return false
			}
			saved++
		}
	}
	return saved == count && cp["native_turn"] != nil
}

func (c *Control) ReturnReady(id, reason string) error {
	return Immediate(c.Path, func(db *sql.Conn) error {
		if err := c.Guard(db, id); err != nil {
			return err
		}
		unknown, err := unresolved(db, id)
		if err != nil {
			return err
		}
		if unknown {
			return ErrUnknownEffect
		}
		return requireOne(db.ExecContext(context.Background(), "UPDATE rounds SET state='ready',error=? WHERE id=? AND state='running' AND checkpoint IS NOT NULL", reason, id))
	})
}
