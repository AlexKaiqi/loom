package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"path/filepath"
	"strconv"
)

type Event struct {
	Seq       int64     `json:"seq,string"`
	Source    string    `json:"source"`
	RequestID string    `json:"request_id"`
	Kind      string    `json:"kind"`
	Payload   Object    `json:"payload"`
	Digest    string    `json:"digest"`
	Created   string    `json:"created"`
	FactID    string    `json:"fact_id"`
	RecordRef RecordRef `json:"record_ref"`
}
type Events struct {
	Path    string
	Control *Control
}

func scanEvent(row scanner) (Event, error) {
	var e Event
	var payload string
	err := row.Scan(&e.Seq, &e.Source, &e.RequestID, &e.Kind, &payload, &e.Digest, &e.Created)
	if err != nil {
		return e, err
	}
	e.Payload, err = DecodeObject(payload)
	e.FactID = "F" + strconv.FormatInt(e.Seq, 10)
	e.RecordRef = refFor([]byte(payload), "application/json")
	return e, err
}
func (e *Events) Admit(source, requestID, kind string, payload Object) (Event, error) {
	return e.append(source, requestID, kind, payload, true, false)
}

// Append records an observation without creating input-processing responsibility.
// It is a trusted adapter API, not an operation exposed to Harness or Work Bash.
func (e *Events) Append(source, requestID, kind string, payload Object) (Event, error) {
	return e.append(source, requestID, kind, payload, false, false)
}

// AppendOwned publishes a controller decision under the same transaction as the
// epoch check. Adapter observations use Append: late evidence remains evidence
// after an ownership change, but an old Harness cannot publish new decisions.
func (e *Events) AppendOwned(source, requestID, kind string, payload Object) (Event, error) {
	if e.Control == nil || e.Control.Owner == "" {
		return Event{}, errors.New("bound Round owner required")
	}
	return e.append(source, requestID, kind, payload, false, true)
}
func (e *Events) append(source, requestID, kind string, payload Object, input, owned bool) (Event, error) {
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
	if _, err = (Records{Directory: filepath.Join(filepath.Dir(e.Path), "records")}).Put([]byte(body), "application/json"); err != nil {
		return result, err
	}
	err = Immediate(e.Path, func(c *sql.Conn) error {
		if owned {
			if err := e.Control.Guard(c, e.Control.RoundID); err != nil {
				return err
			}
		}
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
		if input {
			if _, err = c.ExecContext(ctx, "INSERT INTO pending VALUES(?)", seq); err != nil {
				return err
			}
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
