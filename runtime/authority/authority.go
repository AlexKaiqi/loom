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
	if _, err = db.Exec(`PRAGMA journal_mode=WAL;CREATE TABLE IF NOT EXISTS works(id TEXT PRIMARY KEY,path TEXT UNIQUE NOT NULL,device INTEGER NOT NULL,inode INTEGER NOT NULL);CREATE TABLE IF NOT EXISTS grants(work_id TEXT PRIMARY KEY REFERENCES works(id),path TEXT NOT NULL,device INTEGER NOT NULL,inode INTEGER NOT NULL);CREATE TABLE IF NOT EXISTS relays(sender TEXT REFERENCES works(id),receiver TEXT REFERENCES works(id),PRIMARY KEY(sender,receiver));`); err != nil {
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
		if err = checkOverlap(db, target, "SELECT path,device,inode FROM works UNION ALL SELECT path,device,inode FROM grants"); err != nil {
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
			if !resume && (existing.State == "running" || existing.State == "paused") {
				return fmt.Errorf("%w: active or paused Round exists", store.ErrConflict)
			}
		}
		if w.Definition.Userspace != nil {
			directory, err := a.userspace(db, w)
			if err != nil {
				return err
			}
			if resume {
				err = w.VerifyUserspace(directory)
			} else {
				_, err = w.CaptureUserspace(directory)
			}
			if err != nil {
				return err
			}
		}
		if resume {
			round, err = w.Control.ResumeRound(owner)
		} else {
			round, err = w.Control.BeginRound(owner)
		}
		return err
	})
	return round, err
}
func (a *Authority) Grant(w *work.Work, directory string) error {
	target, err := StatIdentity(directory)
	if err != nil {
		return err
	}
	return store.Immediate(a.Path, func(db *sql.Conn) error {
		if err := a.authorize(db, w); err != nil {
			return err
		}
		if contains(target.Path, a.Path) {
			return fmt.Errorf("%w: Userspace contains authority storage", store.ErrConflict)
		}
		if err := checkOverlap(db, target, "SELECT path,device,inode FROM works UNION ALL SELECT path,device,inode FROM grants WHERE work_id!=?", w.ID); err != nil {
			return err
		}
		if w.Definition.Userspace == nil {
			return errors.New("Work does not declare a Userspace dependency")
		}
		rounds, err := w.Control.Rounds()
		if err != nil {
			return err
		}
		for _, round := range rounds {
			if round.State == "running" || round.State == "paused" && round.Checkpoint == nil {
				return fmt.Errorf("%w: cannot change Userspace during an unconfirmed active Round", store.ErrConflict)
			}
			if round.State == "paused" {
				effects, err := w.Control.Effects(round.ID)
				if err != nil {
					return err
				}
				for _, effect := range effects {
					if effect.Status != "completed" {
						return store.ErrUnknownEffect
					}
				}
			}
		}
		snapshot, err := w.UserspaceSnapshot()
		if err != nil {
			return err
		}
		if snapshot == nil {
			for _, round := range rounds {
				if round.State == "paused" {
					return errors.New("paused Userspace version is missing")
				}
			}
			_, err = w.CaptureUserspace(target.Path)
		} else {
			err = w.VerifyUserspace(target.Path)
		}
		if err != nil {
			return err
		}
		verified, err := StatIdentity(target.Path)
		if err != nil {
			return err
		}
		if verified != target {
			return fmt.Errorf("%w: Userspace changed during grant", store.ErrConflict)
		}
		_, err = db.ExecContext(context.Background(), "INSERT OR REPLACE INTO grants VALUES(?,?,?,?)", w.ID, target.Path, target.Device, target.Inode)
		return err
	})
}
func (a *Authority) Userspace(w *work.Work) (string, error) {
	db, err := store.OpenDB(a.Path)
	if err != nil {
		return "", err
	}
	defer db.Close()
	if err = a.authorize(db, w); err != nil {
		return "", err
	}
	return a.userspace(db, w)
}
func (a *Authority) userspace(db interface {
	QueryRowContext(context.Context, string, ...any) *sql.Row
}, w *work.Work) (string, error) {
	old, err := scanIdentity(db.QueryRowContext(context.Background(), "SELECT path,device,inode FROM grants WHERE work_id=?", w.ID))
	if err != nil {
		return "", fmt.Errorf("%w: no Userspace grant", ErrPermission)
	}
	target, err := StatIdentity(old.Path)
	if err != nil {
		return "", err
	}
	if old != target {
		return "", fmt.Errorf("%w: Userspace physical identity changed; explicit regrant required", ErrPermission)
	}
	return old.Path, nil
}

// RefreshGrant is exclusively for Runtime's confirmed remote-file publication.
func (a *Authority) RefreshGrant(w *work.Work, oldIdentity Identity) error {
	return store.Immediate(a.Path, func(db *sql.Conn) error {
		if err := a.authorize(db, w); err != nil {
			return err
		}
		old, err := scanIdentity(db.QueryRowContext(context.Background(), "SELECT path,device,inode FROM grants WHERE work_id=?", w.ID))
		if err != nil || old != oldIdentity {
			return fmt.Errorf("%w: Userspace grant changed during execution", store.ErrConflict)
		}
		target, err := StatIdentity(old.Path)
		if err != nil {
			return err
		}
		if err = checkOverlap(db, target, "SELECT path,device,inode FROM works UNION ALL SELECT path,device,inode FROM grants WHERE work_id!=?", w.ID); err != nil {
			return err
		}
		if _, err = w.CaptureUserspace(target.Path); err != nil {
			return err
		}
		verified, err := StatIdentity(target.Path)
		if err != nil {
			return err
		}
		if verified != target {
			return fmt.Errorf("%w: Userspace changed during publication capture", store.ErrConflict)
		}
		_, err = db.ExecContext(context.Background(), "UPDATE grants SET device=?,inode=? WHERE work_id=?", target.Device, target.Inode, w.ID)
		return err
	})
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
