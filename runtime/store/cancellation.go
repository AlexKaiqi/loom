package store

import (
	"context"
	"database/sql"
	"errors"
)

func (c *Control) RequestCancellation(id string) error {
	return Immediate(c.Path, func(db *sql.Conn) error {
		ctx := context.Background()
		var round, state string
		if err := db.QueryRowContext(ctx, "SELECT round_id,cancellation FROM effects WHERE id=?", id).Scan(&round, &state); err != nil {
			return err
		}
		if err := c.Guard(db, round); err != nil {
			return err
		}
		if state == "stop_confirmed" {
			return nil
		}
		if _, err := db.ExecContext(ctx, "INSERT INTO effect_observations(effect_id,kind,body) VALUES(?,'cancellation_requested','{}')", id); err != nil {
			return err
		}
		return requireOne(db.ExecContext(ctx, "UPDATE effects SET cancellation='requested' WHERE id=?", id))
	})
}

// ObserveCancellation cannot settle execution or content delivery. Even a
// confirmed stop leaves the original unknown operation unknown.
func (c *Control) ObserveCancellation(id string, confirmed bool, observation Object) error {
	if observation == nil {
		return errors.New("native cancellation observation required")
	}
	body, err := Canonical(observation)
	if err != nil {
		return err
	}
	state := "unknown"
	if confirmed {
		state = "stop_confirmed"
	}
	return Immediate(c.Path, func(db *sql.Conn) error {
		ctx := context.Background()
		if err := requireOne(db.ExecContext(ctx, "UPDATE effects SET cancellation=CASE WHEN cancellation='stop_confirmed' THEN cancellation ELSE ? END WHERE id=? AND cancellation!='none'", state, id)); err != nil {
			return err
		}
		_, err := db.ExecContext(ctx, "INSERT INTO effect_observations(effect_id,kind,body) VALUES(?,'cancellation_observed',?)", id, body)
		return err
	})
}

func (c *Control) ObserveEffect(id, kind string, observation Object) error {
	if observation == nil || kind == "" {
		return errors.New("adapter observation required")
	}
	body, err := Canonical(observation)
	if err != nil {
		return err
	}
	return Immediate(c.Path, func(db *sql.Conn) error {
		_, err := db.ExecContext(context.Background(), "INSERT INTO effect_observations(effect_id,kind,body) VALUES(?,?,?)", id, kind, body)
		return err
	})
}
