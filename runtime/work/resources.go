package work

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"loom/runtime/filesystem"
	"loom/runtime/store"
	"os"
	"path/filepath"
)

type ResourceSource struct {
	Alias    string          `json:"alias"`
	Resource string          `json:"resource"`
	BaseRef  store.RecordRef `json:"base_ref"`
}
type ResourceCopy struct {
	ID         string          `json:"working_copy_id"`
	Alias      string          `json:"alias"`
	Target     string          `json:"target"`
	Generation int64           `json:"generation,string"`
	ContentRef store.RecordRef `json:"content_ref"`
}

func (w *Work) CaptureContent(directory string) (store.RecordRef, error) {
	var empty store.RecordRef
	before, err := filesystem.TreeDigest(directory)
	if err != nil {
		return empty, err
	}
	var body bytes.Buffer
	if err = filesystem.Archive(directory, &body); err != nil {
		return empty, err
	}
	after, err := filesystem.TreeDigest(directory)
	if err != nil {
		return empty, err
	}
	if before != after || digestBytes(body.Bytes()) != before {
		return empty, errors.New("baseline_conflict: resource changed during capture")
	}
	return (store.Records{Directory: w.ArtifactsDir()}).Put(body.Bytes(), "application/x-tar")
}
func (w *Work) ResourceSource(alias string) (*ResourceSource, error) {
	db, err := store.OpenDB(w.DBPath)
	if err != nil {
		return nil, err
	}
	defer db.Close()
	var body string
	err = db.QueryRow("SELECT source FROM resource_sources WHERE alias=?", alias).Scan(&body)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var source ResourceSource
	if err = json.Unmarshal([]byte(body), &source); err != nil {
		return nil, err
	}
	declaration, ok := w.Definition.Userspaces[alias]
	if !ok || source.Alias != alias || source.Resource != declaration.Resource {
		return nil, errors.New("resource source does not match declaration")
	}
	if _, err = (store.Records{Directory: w.ArtifactsDir()}).Get(source.BaseRef); err != nil {
		return nil, err
	}
	return &source, nil
}

// BindResource fixes an initial version once. Regranting on another host does
// not silently replace portable content with that host's current project tree.
func (w *Work) BindResource(alias, directory string) (*ResourceSource, error) {
	declaration, ok := w.Definition.Userspaces[alias]
	if !ok {
		return nil, errors.New("unknown resource alias")
	}
	old, err := w.ResourceSource(alias)
	if err != nil || old != nil {
		return old, err
	}
	ref, err := w.CaptureContent(directory)
	if err != nil {
		return nil, err
	}
	source := &ResourceSource{Alias: alias, Resource: declaration.Resource, BaseRef: ref}
	raw, err := json.Marshal(source)
	if err != nil {
		return nil, err
	}
	err = store.Immediate(w.DBPath, func(db *sql.Conn) error {
		var active int
		if err := db.QueryRowContext(context.Background(), "SELECT count(*) FROM rounds WHERE state IN('ready','running','recovering','blocked')").Scan(&active); err != nil {
			return err
		}
		if active != 0 {
			return errors.New("cannot initialize resource during active Round")
		}
		_, err := db.ExecContext(context.Background(), "INSERT INTO resource_sources VALUES(?,?)", alias, string(raw))
		return err
	})
	return source, err
}
func (w *Work) ResourceCopy(alias, target string) (ResourceCopy, error) {
	var copy ResourceCopy
	source, err := w.ResourceSource(alias)
	if err != nil {
		return copy, err
	}
	if source == nil {
		return copy, errors.New("dependency_missing: resource initial version not selected")
	}
	if target != "@read" {
		t, ok := w.Definition.Targets[target]
		if !ok {
			return copy, errors.New("unknown target")
		}
		allowed := false
		for _, name := range t.Userspaces {
			if name == alias {
				allowed = true
			}
		}
		if !allowed {
			return copy, errors.New("Target has no resource binding")
		}
	}
	err = store.Immediate(w.DBPath, func(db *sql.Conn) error {
		ctx := context.Background()
		if err := w.Control.Guard(db, w.Control.RoundID); err != nil {
			return err
		}
		var body string
		err := db.QueryRowContext(ctx, "SELECT id,alias,target,generation,content_ref FROM resource_copies WHERE alias=? AND target=?", alias, target).Scan(&copy.ID, &copy.Alias, &copy.Target, &copy.Generation, &body)
		if err == nil {
			return json.Unmarshal([]byte(body), &copy.ContentRef)
		}
		if !errors.Is(err, sql.ErrNoRows) {
			return err
		}
		id, err := store.ID()
		if err != nil {
			return err
		}
		copy = ResourceCopy{ID: id, Alias: alias, Target: target, Generation: 1, ContentRef: source.BaseRef}
		raw, err := json.Marshal(copy.ContentRef)
		if err != nil {
			return err
		}
		_, err = db.ExecContext(ctx, "INSERT INTO resource_copies VALUES(?,?,?,?,?)", id, alias, target, 1, string(raw))
		return err
	})
	if err == nil {
		_, err = (store.Records{Directory: w.ArtifactsDir()}).Get(copy.ContentRef)
	}
	return copy, err
}

