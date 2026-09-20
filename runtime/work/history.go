package work

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"

	"loom/runtime/filesystem"
	"loom/runtime/store"
)

// Inspect never opens a strategy or imports execution authority. The output is
// plain content plus a checkpoint record, usable with ordinary file tools.
func (w *Work) Inspect(checkpoint, destination string) error {
	cp, err := w.Control.Checkpoint(checkpoint)
	if err != nil {
		return err
	}
	version, ok := cp["content_ref"].(string)
	if !ok {
		return errors.New("checkpoint has no content version")
	}
	if err = w.Materialize(version, destination); err != nil {
		return err
	}
	good := false
	defer func() {
		if !good {
			os.RemoveAll(destination)
		}
	}()
	raw, err := json.MarshalIndent(cp, "", "  ")
	if err != nil {
		return err
	}
	if err = Save(filepath.Join(destination, "checkpoint.json"), raw); err != nil {
		return err
	}
	copies, err := checkpointCopies(cp)
	if err != nil {
		return err
	}
	resources := filepath.Join(destination, "resource-copies")
	if err = os.Mkdir(resources, 0700); err != nil {
		return err
	}
	for _, copy := range copies {
		// Directory names are fixed UUIDs, never imported aliases or target paths.
		if !safeUUID(copy.ID) {
			return errors.New("invalid saved copy identity")
		}
		if err = w.RestoreContent(copy.ContentRef, filepath.Join(resources, copy.ID)); err != nil {
			return err
		}
	}
	good = true
	return nil
}
func checkpointCopies(cp store.Object) ([]ResourceCopy, error) {
	raw, err := json.Marshal(cp["resource_copies"])
	if err != nil {
		return nil, err
	}
	var copies []ResourceCopy
	if err = json.Unmarshal(raw, &copies); err != nil {
		return nil, err
	}
	return copies, nil
}
func safeUUID(id string) bool {
	if len(id) != 36 {
		return false
	}
	for i, c := range id {
		if i == 8 || i == 13 || i == 18 || i == 23 {
			if c != '-' {
				return false
			}
		} else if !(c >= '0' && c <= '9' || c >= 'a' && c <= 'f') {
			return false
		}
	}
	return true
}

