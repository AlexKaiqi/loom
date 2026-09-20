// Package authority owns host-local grants. Work portability cannot confer them.
package authority

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"loom/runtime/store"
	"loom/runtime/work"
)

type Authority struct{ Path string }

var ErrPermission = errors.New("permission denied")

func Open(path string) (*Authority, error) {
	path, err := filepath.Abs(path)
	if err != nil {
		return nil, err
	}
	if err = os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return nil, err
	}
	parent, err := filepath.EvalSymlinks(filepath.Dir(path))
	if err != nil {
		return nil, err
	}
	path = filepath.Join(parent, filepath.Base(path))
	if info, err := os.Lstat(path); err == nil && info.Mode()&os.ModeSymlink != 0 {
		return nil, errors.New("symbolic authority database refused")
	}
	db, err := store.OpenDB(path)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	if _, err = db.Exec(`PRAGMA journal_mode=WAL;CREATE TABLE IF NOT EXISTS works(id TEXT PRIMARY KEY,path TEXT UNIQUE NOT NULL,device INTEGER NOT NULL,inode INTEGER NOT NULL);CREATE TABLE IF NOT EXISTS authority_identity(singleton INTEGER PRIMARY KEY CHECK(singleton=1),scope TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS resources(id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,path TEXT NOT NULL,device INTEGER NOT NULL,inode INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS resource_grants(work_id TEXT NOT NULL REFERENCES works(id),alias TEXT NOT NULL,resource_id TEXT NOT NULL REFERENCES resources(id),access TEXT NOT NULL CHECK(access IN('read','write')),PRIMARY KEY(work_id,alias));CREATE TABLE IF NOT EXISTS execution_identity_range(singleton INTEGER PRIMARY KEY CHECK(singleton=1),base INTEGER NOT NULL,size INTEGER NOT NULL);CREATE TABLE IF NOT EXISTS execution_identities(ordinal INTEGER PRIMARY KEY AUTOINCREMENT,work_id TEXT UNIQUE NOT NULL REFERENCES works(id));CREATE TABLE IF NOT EXISTS execution_domains(id TEXT PRIMARY KEY,work_id TEXT NOT NULL REFERENCES works(id),round_id TEXT NOT NULL,owner TEXT NOT NULL,role TEXT NOT NULL,cgroup TEXT NOT NULL,staging TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN('retained','fenced','cleaned')));CREATE TABLE IF NOT EXISTS read_grants(source TEXT NOT NULL REFERENCES works(id),reader TEXT NOT NULL REFERENCES works(id),alias TEXT NOT NULL,PRIMARY KEY(reader,alias));CREATE TABLE IF NOT EXISTS relays(sender TEXT REFERENCES works(id),receiver TEXT REFERENCES works(id),PRIMARY KEY(sender,receiver));`); err != nil {
		return nil, err
	}
	scope, e := store.ID()
	if e != nil {
		return nil, e
	}
	if _, err = db.Exec("INSERT OR IGNORE INTO authority_identity VALUES(1,?)", scope); err != nil {
		return nil, err
	}
	if err = os.Chmod(path, 0600); err != nil {
		return nil, err
	}
	return &Authority{Path: path}, nil
}
func scanIdentity(row interface{ Scan(...any) error }) (Identity, error) {
	var i Identity
	err := row.Scan(&i.Path, &i.Device, &i.Inode)
	return i, err
}
func (a *Authority) Register(w *work.Work) error {
	target, err := StatIdentity(w.Path)
	if err != nil {
		return err
	}
	opened, err := work.Open(w.Path)
	if err != nil {
		return err
	}
	if opened.ID != w.ID {
		return errors.New("Work identity changed")
	}
	return store.Immediate(a.Path, func(db *sql.Conn) error {
		ctx := context.Background()
		old, err := scanIdentity(db.QueryRowContext(ctx, "SELECT path,device,inode FROM works WHERE id=?", w.ID))
		if err == nil {
			if old != target {
				return fmt.Errorf("%w: Work registered at another physical location", store.ErrConflict)
			}
			return nil
		}
		if !errors.Is(err, sql.ErrNoRows) {
			return err
		}
		if contains(target.Path, a.Path) {
			return fmt.Errorf("%w: Work contains authority storage", store.ErrConflict)
		}
		if err = checkOverlap(db, target, "SELECT path,device,inode FROM works UNION ALL SELECT path,device,inode FROM resources"); err != nil {
			return err
		}
		_, err = db.ExecContext(ctx, "INSERT INTO works VALUES(?,?,?,?)", w.ID, target.Path, target.Device, target.Inode)
		return err
	})
}
func checkOverlap(db *sql.Conn, target Identity, query string, args ...any) error {
	rows, err := db.QueryContext(context.Background(), query, args...)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		old, err := scanIdentity(rows)
		if err != nil {
			return err
		}
		if Overlaps(target.Path, old.Path) || target.samePhysical(old) {
			return fmt.Errorf("%w: root overlaps another authorized root", store.ErrConflict)
		}
	}
	return rows.Err()
}
func (a *Authority) authorize(db interface {
	QueryRowContext(context.Context, string, ...any) *sql.Row
}, w *work.Work) error {
	target, err := StatIdentity(w.Path)
	if err != nil {
		return err
	}
	old, err := scanIdentity(db.QueryRowContext(context.Background(), "SELECT path,device,inode FROM works WHERE id=?", w.ID))
	if err != nil || old != target {
		return fmt.Errorf("%w: Work not registered at this physical location", ErrPermission)
	}
	opened, err := work.Open(w.Path)
	if err != nil {
		return err
	}
	if opened.ID != w.ID {
		return fmt.Errorf("%w: Work identity changed", ErrPermission)
	}
	return nil
}
func (a *Authority) Authorize(w *work.Work) error {
	db, err := store.OpenDB(a.Path)
	if err != nil {
		return err
	}
	defer db.Close()
	return a.authorize(db, w)
}