type CopyUpdate struct {
	Prior ResourceCopy
	Ref   store.RecordRef
}

func (w *Work) SaveResourceCopy(prior ResourceCopy, ref store.RecordRef, effectID string) error {
	return w.SaveResourceCopies([]CopyUpdate{{prior, ref}}, effectID)
}

// All output copies and their predecessor checks commit in one SQLite transaction.
// A stale owner or one conflicting copy leaves every current pointer unchanged.
func (w *Work) SaveResourceCopies(updates []CopyUpdate, effectID string) error {
	for _, u := range updates {
		if w.Definition.Userspaces[u.Prior.Alias].Access != "write" {
			return errors.New("permission_denied: read resource cannot receive content")
		}
		if _, err := (store.Records{Directory: w.ArtifactsDir()}).Get(u.Ref); err != nil {
			return err
		}
	}
	return store.Immediate(w.DBPath, func(db *sql.Conn) error {
		if err := w.Control.Guard(db, w.Control.RoundID); err != nil {
			return err
		}
		ctx := context.Background()
		for _, u := range updates {
			body, err := json.Marshal(u.Ref)
			if err != nil {
				return err
			}
			before, err := json.Marshal(u.Prior.ContentRef)
			if err != nil {
				return err
			}
			p := u.Prior
			result, err := db.ExecContext(ctx, "UPDATE resource_copies SET content_ref=?,generation=generation+1 WHERE id=? AND alias=? AND target=? AND generation=? AND content_ref=?", string(body), p.ID, p.Alias, p.Target, p.Generation, string(before))
			if err != nil {
				return err
			}
			n, err := result.RowsAffected()
			if err != nil {
				return err
			}
			if n != 1 {
				return fmt.Errorf("%w: resource copy predecessor changed", store.ErrConflict)
			}
			if _, err = db.ExecContext(ctx, "INSERT INTO resource_versions(copy_id,predecessor,content_ref,effect_id) VALUES(?,?,?,?)", p.ID, string(before), string(body), effectID); err != nil {
				return err
			}
		}
		return nil
	})
}
func (w *Work) RestoreContent(ref store.RecordRef, destination string) error {
	raw, err := (store.Records{Directory: w.ArtifactsDir()}).Get(ref)
	if err != nil {
		return err
	}
	if ref.MediaType != "application/x-tar" {
		return errors.New("unsupported content type")
	}
	if err = os.Mkdir(destination, 0700); err != nil {
		return err
	}
	if err = filesystem.Extract(bytes.NewReader(raw), destination); err != nil {
		os.RemoveAll(destination)
		return err
	}
	return filesystem.SyncDir(filepath.Dir(destination))
}
func (w *Work) RestoreResource(alias, target, destination string) error {
	if filesystem.Inside(w.Path, destination) {
		return errors.New("resource restoration requires an independent destination")
	}
	if target == "" {
		source, err := w.ResourceSource(alias)
		if err != nil {
			return err
		}
		if source == nil {
			return errors.New("missing source")
		}
		return w.RestoreContent(source.BaseRef, destination)
	}
	copy, err := w.ResourceCopy(alias, target)
	if err != nil {
		return err
	}
	return w.RestoreContent(copy.ContentRef, destination)
}
func (w *Work) ValidateResources() error {
	for alias := range w.Definition.Userspaces {
		if _, err := w.ResourceSource(alias); err != nil {
			return err
		}
	}
	db, err := store.OpenDB(w.DBPath)
	if err != nil {
		return err
	}
	defer db.Close()
	rows, err := db.Query("SELECT content_ref FROM resource_copies UNION ALL SELECT predecessor FROM resource_versions UNION ALL SELECT content_ref FROM resource_versions")
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		var body string
		if err = rows.Scan(&body); err != nil {
			return err
		}
		var ref store.RecordRef
		if err = json.Unmarshal([]byte(body), &ref); err != nil {
			return err
		}
		if _, err = (store.Records{Directory: w.ArtifactsDir()}).Get(ref); err != nil {
			return err
		}
	}
	return rows.Err()
}
