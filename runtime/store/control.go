package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
)

type Round struct {
	ID         string `json:"id"`
	Owner      string `json:"owner"`
	InputSeq   int64  `json:"input_seq"`
	State      string `json:"state"`
	Revision   string `json:"revision,omitempty"`
	Error      string `json:"error,omitempty"`
	Checkpoint Object `json:"checkpoint,omitempty"`
	Created    string `json:"created"`
}
type Effect struct {
	ID      string `json:"id"`
	RoundID string `json:"round_id"`
	Key     string `json:"key"`
	Kind    string `json:"kind"`
	Request Object `json:"request"`
	Digest  string `json:"digest"`
	Status  string `json:"status"`
	Receipt Object `json:"receipt"`
	Result  Object `json:"result"`
	Error   string `json:"error,omitempty"`
}
type Control struct{ Path string }

func scanRound(row scanner) (Round, error) {
	var r Round
	var rev, msg, cp sql.NullString
	err := row.Scan(&r.ID, &r.Owner, &r.InputSeq, &r.State, &rev, &msg, &cp, &r.Created)
	if err != nil {
		return r, err
	}
	r.Revision, r.Error = rev.String, msg.String
	if cp.Valid {
		r.Checkpoint, err = DecodeObject(cp.String)
	}
	return r, err
}
func scanEffect(row scanner) (Effect, error) {
	var e Effect
	var request string
	var receipt, result, msg sql.NullString
	err := row.Scan(&e.ID, &e.RoundID, &e.Key, &e.Kind, &request, &e.Digest, &e.Status, &receipt, &result, &msg)
	if err != nil {
		return e, err
	}
	e.Error = msg.String
	e.Request, err = DecodeObject(request)
	if err != nil {
		return e, err
	}
	if receipt.Valid {
		e.Receipt, err = DecodeObject(receipt.String)
		if err != nil {
			return e, err
		}
	}
	if result.Valid {
		e.Result, err = DecodeObject(result.String)
	}
	return e, err
}
func (c *Control) BeginRound(owner string) (Round, error) {
	var r Round
	if owner == "" {
		return r, errors.New("owner required")
	}
	err := Immediate(c.Path, func(db *sql.Conn) error {
		ctx := context.Background()
		var n int
		if err := db.QueryRowContext(ctx, "SELECT count(*) FROM rounds WHERE state IN('running','paused')").Scan(&n); err != nil {
			return err
		}
		if n != 0 {
			return fmt.Errorf("%w: active or paused Round exists", ErrConflict)
		}
		var boundary sql.NullInt64
		if err := db.QueryRowContext(ctx, "SELECT MAX(seq) FROM pending").Scan(&boundary); err != nil {
			return err
		}
		if !boundary.Valid {
			return fmt.Errorf("%w: no pending responsibility", ErrConflict)
		}
		id, err := ID()
		if err != nil {
			return err
		}
		if _, err = db.ExecContext(ctx, "INSERT INTO rounds(id,owner,input_seq,state) VALUES(?,?,?,'running')", id, owner, boundary.Int64); err != nil {
			return err
		}
		r, err = scanRound(db.QueryRowContext(ctx, "SELECT * FROM rounds WHERE id=?", id))
		return err
	})
	return r, err
}
func (c *Control) PrepareEffect(roundID, key, kind string, request Object) (Effect, error) {
	var e Effect
	if key == "" || kind == "" || request == nil {
		return e, errors.New("effect key, kind and request required")
	}
	fingerprint, err := Digest(Object{"kind": kind, "request": request})
	if err != nil {
		return e, err
	}
	body, err := Canonical(request)
	if err != nil {
		return e, err
	}
	err = Immediate(c.Path, func(db *sql.Conn) error {
		ctx := context.Background()
		old, err := scanEffect(db.QueryRowContext(ctx, "SELECT * FROM effects WHERE round_id=? AND key=?", roundID, key))
		if err == nil {
			if old.Digest != fingerprint {
				return fmt.Errorf("%w: effect identity reused with different request", ErrConflict)
			}
			if old.Status != "completed" {
				return ErrUnknownEffect
			}
			e = old
			return nil
		}
		if !errors.Is(err, sql.ErrNoRows) {
			return err
		}
		var state string
		if err = db.QueryRowContext(ctx, "SELECT state FROM rounds WHERE id=?", roundID).Scan(&state); err != nil || state != "running" {
			return fmt.Errorf("%w: Round not running", ErrConflict)
		}
		id, err := ID()
		if err != nil {
			return err
		}
		if _, err = db.ExecContext(ctx, "INSERT INTO effects(id,round_id,key,kind,request,digest,status) VALUES(?,?,?,?,?,?,'intent')", id, roundID, key, kind, body, fingerprint); err != nil {
			return err
		}
		e, err = scanEffect(db.QueryRowContext(ctx, "SELECT * FROM effects WHERE id=?", id))
		return err
	})
	return e, err
}
func (c *Control) CheckpointEffect(id string, receipt Object) error {
	return c.objectUpdate("UPDATE effects SET receipt=? WHERE id=? AND status!='completed'", id, receipt)
}
func (c *Control) CompleteEffect(id string, result Object) error {
	return c.objectUpdate("UPDATE effects SET status='completed',result=? WHERE id=? AND status!='completed'", id, result)
}
func (c *Control) objectUpdate(query, id string, value Object) error {
	if value == nil {
		return errors.New("object required")
	}
	body, err := Canonical(value)
	if err != nil {
		return err
	}
	return Immediate(c.Path, func(db *sql.Conn) error { return requireOne(db.ExecContext(context.Background(), query, body, id)) })
}
func (c *Control) UnknownEffect(id, message string) error {
	return Immediate(c.Path, func(db *sql.Conn) error {
		return requireOne(db.ExecContext(context.Background(), "UPDATE effects SET status='unknown',error=? WHERE id=? AND status!='completed'", message, id))
	})
}
func unresolved(db *sql.Conn, roundID string) (bool, error) {
	var n int
	err := db.QueryRowContext(context.Background(), "SELECT count(*) FROM effects WHERE round_id=? AND status!='completed'", roundID).Scan(&n)
	return n > 0, err
}
func (c *Control) FinishRound(id, revision string) error {
	return Immediate(c.Path, func(db *sql.Conn) error {
		ctx := context.Background()
		r, err := scanRound(db.QueryRowContext(ctx, "SELECT * FROM rounds WHERE id=? AND state='running'", id))
		if err != nil {
			return fmt.Errorf("%w: Round not running", ErrConflict)
		}
		pending, err := unresolved(db, id)
		if err != nil {
			return err
		}
		if pending {
			return ErrUnknownEffect
		}
		if err = requireOne(db.ExecContext(ctx, "UPDATE rounds SET state='completed',revision=? WHERE id=?", revision, id)); err != nil {
			return err
		}
		_, err = db.ExecContext(ctx, "DELETE FROM pending WHERE seq<=?", r.InputSeq)
		return err
	})
}
func (c *Control) PauseRound(id, message string, checkpoint Object) error {
	var value any
	if checkpoint != nil {
		body, err := Canonical(checkpoint)
		if err != nil {
			return err
		}
		value = body
	}
	return Immediate(c.Path, func(db *sql.Conn) error {
		if checkpoint != nil {
			unknown, err := unresolved(db, id)
			if err != nil {
				return err
			}
			if unknown {
				return ErrUnknownEffect
			}
		}
		return requireOne(db.ExecContext(context.Background(), "UPDATE rounds SET state='paused',error=?,checkpoint=? WHERE id=? AND state='running'", message, value, id))
	})
}
func (c *Control) ResumeRound(owner string) (Round, error) {
	var r Round
	if owner == "" {
		return r, errors.New("owner required")
	}
	err := Immediate(c.Path, func(db *sql.Conn) error {
		ctx := context.Background()
		var err error
		r, err = scanRound(db.QueryRowContext(ctx, "SELECT * FROM rounds WHERE state IN('running','paused')"))
		if err != nil || r.State != "paused" || r.Checkpoint == nil {
			return fmt.Errorf("%w: no confirmed paused continuation; takeover forbidden", ErrConflict)
		}
		unknown, err := unresolved(db, r.ID)
		if err != nil {
			return err
		}
		if unknown {
			return ErrUnknownEffect
		}
		if err = requireOne(db.ExecContext(ctx, "UPDATE rounds SET state='running',owner=?,error=NULL,checkpoint=NULL WHERE id=? AND state='paused'", owner, r.ID)); err != nil {
			return err
		}
		r.Owner, r.State, r.Error = owner, "running", ""
		return nil
	})
	return r, err
}
func (c *Control) RejectIfUndispatched(id string) (bool, error) {
	var rejected bool
	err := Immediate(c.Path, func(db *sql.Conn) error {
		ctx := context.Background()
		var n int
		if err := db.QueryRowContext(ctx, "SELECT count(*) FROM effects WHERE round_id=?", id).Scan(&n); err != nil {
			return err
		}
		if n > 0 {
			return nil
		}
		res, err := db.ExecContext(ctx, "UPDATE rounds SET state='rejected',error='local failure before dispatch' WHERE id=? AND state='running'", id)
		if err != nil {
			return err
		}
		count, err := res.RowsAffected()
		rejected = count == 1
		return err
	})
	return rejected, err
}
func (c *Control) Rounds() ([]Round, error) {
	db, err := OpenDB(c.Path)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	rows, err := db.Query("SELECT * FROM rounds ORDER BY rowid")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := []Round{}
	for rows.Next() {
		r, err := scanRound(rows)
		if err != nil {
			return nil, err
		}
		result = append(result, r)
	}
	return result, rows.Err()
}
func (c *Control) Effects(roundID string) ([]Effect, error) {
	db, err := OpenDB(c.Path)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	rows, err := db.Query("SELECT * FROM effects WHERE round_id=? ORDER BY rowid", roundID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := []Effect{}
	for rows.Next() {
		e, err := scanEffect(rows)
		if err != nil {
			return nil, err
		}
		result = append(result, e)
	}
	return result, rows.Err()
}