// Export serializes the snapshot with every host-authorized dependency change.
// Lock order matches Claim/Grant: host authority first, then the Work database.
func (a *Authority) Export(w *work.Work, archive string) error {
	return store.Immediate(a.Path, func(db *sql.Conn) error {
		if err := a.authorize(db, w); err != nil {
			return err
		}
		var retained int
		if err := db.QueryRowContext(context.Background(), "SELECT count(*) FROM execution_domains WHERE work_id=? AND state!='cleaned'", w.ID).Scan(&retained); err != nil {
			return err
		}
		if retained != 0 {
			return fmt.Errorf("%w: export requires saved fencing and content custody for every execution domain", store.ErrConflict)
		}
		return w.Export(archive)
	})
}
func (a *Authority) Claim(w *work.Work, owner string, resume bool) (store.Round, error) {
	var round store.Round
	err := store.Immediate(a.Path, func(db *sql.Conn) error {
		if err := a.authorize(db, w); err != nil {
			return err
		}
		// Validate before changing either the checkpoint or its external version.
		rounds, err := w.Control.Rounds()
		if err != nil {
			return err
		}
		for _, existing := range rounds {
			if !resume && (existing.State != "handed_off") {
				return fmt.Errorf("%w: active or paused Round exists", store.ErrConflict)
			}
		}
		ref, err := w.Control.SelectedStrategy()
		if err != nil {
			return err
		}
		if resume {
			for _, existing := range rounds {
				if existing.State != "handed_off" {
					ref = existing.HarnessRef
					break
				}
			}
		}
		w, err := w.ForStrategy(ref)
		if err != nil {
			return err
		}
		for alias := range w.Definition.Userspaces {
			if _, err := a.resource(db, w, alias); err != nil {
				return err
			}
			if source, err := w.ResourceSource(alias); err != nil {
				return err
			} else if source == nil {
				return errors.New("dependency_missing: resource source is not fixed")
			}
		}
		if resume {
			round, err = w.Control.ResumeRound(owner)
		} else {
			round, err = w.Control.BeginRoundSelected(owner, ref)
		}
		return err
	})
	return round, err
}
func (a *Authority) AllowRelay(sender, receiver *work.Work) error {
	return store.Immediate(a.Path, func(db *sql.Conn) error {
		if err := a.authorize(db, sender); err != nil {
			return err
		}
		if err := a.authorize(db, receiver); err != nil {
			return err
		}
		_, err := db.ExecContext(context.Background(), "INSERT OR IGNORE INTO relays VALUES(?,?)", sender.ID, receiver.ID)
		return err
	})
}
func (a *Authority) RelayAllowed(sender, receiver *work.Work) error {
	db, err := store.OpenDB(a.Path)
	if err != nil {
		return err
	}
	defer db.Close()
	if err = a.authorize(db, sender); err != nil {
		return err
	}
	if err = a.authorize(db, receiver); err != nil {
		return err
	}
	var marker int
	if err = db.QueryRow("SELECT 1 FROM relays WHERE sender=? AND receiver=?", sender.ID, receiver.ID).Scan(&marker); err != nil {
		return fmt.Errorf("%w: cross-Work relay has no host grant", ErrPermission)
	}
	return nil
}
