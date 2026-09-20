package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"path/filepath"
	"strconv"
)

// CommitCandidate verifies the caller's predecessor and complete copy bindings.
// ContentRef is verified against captured content by the controller before this
// transaction. Native continuation fields come only from the current checkpoint.
func (c *Control) CommitCandidate(id, previous, content string, expected []Object) (Object, error) {
	var result Object
	err := Immediate(c.Path, func(db *sql.Conn) error {
		if err := c.Guard(db, id); err != nil {
			return err
		}
		r, err := scanRound(db.QueryRowContext(context.Background(), "SELECT * FROM rounds WHERE id=? AND state='running'", id))
		if err != nil {
			return err
		}
		var latest string
		if err = db.QueryRowContext(context.Background(), "SELECT COALESCE((SELECT id FROM checkpoints ORDER BY rowid DESC LIMIT 1),'')").Scan(&latest); err != nil {
			return err
		}
		if latest != previous {
			return fmt.Errorf("%w: baseline_conflict", ErrConflict)
		}
		unknown, err := unresolved(db, id)
		if err != nil {
			return err
		}
		if unknown {
			return ErrUnknownEffect
		}
		ref, err := c.saveCheckpoint(db, r, Object{"content_ref": content}, "policy_checkpoint")
		if err != nil {
			return err
		}
		raw, err := (Records{Directory: filepath.Join(filepath.Dir(c.Path), "records")}).Get(ref)
		if err != nil {
			return err
		}
		result, err = DecodeObject(string(raw))
		if err != nil {
			return err
		}
		actual, err := Canonical(result["resource_copies"])
		if err != nil {
			return err
		}
		supplied, err := Canonical(expected)
		if err != nil {
			return err
		}
		if actual != supplied {
			return fmt.Errorf("%w: resource copy baseline_conflict", ErrConflict)
		}
		return requireOne(db.ExecContext(context.Background(), "UPDATE rounds SET checkpoint=? WHERE id=?", string(raw), id))
	})
	return result, err
}

// RequestHandoff persists exactly which inputs the strategy is settling. It
// revokes further strategy advancement through the controller, but does not
// claim that execution domains have already been fenced.
func (c *Control) RequestHandoff(id, checkpoint string, inputs []string, intent string) (Object, error) {
	var result Object
	if intent != "wait" && intent != "continue" {
		return nil, errors.New("invalid_request: handoff intent")
	}
	err := Immediate(c.Path, func(db *sql.Conn) error {
		if err := c.Guard(db, id); err != nil {
			return err
		}
		r, err := scanRound(db.QueryRowContext(context.Background(), "SELECT * FROM rounds WHERE id=? AND state='running'", id))
		if err != nil {
			return err
		}
		if r.Checkpoint["checkpoint_id"] != checkpoint || r.Checkpoint["phase"] != "policy_checkpoint" {
			return fmt.Errorf("%w: baseline_conflict", ErrConflict)
		}
		unknown, err := unresolved(db, id)
		if err != nil {
			return err
		}
		if unknown {
			return ErrUnknownEffect
		}
		if intent == "continue" && r.Checkpoint["native_turn"] == nil {
			return errors.New("not_ready: native continuation required")
		}
		seen := map[int64]bool{}
		for _, input := range inputs {
			if len(input) < 2 || input[0] != 'F' {
				return errors.New("invalid_request: input id")
			}
			n, err := strconv.ParseInt(input[1:], 10, 64)
			if err != nil || n < 1 || "F"+strconv.FormatInt(n, 10) != input || seen[n] {
				return errors.New("invalid_request: input id")
			}
			seen[n] = true
			var count int
			if err = db.QueryRowContext(context.Background(), "SELECT count(*) FROM round_inputs WHERE round_id=? AND seq=?", id, n).Scan(&count); err != nil {
				return err
			}
			if count != 1 {
				return errors.New("permission_denied: input not adopted by this Round")
			}
		}
		ref, err := c.saveCheckpoint(db, r, Object{"handled_input_ids": inputs, "handoff_intent": intent}, "handoff_pending")
		if err != nil {
			return err
		}
		raw, err := (Records{Directory: filepath.Join(filepath.Dir(c.Path), "records")}).Get(ref)
		if err != nil {
			return err
		}
		result, err = DecodeObject(string(raw))
		if err != nil {
			return err
		}
		return requireOne(db.ExecContext(context.Background(), "UPDATE rounds SET checkpoint=? WHERE id=?", string(raw), id))
	})
	return result, err
}

