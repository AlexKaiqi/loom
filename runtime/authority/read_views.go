package authority

import (
	"context"
	"database/sql"
	"errors"
	"loom/runtime/store"
	"loom/runtime/work"
	"regexp"
)

type ReadGrant struct {
	Alias  string
	Source *work.Work
}

var readAlias = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]*$`)

func (a *Authority) GrantRead(source, reader *work.Work, alias string) error {
	if source.ID == reader.ID || !readAlias.MatchString(alias) {
		return errors.New("invalid cross-Work read alias")
	}
	if _, exists := reader.Definition.Userspaces[alias]; exists {
		return errors.New("read alias conflicts with Userspace")
	}
	return store.Immediate(a.Path, func(db *sql.Conn) error {
		if err := a.authorize(db, source); err != nil {
			return err
		}
		if err := a.authorize(db, reader); err != nil {
			return err
		}
		var existing string
		err := db.QueryRowContext(context.Background(), "SELECT source FROM read_grants WHERE reader=? AND alias=?", reader.ID, alias).Scan(&existing)
		if err == nil {
			if existing != source.ID {
				return store.ErrConflict
			}
			return nil
		}
		if !errors.Is(err, sql.ErrNoRows) {
			return err
		}
		_, err = db.ExecContext(context.Background(), "INSERT INTO read_grants VALUES(?,?,?)", source.ID, reader.ID, alias)
		return err
	})
}
func (a *Authority) ReadGrants(reader *work.Work) ([]ReadGrant, error) {
	if err := a.Authorize(reader); err != nil {
		return nil, err
	}
	db, err := store.OpenDB(a.Path)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	rows, err := db.Query("SELECT source,alias FROM read_grants WHERE reader=? ORDER BY alias", reader.ID)
	if err != nil {
		return nil, err
	}
	type row struct{ source, alias string }
	entries := []row{}
	for rows.Next() {
		var r row
		if err = rows.Scan(&r.source, &r.alias); err != nil {
			rows.Close()
			return nil, err
		}
		entries = append(entries, r)
	}
	if err = errors.Join(rows.Err(), rows.Close()); err != nil {
		return nil, err
	}
	out := []ReadGrant{}
	for _, r := range entries {
		source, err := a.WorkByID(r.source)
		if err != nil {
			return nil, err
		}
		out = append(out, ReadGrant{r.alias, source})
	}
	return out, nil
}
func (a *Authority) RevokeRead(reader *work.Work, alias string) error {
	return store.Immediate(a.Path, func(db *sql.Conn) error {
		if err := a.authorize(db, reader); err != nil {
			return err
		}
		var active int
		if err := db.QueryRowContext(context.Background(), "SELECT count(*) FROM execution_domains WHERE work_id=? AND state!='cleaned'", reader.ID).Scan(&active); err != nil {
			return err
		}
		if active != 0 {
			return errors.New("not_ready: fence reader execution domains before revoking a mounted read view")
		}
		return reader.Control.Owned(func() error {
			// Claim uses the same authority-then-Work lock order, so no domain can be
			// created concurrently between the grant deletion and the next validation.
			rounds, err := reader.Control.Rounds()
			if err != nil {
				return err
			}
			for _, r := range rounds {
				if r.State == "running" || r.State == "recovering" {
					return errors.New("not_ready: recover the reader before revoking its view")
				}
			}
			_, err = db.ExecContext(context.Background(), "DELETE FROM read_grants WHERE reader=? AND alias=?", reader.ID, alias)
			return err
		})
	})
}