// Fork creates new responsibility and new copy identities. Original facts remain
// immutable history; no pending inputs, effects, allocations, subscriptions,
// owners or physical grants are copied. A new input is needed to start work.
func (w *Work) Fork(checkpoint, destination string) (result *Work, err error) {
	cp, err := w.Control.Checkpoint(checkpoint)
	if err != nil {
		return nil, err
	}
	version, ok := cp["content_ref"].(string)
	if !ok {
		return nil, errors.New("checkpoint has no content version")
	}
	harnessRef, ok := cp["harness_ref"].(string)
	if !ok {
		return nil, errors.New("checkpoint has no strategy version")
	}
	watermark, err := strconv.ParseInt(fmt.Sprint(cp["fact_watermark"]), 10, 64)
	if err != nil || watermark < 0 {
		return nil, errors.New("invalid checkpoint watermark")
	}
	temp, err := os.MkdirTemp("", "loom-fork-")
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(temp)
	content, strategy := filepath.Join(temp, "content"), filepath.Join(temp, "strategy")
	if err = w.Materialize(version, content); err != nil {
		return nil, err
	}
	if err = w.Materialize(harnessRef, strategy); err != nil {
		return nil, err
	}
	child, err := Create(destination, filepath.Join(strategy, "harness"), filepath.Join(strategy, "work.toml"))
	if err != nil {
		return nil, err
	}
	defer func() {
		if err != nil {
			os.RemoveAll(child.Path)
		}
	}()
	// These are unshared new directories; this operation never resets a live Work.
	if err = os.Remove(child.Surface); err != nil {
		return nil, err
	}
	if err = copyTree(filepath.Join(content, "surface"), child.Surface); err != nil {
		return nil, err
	}
	records, err := os.ReadDir(w.ArtifactsDir())
	if err != nil {
		return nil, err
	}
	for _, entry := range records {
		if entry.IsDir() {
			continue
		} // adapter staging is not an immutable record
		if !validDigest(entry.Name()) {
			return nil, errors.New("invalid record member")
		}
		info, e := entry.Info()
		if e != nil {
			return nil, e
		}
		ref := store.RecordRef{SHA256: entry.Name(), SizeBytes: strconv.FormatInt(info.Size(), 10), MediaType: "application/octet-stream"}
		raw, e := (store.Records{Directory: w.ArtifactsDir()}).Get(ref)
		if e != nil {
			return nil, e
		}
		if _, e = (store.Records{Directory: child.ArtifactsDir()}).Put(raw, ref.MediaType); e != nil {
			return nil, e
		}
	}
	// Imported fact projections keep their original immutable content refs.
	if _, err = child.git("fetch", "--no-tags", "--no-write-fetch-head", filepath.Join(w.Path, ".loom", "versions.git"), "refs/loom/retained/*:refs/loom/origin/*"); err != nil {
		return nil, err
	}
	copies, err := checkpointCopies(cp)
	if err != nil {
		return nil, err
	}
	err = store.Immediate(w.DBPath, func(source *sql.Conn) error {
		return store.Immediate(child.DBPath, func(target *sql.Conn) error {
			ctx := context.Background()
			// Copy only the immutable fact prefix selected by the checkpoint. Admissions
			// are deliberately not inherited; they belong to original Work identities.
			rows, e := source.QueryContext(ctx, "SELECT seq,source,request_id,kind,payload,digest,created FROM events WHERE seq<=? ORDER BY seq", watermark)
			if e != nil {
				return e
			}
			defer rows.Close()
			for rows.Next() {
				var seq int64
				var src, key, kind, payload, digest, created string
				if e = rows.Scan(&seq, &src, &key, &kind, &payload, &digest, &created); e != nil {
					return e
				}
				if _, e = target.ExecContext(ctx, "INSERT INTO events(seq,source,request_id,kind,payload,digest,created) VALUES(?,?,?,?,?,?,?)", seq, src, key, kind, payload, digest, created); e != nil {
					return e
				}
			}
			if e = rows.Err(); e != nil {
				return e
			}
			sources, e := source.QueryContext(ctx, "SELECT alias,source FROM resource_sources ORDER BY alias")
			if e != nil {
				return e
			}
			defer sources.Close()
			for sources.Next() {
				var alias, raw string
				if e = sources.Scan(&alias, &raw); e != nil {
					return e
				}
				if _, e = target.ExecContext(ctx, "INSERT INTO resource_sources VALUES(?,?)", alias, raw); e != nil {
					return e
				}
			}
			if e = sources.Err(); e != nil {
				return e
			}
			for _, copy := range copies {
				if _, e := (store.Records{Directory: child.ArtifactsDir()}).Get(copy.ContentRef); e != nil {
					return e
				}
				id, e := store.ID()
				if e != nil {
					return e
				}
				raw, e := json.Marshal(copy.ContentRef)
				if e != nil {
					return e
				}
				if _, e = target.ExecContext(ctx, "INSERT INTO resource_copies VALUES(?,?,?,?,?)", id, copy.Alias, copy.Target, 1, string(raw)); e != nil {
					return e
				}
			}
			return nil
		})
	})
	if err != nil {
		return nil, err
	}
	if _, err = child.SelectHarness(); err != nil {
		return nil, err
	}
	if _, err = child.Events.Append("runtime", "fork-origin", "work.forked", store.Object{"source_work_id": w.ID, "source_checkpoint_id": checkpoint, "source_fact_watermark": strconv.FormatInt(watermark, 10), "source_content_ref": version, "source_harness_ref": harnessRef}); err != nil {
		return nil, err
	}
	if err = filesystem.SyncDir(child.Path); err != nil {
		return nil, err
	}
	return child, nil
}
