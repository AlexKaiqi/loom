package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
)

type Event struct {
	Seq       int64  `json:"seq"`
	Source    string `json:"source"`
	RequestID string `json:"request_id"`
	Kind      string `json:"kind"`
	Payload   Object `json:"payload"`
	Digest    string `json:"digest"`
	Created   string `json:"created"`
}
type Events struct{ Path string }

func scanEvent(row scanner) (Event, error) {
	var e Event
	var payload string
	err := row.Scan(&e.Seq, &e.Source, &e.RequestID, &e.Kind, &payload, &e.Digest, &e.Created)
	if err != nil {
		return e, err
	}
	e.Payload, err = DecodeObject(payload)
	return e, err
}
func (e *Events) Admit(source, requestID, kind string, payload Object) (Event, error) {
	var result Event
	if source == "" || requestID == "" || kind == "" || payload == nil {
		return result, errors.New("source, request ID, kind and object payload required")
	}
	fingerprint, err := Digest(Object{"kind": kind, "payload": payload})
	if err != nil {
		return result, err
	}
	body, err := Canonical(payload)
	if err != nil {
		return result, err
	}
	err = Immediate(e.Path, func(c *sql.Conn) error {
		ctx := context.Background()
		var oldDigest string
		var seq int64
		err := c.QueryRowContext(ctx, "SELECT digest,seq FROM admissions WHERE source=? AND request_id=?", source, requestID).Scan(&oldDigest, &seq)
		if err == nil {
			if oldDigest != fingerprint {
				return fmt.Errorf("%w: request identity already has different content", ErrConflict)
			}
			result, err = scanEvent(c.QueryRowContext(ctx, "SELECT * FROM events WHERE seq=?", seq))
			return err
		}
		if !errors.Is(err, sql.ErrNoRows) {
			return err
		}
		res, err := c.ExecContext(ctx, "INSERT INTO events(source,request_id,kind,payload,digest) VALUES(?,?,?,?,?)", source, requestID, kind, body, fingerprint)
		if err != nil {
			return err
		}
		seq, err = res.LastInsertId()
		if err != nil {
			return err
		}
		if _, err = c.ExecContext(ctx, "INSERT INTO admissions VALUES(?,?,?,?)", source, requestID, fingerprint, seq); err != nil {
			return err
		}
		if _, err = c.ExecContext(ctx, "INSERT INTO pending VALUES(?)", seq); err != nil {
			return err
		}
		result, err = scanEvent(c.QueryRowContext(ctx, "SELECT * FROM events WHERE seq=?", seq))
		return err
	})
	return result, err
}
func (e *Events) query(query string, args ...any) ([]Event, error) {
	db, err := OpenDB(e.Path)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	rows, err := db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Event{}
	for rows.Next() {
		event, err := scanEvent(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, event)
	}
	return out, rows.Err()
}
func (e *Events) Events(after int64) ([]Event, error) {
	return e.query("SELECT * FROM events WHERE seq>? ORDER BY seq", after)
}
func (e *Events) Pending() ([]Event, error) {
	return e.query("SELECT e.* FROM events e JOIN pending p USING(seq) ORDER BY seq")
}
