package store

import (
	"context"
	"database/sql"
	"errors"
	"regexp"
)

var gitObject = regexp.MustCompile(`^(?:[0-9a-f]{40}|[0-9a-f]{64})$`)

func (c *Control) SelectedStrategy() (string, error) {
	db, err := OpenDB(c.Path)
	if err != nil {
		return "", err
	}
	defer db.Close()
	var ref string
	err = db.QueryRow("SELECT content_ref FROM selected_strategy WHERE singleton=1").Scan(&ref)
	return ref, err
}

// SelectStrategy affects only a subsequently created Round. Existing Round and
// checkpoint bindings are never rewritten, including during an active advance.
func (c *Control) SelectStrategy(ref string) error {
	if !gitObject.MatchString(ref) {
		return errors.New("full immutable Git content reference required")
	}
	return Immediate(c.Path, func(db *sql.Conn) error {
		_, err := db.ExecContext(context.Background(), "INSERT INTO selected_strategy VALUES(1,?) ON CONFLICT(singleton) DO UPDATE SET content_ref=excluded.content_ref", ref)
		return err
	})
}

func (c *Control) ClaimedInputs(round string) ([]int64, error) {
	db, err := OpenDB(c.Path)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	rows, err := db.Query("SELECT seq FROM round_inputs WHERE round_id=? ORDER BY seq", round)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []int64{}
	for rows.Next() {
		var seq int64
		if err = rows.Scan(&seq); err != nil {
			return nil, err
		}
		out = append(out, seq)
	}
	return out, rows.Err()
}
