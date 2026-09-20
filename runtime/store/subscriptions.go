package store

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"slices"
)

type Subscription struct {
	ID           string   `json:"id"`
	SourceWorkID string   `json:"source_work_id"`
	Kinds        []string `json:"kinds"`
	Start        int64    `json:"start,string"`
	Cursor       int64    `json:"cursor,string"`
	Active       bool     `json:"active"`
}

func (e *Events) Subscribe(id, source string, kinds []string, start int64) error {
	if id == "" || source == "" || start < 0 || len(kinds) == 0 {
		return errors.New("subscription requires identity, source, kinds and start")
	}
	kinds = append([]string(nil), kinds...)
	slices.Sort(kinds)
	for i, kind := range kinds {
		if kind == "" || (i > 0 && kinds[i-1] == kind) {
			return errors.New("empty or duplicate subscription kind")
		}
	}
	body, _ := json.Marshal(kinds)
	return Immediate(e.Path, func(db *sql.Conn) error {
		if e.Control != nil {
			if err := e.Control.Guard(db, e.Control.RoundID); err != nil {
				return err
			}
		}
		var oldSource, oldKinds string
		var oldStart int64
		err := db.QueryRowContext(context.Background(), "SELECT source_work_id,kinds,start_seq FROM subscriptions WHERE id=?", id).Scan(&oldSource, &oldKinds, &oldStart)
		if err == nil {
			if oldSource != source || oldKinds != string(body) || oldStart != start {
				return fmt.Errorf("%w: changed subscription identity", ErrConflict)
			}
			return nil
		}
		if !errors.Is(err, sql.ErrNoRows) {
			return err
		}
		_, err = db.ExecContext(context.Background(), "INSERT INTO subscriptions VALUES(?,?,?,?,?,1)", id, source, string(body), start, start)
		return err
	})
}
func (e *Events) RemoveSubscription(id string) error {
	return Immediate(e.Path, func(db *sql.Conn) error {
		if e.Control != nil {
			if err := e.Control.Guard(db, e.Control.RoundID); err != nil {
				return err
			}
		}
		return requireOne(db.ExecContext(context.Background(), "UPDATE subscriptions SET active=0 WHERE id=?", id))
	})
}
func (e *Events) Subscriptions() ([]Subscription, error) {
	db, err := OpenDB(e.Path)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	rows, err := db.Query("SELECT id,source_work_id,kinds,start_seq,cursor,active FROM subscriptions ORDER BY id")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Subscription{}
	for rows.Next() {
		var s Subscription
		var kinds string
		if err = rows.Scan(&s.ID, &s.SourceWorkID, &kinds, &s.Start, &s.Cursor, &s.Active); err != nil {
			return nil, err
		}
		if err = json.Unmarshal([]byte(kinds), &s.Kinds); err != nil {
			return nil, err
		}
		out = append(out, s)
	}
	return out, rows.Err()
}

// ConfirmDelivery advances only after the target input exists. A crash after
// Admit but before this transaction is handled by resending the same source
// fact identity; it creates neither a second input nor a second business action.
func (e *Events) ConfirmDelivery(id string, expected, sourceSeq int64, sourceFact string, inputSeq int64) error {
	return Immediate(e.Path, func(db *sql.Conn) error {
		if e.Control != nil {
			if err := e.Control.Guard(db, e.Control.RoundID); err != nil {
				return err
			}
		}
		ctx := context.Background()
		var current int64
		if err := db.QueryRowContext(ctx, "SELECT cursor FROM subscriptions WHERE id=? AND active=1", id).Scan(&current); err != nil {
			return err
		}
		if current >= sourceSeq {
			return nil
		}
		if current != expected || sourceSeq <= expected {
			return fmt.Errorf("%w: subscription scan predecessor changed", ErrConflict)
		}
		if inputSeq != 0 {
			if _, err := db.ExecContext(ctx, "INSERT INTO deliveries VALUES(?,?,?,?)", id, sourceSeq, sourceFact, inputSeq); err != nil {
				return err
			}
		}
		return requireOne(db.ExecContext(ctx, "UPDATE subscriptions SET cursor=? WHERE id=? AND cursor=? AND active=1", sourceSeq, id, expected))
	})
}
