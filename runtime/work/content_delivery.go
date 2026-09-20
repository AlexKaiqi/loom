package work

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"loom/runtime/filesystem"
	"loom/runtime/store"
)

// ContentChange names a logical Work root. Neither host paths nor physical
// identities enter the portable journal. Only the controller writes this type.
type ContentChange struct {
	Root     string          `json:"root"`
	Expected string          `json:"expected_digest"`
	Ref      store.RecordRef `json:"record_ref"`
}

// PublishContent retains all candidates before touching the working files. Each
// Unix directory exchange is atomic; the journal joins them into one recoverable
// delivery. A model request cannot cross an unfinished delivery.
func (w *Work) PublishContent(effectID string, changes []ContentChange) (string, error) {
	if len(changes) != 2 {
		return "", errors.New("complete Work content candidate required")
	}
	seen := map[string]bool{}
	records := store.Records{Directory: w.ArtifactsDir()}
	for _, change := range changes {
		if (change.Root != "surface" && change.Root != "harness") || seen[change.Root] || len(change.Expected) != 64 {
			return "", errors.New("invalid content candidate")
		}
		seen[change.Root] = true
		if _, err := records.Get(change.Ref); err != nil {
			return "", err
		}
	}
	encoded, err := json.Marshal(changes)
	if err != nil {
		return "", err
	}
	ref, err := records.Put(encoded, "application/vnd.loom.content-delivery+json")
	if err != nil {
		return "", err
	}
	body, err := store.Canonical(ref)
	if err != nil {
		return "", err
	}
	err = store.Immediate(w.DBPath, func(db *sql.Conn) error {
		if err := w.Control.Guard(db, w.Control.RoundID); err != nil {
			return err
		}
		var round, kind, resolution string
		if err := db.QueryRowContext(context.Background(), "SELECT round_id,kind,resolution FROM effects WHERE id=?", effectID).Scan(&round, &kind, &resolution); err != nil {
			return err
		}
		if kind != "tool.exec" || resolution != "native_result" || w.Control.Owner != "" && round != w.Control.RoundID {
			return errors.New("native Work execution result required")
		}
		var prior string
		err := db.QueryRowContext(context.Background(), "SELECT candidate_ref FROM content_deliveries WHERE effect_id=?", effectID).Scan(&prior)
		if err == nil {
			if prior != body {
				return fmt.Errorf("%w: content candidate identity", store.ErrConflict)
			}
			return nil
		}
		if !errors.Is(err, sql.ErrNoRows) {
			return err
		}
		_, err = db.ExecContext(context.Background(), "INSERT INTO content_deliveries(effect_id,candidate_ref) VALUES(?,?)", effectID, body)
		return err
	})
	if err != nil {
		return "", err
	}
	return w.deliverContent(effectID)
}

func (w *Work) deliverContent(effectID string) (revision string, err error) {
	err = store.Immediate(w.DBPath, func(db *sql.Conn) error {
		if err := w.Control.Guard(db, w.Control.RoundID); err != nil {
			return err
		}
		var encoded string
		var saved sql.NullString
		if err := db.QueryRowContext(context.Background(), "SELECT candidate_ref,revision FROM content_deliveries WHERE effect_id=?", effectID).Scan(&encoded, &saved); err != nil {
			return err
		}
		if saved.Valid {
			revision = saved.String
			return nil
		}
		var ref store.RecordRef
		if err := json.Unmarshal([]byte(encoded), &ref); err != nil {
			return err
		}
		records := store.Records{Directory: w.ArtifactsDir()}
		body, err := records.Get(ref)
		if err != nil {
			return err
		}
		var changes []ContentChange
		if err = json.Unmarshal(body, &changes); err != nil {
			return err
		}
		// Validate every complete archive before exchanging the first root. A bad
		// second candidate must not leave a new Surface paired with old strategy.
		validation, err := os.MkdirTemp(filepath.Join(w.Path, ".loom"), ".delivery-check-")
		if err != nil {
			return err
		}
		defer os.RemoveAll(validation)
		for _, change := range changes {
			if change.Root != "surface" && change.Root != "harness" {
				return errors.New("invalid delivery root")
			}
			if err = w.RestoreContent(change.Ref, filepath.Join(validation, change.Root)); err != nil {
				return err
			}
		}
		// Check all roots first. After a crash, either the old or the candidate
		// root is acceptable; a human's third version is preserved and conflicts.
		for _, change := range changes {
			now, err := filesystem.TreeDigest(w.contentRoot(change.Root))
			if err != nil {
				return err
			}
			if now != change.Expected && now != change.Ref.SHA256 {
				return fmt.Errorf("%w: local %s edits preserved", store.ErrConflict, change.Root)
			}
		}
		for _, change := range changes {
			root := w.contentRoot(change.Root)
			now, err := filesystem.TreeDigest(root)
			if err != nil {
				return err
			}
			if now == change.Ref.SHA256 {
				continue
			}
			info, err := os.Lstat(root)
			if err != nil {
				return err
			}
			body, err := records.Get(change.Ref)
			if err != nil {
				return err
			}
			if err = filesystem.Restore(bytes.NewReader(body), root, info, change.Expected); err != nil {
				return err
			}
		}
		revision, err = w.Snapshot("Work content delivery " + effectID)
		if err != nil {
			return err
		}
		if _, err = db.ExecContext(context.Background(), "UPDATE content_deliveries SET revision=? WHERE effect_id=?", revision, effectID); err != nil {
			return err
		}
		_, err = db.ExecContext(context.Background(), "UPDATE effects SET content_delivery='confirmed' WHERE id=? AND resolution='native_result'", effectID)
		return err
	})
	return revision, err
}

// RecoverContent is used only by the host recovery coordinator after fencing all
// retained domains. It completes file custody, never repeats the tool command.
func (w *Work) RecoverContent() error {
	db, err := store.OpenDB(w.DBPath)
	if err != nil {
		return err
	}
	rows, err := db.Query("SELECT effect_id FROM content_deliveries WHERE revision IS NULL ORDER BY rowid")
	if err != nil {
		db.Close()
		return err
	}
	var ids []string
	for rows.Next() {
		var id string
		if err = rows.Scan(&id); err != nil {
			break
		}
		ids = append(ids, id)
	}
	err = errors.Join(err, rows.Err(), rows.Close(), db.Close())
	if err != nil {
		return err
	}
	for _, id := range ids {
		if _, err = w.deliverContent(id); err != nil {
			return err
		}
	}
	return nil
}