// CompleteHandoff is the controller's fencing confirmation, not a Harness API.
// Recovery uses the same function once old domains are actually stopped.
func (c *Control) CompleteHandoff(id string) error {
	return Immediate(c.Path, func(db *sql.Conn) error {
		if err := c.Guard(db, id); err != nil {
			return err
		}
		r, err := scanRound(db.QueryRowContext(context.Background(), "SELECT * FROM rounds WHERE id=? AND state='running'", id))
		if err != nil {
			return err
		}
		return c.completeHandoff(db, r)
	})
}
func (c *Control) completeHandoff(db *sql.Conn, r Round) error {
	if r.Checkpoint["phase"] != "handoff_pending" {
		return errors.New("not_ready: no durable handoff intent")
	}
	unknown, err := unresolved(db, r.ID)
	if err != nil {
		return err
	}
	if unknown {
		return ErrUnknownEffect
	}
	ids, ok := r.Checkpoint["handled_input_ids"].([]any)
	if !ok {
		return errors.New("invalid stored handoff inputs")
	}
	for _, raw := range ids {
		id, ok := raw.(string)
		if !ok || len(id) < 2 {
			return errors.New("invalid stored handoff input")
		}
		seq, err := strconv.ParseInt(id[1:], 10, 64)
		if err != nil {
			return err
		}
		if _, err = db.ExecContext(context.Background(), "DELETE FROM pending WHERE seq=? AND seq IN(SELECT seq FROM round_inputs WHERE round_id=?)", seq, r.ID); err != nil {
			return err
		}
	}
	state := "handed_off"
	if r.Checkpoint["handoff_intent"] == "continue" {
		state = "ready"
	}
	ref, err := c.saveCheckpoint(db, r, Object{}, state)
	if err != nil {
		return err
	}
	body, err := (Records{Directory: filepath.Join(filepath.Dir(c.Path), "records")}).Get(ref)
	if err != nil {
		return err
	}
	return requireOne(db.ExecContext(context.Background(), "UPDATE rounds SET state=?,revision=?,checkpoint=?,error=NULL WHERE id=?", state, r.Checkpoint["content_ref"], string(body), r.ID))
}

func (c *Control) HandoffBasis(id string) (Object, error) {
	db, err := OpenDB(c.Path)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	var previous string
	if err = db.QueryRow("SELECT COALESCE((SELECT id FROM checkpoints ORDER BY rowid DESC LIMIT 1),'')").Scan(&previous); err != nil {
		return nil, err
	}
	rows, err := db.Query("SELECT id,alias,target,generation,content_ref FROM resource_copies ORDER BY id")
	if err != nil {
		return nil, err
	}
	copies := []Object{}
	for rows.Next() {
		var key, alias, target, ref string
		var generation int64
		if err = rows.Scan(&key, &alias, &target, &generation, &ref); err != nil {
			rows.Close()
			return nil, err
		}
		content, err := DecodeObject(ref)
		if err != nil {
			rows.Close()
			return nil, err
		}
		copies = append(copies, Object{"working_copy_id": key, "alias": alias, "target": target, "generation": strconv.FormatInt(generation, 10), "content_ref": content})
	}
	if err = errors.Join(rows.Err(), rows.Close()); err != nil {
		return nil, err
	}
	claimed, err := c.ClaimedInputs(id)
	if err != nil {
		return nil, err
	}
	inputs := []string{}
	for _, seq := range claimed {
		inputs = append(inputs, fmt.Sprintf("F%d", seq))
	}
	return Object{"previous_checkpoint_id": previous, "resource_copies": copies, "claimed_input_ids": inputs}, nil
}
