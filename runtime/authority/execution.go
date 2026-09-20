package authority

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"loom/runtime/store"
	"loom/runtime/work"
)

type RoleIdentity struct{ HarnessUID, BashUID int }

// IDs come from a host-reserved range, never a Work file or caller's UID claim.
// They are monotonic and never recycled by this authority database.
func (a *Authority) ExecutionIdentity(w *work.Work, base, limit int) (RoleIdentity, error) {
	var identity RoleIdentity
	if base < 100000 || limit < 2 {
		return identity, errors.New("explicit reserved Unix identity range required")
	}
	err := store.Immediate(a.Path, func(db *sql.Conn) error {
		if err := a.authorize(db, w); err != nil {
			return err
		}
		ctx := context.Background()
		if _, err := db.ExecContext(ctx, "INSERT OR IGNORE INTO execution_identity_range VALUES(1,?,?)", base, limit); err != nil {
			return err
		}
		var savedBase, savedSize int
		if err := db.QueryRowContext(ctx, "SELECT base,size FROM execution_identity_range WHERE singleton=1").Scan(&savedBase, &savedSize); err != nil {
			return err
		}
		if savedBase != base || savedSize != limit {
			return errors.New("identity range differs from host reservation")
		}
		if _, err := db.ExecContext(ctx, "INSERT INTO execution_identities(work_id) VALUES(?) ON CONFLICT(work_id) DO NOTHING", w.ID); err != nil {
			return err
		}
		var ordinal int
		if err := db.QueryRowContext(ctx, "SELECT ordinal FROM execution_identities WHERE work_id=?", w.ID).Scan(&ordinal); err != nil {
			return err
		}
		if ordinal > limit/2 {
			return errors.New("reserved Unix identity range exhausted")
		}
		identity = RoleIdentity{base + 2*(ordinal-1), base + 2*(ordinal-1) + 1}
		return nil
	})
	return identity, err
}

type Domain struct{ ID, WorkID, RoundID, Owner, Role, Cgroup, Staging, State string }

func (a *Authority) SaveDomain(w *work.Work, d Domain) error {
	if d.ID == "" || d.Owner == "" || d.Cgroup == "" || d.Staging == "" || d.WorkID != w.ID {
		return errors.New("incomplete execution domain")
	}
	return store.Immediate(a.Path, func(db *sql.Conn) error {
		if err := a.authorize(db, w); err != nil {
			return err
		}
		return w.Control.Owned(func() error {
			_, err := db.ExecContext(context.Background(), "INSERT INTO execution_domains VALUES(?,?,?,?,?,?,?,?)", d.ID, d.WorkID, d.RoundID, d.Owner, d.Role, d.Cgroup, d.Staging, "retained")
			return err
		})
	})
}
func (a *Authority) Domains(w *work.Work) ([]Domain, error) {
	db, err := store.OpenDB(a.Path)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	if err = a.authorize(db, w); err != nil {
		return nil, err
	}
	rows, err := db.Query("SELECT id,work_id,round_id,owner,role,cgroup,staging,state FROM execution_domains WHERE work_id=? AND state!='cleaned'", w.ID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Domain{}
	for rows.Next() {
		var d Domain
		if err = rows.Scan(&d.ID, &d.WorkID, &d.RoundID, &d.Owner, &d.Role, &d.Cgroup, &d.Staging, &d.State); err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	return out, rows.Err()
}
func (a *Authority) SettleDomain(id, owner string) error {
	return store.Immediate(a.Path, func(db *sql.Conn) error {
		result, err := db.ExecContext(context.Background(), "UPDATE execution_domains SET state='fenced' WHERE id=? AND owner=? AND state IN('retained','fenced')", id, owner)
		if err != nil {
			return err
		}
		n, err := result.RowsAffected()
		if err != nil {
			return err
		}
		if n != 1 {
			return fmt.Errorf("%w: execution domain ownership", store.ErrConflict)
		}
		return nil
	})
}

func (a *Authority) CleanDomain(id, owner string) error {
	return store.Immediate(a.Path, func(db *sql.Conn) error {
		res, err := db.ExecContext(context.Background(), "UPDATE execution_domains SET state='cleaned' WHERE id=? AND owner=? AND state IN('fenced','cleaned')", id, owner)
		if err != nil {
			return err
		}
		n, err := res.RowsAffected()
		if err != nil {
			return err
		}
		if n != 1 {
			return store.ErrConflict
		}
		return nil
	})
}
