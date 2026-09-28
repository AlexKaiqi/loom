package store

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
)

type Allocation struct {
	ID           string `json:"allocation_id"`
	EffectID     string `json:"effect_id"`
	Target       string `json:"target"`
	Binding      Object `json:"binding"`
	SandboxID    string `json:"sandbox_id,omitempty"`
	ExecutionID  string `json:"execution_id,omitempty"`
	ReleaseState string `json:"release_state"`
}

func (c *Control) Allocations(round string) ([]Allocation, error) {
	db, err := OpenDB(c.Path)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	rows, err := db.Query("SELECT a.id,a.effect_id,a.target,a.binding,COALESCE(a.sandbox_id,''),COALESCE(a.execution_id,''),a.release_state FROM allocations a JOIN effects e ON e.id=a.effect_id WHERE e.round_id=? ORDER BY a.rowid", round)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Allocation{}
	for rows.Next() {
		var a Allocation
		var raw string
		if err = rows.Scan(&a.ID, &a.EffectID, &a.Target, &raw, &a.SandboxID, &a.ExecutionID, &a.ReleaseState); err != nil {
			return nil, err
		}
		if err = json.Unmarshal([]byte(raw), &a.Binding); err != nil {
			return nil, err
		}
		out = append(out, a)
	}
	return out, rows.Err()
}
func (c *Control) ObserveAllocation(id, kind string, body Object, nativeID string) error {
	raw, err := Canonical(body)
	if err != nil {
		return err
	}
	return Immediate(c.Path, func(db *sql.Conn) error {
		var effect, old string
		if err := db.QueryRowContext(context.Background(), "SELECT effect_id,COALESCE(sandbox_id,'') FROM allocations WHERE id=?", id).Scan(&effect, &old); err != nil {
			return err
		}
		if nativeID != "" && old != "" && nativeID != old {
			return errors.New("allocation native identity changed")
		}
		if nativeID != "" {
			if _, err := db.ExecContext(context.Background(), "UPDATE allocations SET sandbox_id=? WHERE id=?", nativeID, id); err != nil {
				return err
			}
		}
		_, err := db.ExecContext(context.Background(), "INSERT INTO effect_observations(effect_id,kind,body) VALUES(?,?,?)", effect, kind, raw)
		return err
	})
}

func (c *Control) CreateAllocation(round, id, effect, target, binding string) error {
	return Immediate(c.Path, func(db *sql.Conn) error {
		if err := c.Guard(db, round); err != nil {
			return err
		}
		result, err := db.ExecContext(context.Background(), "INSERT INTO allocations(id,effect_id,target,binding,release_state) SELECT ?,?,?,?,'pending' WHERE EXISTS(SELECT 1 FROM effects WHERE id=? AND round_id=?)", id, effect, target, binding, effect, round)
		if err != nil {
			return err
		}
		n, err := result.RowsAffected()
		if err != nil {
			return err
		}
		if n != 1 {
			return errors.New("allocation effect outside owned round")
		}
		return nil
	})
}
func (c *Control) CheckpointAllocation(round, id, sandboxID, executionID, body string) error {
	return Immediate(c.Path, func(db *sql.Conn) error {
		if err := c.Guard(db, round); err != nil {
			return err
		}
		result, err := db.ExecContext(context.Background(), "UPDATE allocations SET sandbox_id=COALESCE(NULLIF(?,''),sandbox_id),execution_id=COALESCE(NULLIF(?,''),execution_id),observation=? WHERE id=? AND (COALESCE(sandbox_id,'')='' OR ?='' OR sandbox_id=?) AND effect_id IN (SELECT id FROM effects WHERE round_id=?)", sandboxID, executionID, body, id, sandboxID, sandboxID, round)
		if err != nil {
			return err
		}
		n, err := result.RowsAffected()
		if err != nil {
			return err
		}
		if n != 1 {
			return errors.New("allocation identity changed")
		}
		return nil
	})
}
