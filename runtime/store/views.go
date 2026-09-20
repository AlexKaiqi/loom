package store

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type ViewScope struct {
	MountPath string `json:"mount_path,omitempty"`
	WorkID    string `json:"work_id"`
	// Nil means all facts of this Work, only after the caller's full-read grant.
	FactIDs []string `json:"fact_ids"`
}
type FactView struct {
	ID        string    `json:"view_id"`
	Directory string    `json:"directory"`
	Database  string    `json:"database"`
	Watermark string    `json:"fact_watermark"`
	ScopeRef  RecordRef `json:"access_scope_ref"`
}

// OpenView reads one SQLite snapshot, copies only authorized raw records and
// atomically publishes a derived, closed database. It contains no control tables
// or hidden unfiltered base tables. The execution layer mounts the result read
// only; SQLite's -readonly argument is merely a convenience.
func (e *Events) OpenView(scope ViewScope, minimum int64) (FactView, error) {
	var view FactView
	if scope.WorkID == "" || minimum < 0 || (scope.MountPath != "" && scope.MountPath != "/facts" && !(strings.HasPrefix(scope.MountPath, "/facts/") && filepath.Clean(scope.MountPath) == scope.MountPath)) {
		return view, errors.New("view source and nonnegative watermark required")
	}
	db, err := OpenDB(e.Path)
	if err != nil {
		return view, err
	}
	defer db.Close()
	tx, err := db.BeginTx(context.Background(), &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return view, err
	}
	defer tx.Rollback()
	var watermark int64
	if err = tx.QueryRow("SELECT COALESCE(MAX(seq),0) FROM events").Scan(&watermark); err != nil {
		return view, err
	}
	if watermark < minimum {
		return view, fmt.Errorf("not_ready: view watermark %d is below required %d", watermark, minimum)
	}
	allowed := map[string]bool{}
	for _, id := range scope.FactIDs {
		if id == "" || allowed[id] {
			return view, errors.New("invalid fact scope")
		}
		allowed[id] = true
	}
	rows, err := tx.Query("SELECT * FROM events ORDER BY seq")
	if err != nil {
		return view, err
	}
	facts := []Event{}
	for rows.Next() {
		fact, err := scanEvent(rows)
		if err != nil {
			rows.Close()
			return view, err
		}
		if scope.FactIDs == nil || allowed[fact.FactID] {
			facts = append(facts, fact)
			delete(allowed, fact.FactID)
		}
	}
	err = errors.Join(rows.Err(), rows.Close())
	if err != nil {
		return view, err
	}
	if len(allowed) > 0 {
		return view, errors.New("dependency_missing: scope refers to unavailable facts")
	}
	advanceOrder, err := viewAdvanceOrder(tx, facts)
	if err != nil {
		return view, err
	}
	if err = tx.Commit(); err != nil {
		return view, err
	}
	state := filepath.Dir(e.Path)
	records := Records{Directory: filepath.Join(state, "records")}
	scopeBytes, err := json.Marshal(scope)
	if err != nil {
		return view, err
	}
	scopeRef, err := records.Put(scopeBytes, "application/vnd.loom.access-scope+json")
	if err != nil {
		return view, err
	}
	id, err := Digest(Object{"schema_version": 1, "scope": scopeRef, "watermark": strconv.FormatInt(watermark, 10), "facts": facts, "advance_order": advanceOrder})
	if err != nil {
		return view, err
	}
	parent := filepath.Join(state, "views")
	if err = os.MkdirAll(parent, 0700); err != nil {
		return view, err
	}
	view = FactView{ID: id, Directory: filepath.Join(parent, id), Watermark: strconv.FormatInt(watermark, 10), ScopeRef: scopeRef}
	view.Database = filepath.Join(view.Directory, "facts.sqlite")
	// Rebuild rather than trust a possibly damaged cache. The fixed publication
	// path may already exist; validation below compares every produced byte.
	stage, err := os.MkdirTemp(parent, ".view-")
	if err != nil {
		return view, err
	}
	defer os.RemoveAll(stage)
	derived, err := sql.Open("sqlite", filepath.Join(stage, "facts.sqlite"))
	if err != nil {
		return view, err
	}
	defer derived.Close()
	if _, err = derived.Exec(`PRAGMA journal_mode=DELETE; PRAGMA synchronous=FULL;
CREATE TABLE view_meta(schema_version INTEGER NOT NULL,view_id TEXT NOT NULL,source_work_id TEXT NOT NULL,fact_watermark TEXT NOT NULL,access_scope_ref TEXT NOT NULL,text_coverage TEXT NOT NULL);
CREATE TABLE facts(ordinal INTEGER PRIMARY KEY,fact_id TEXT UNIQUE NOT NULL,kind TEXT NOT NULL,source TEXT NOT NULL,observed_at TEXT NOT NULL,search_text TEXT NOT NULL,record_ref TEXT NOT NULL,record_path TEXT,advance_ordinal INTEGER);
CREATE INDEX facts_source_kind ON facts(source,kind);`); err != nil {
		return view, err
	}
	scopeJSON, _ := json.Marshal(scopeRef)
	if _, err = derived.Exec("INSERT INTO view_meta VALUES(1,?,?,?,?,?)", id, scope.WorkID, view.Watermark, string(scopeJSON), "partial: decoded JSON text only; attachments and referenced binary bodies are not indexed"); err != nil {
		return view, err
	}
	for i, fact := range facts {
		raw, err := records.Get(fact.RecordRef)
		if err != nil {
			return view, err
		}
		ref, err := (Records{Directory: filepath.Join(stage, "records")}).Put(raw, fact.RecordRef.MediaType)
		if err != nil {
			return view, err
		}
		if err = materializeLinkedRecords(records, fact, stage); err != nil {
			return view, err
		}
		refJSON, _ := json.Marshal(ref)
		recordRoot := view.Directory
		if scope.MountPath != "" {
			recordRoot = scope.MountPath
		}
		var advance any
		if rank, ok := advanceOrder[fact.FactID]; ok {
			advance = rank
		}
		if _, err = derived.Exec("INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?)", i+1, fact.FactID, fact.Kind, fact.Source, fact.Created, string(raw), string(refJSON), filepath.Join(recordRoot, "records", ref.SHA256), advance); err != nil {
			return view, err
		}
	}
	if err = derived.Close(); err != nil {
		return view, err
	}
	f, err := os.OpenFile(filepath.Join(stage, "facts.sqlite"), os.O_RDONLY, 0)
	if err != nil {
		return view, err
	}
	err = errors.Join(f.Chmod(0400), f.Sync(), f.Close())
	if err != nil {
		return view, err
	}
	if err = syncDir(stage); err != nil {
		return view, err
	}
	if err = os.Rename(stage, view.Directory); err != nil {
		if _, e := os.Stat(view.Database); e != nil {
			return view, err
		}
		// Existing snapshots are immutable runtime-owned caches. Verify their
		// database bytes against a freshly rebuilt snapshot before reuse.
		want, e := os.ReadFile(filepath.Join(stage, "facts.sqlite"))
		if e != nil {
			return view, e
		}
		got, e := os.ReadFile(view.Database)
		if e != nil {
			return view, e
		}
		if refFor(want, "application/vnd.sqlite3") != refFor(got, "application/vnd.sqlite3") {
			return view, errors.New("fact view cache changed; discard and rebuild")
		}
		for _, fact := range facts {
			refs, e := toolRecordRefs(fact)
			if e != nil {
				return view, e
			}
			for _, ref := range refs {
				if _, e = (Records{Directory: filepath.Join(view.Directory, "records")}).Get(ref); e != nil {
					return view, e
				}
			}
			if _, e := (Records{Directory: filepath.Join(view.Directory, "records")}).Get(fact.RecordRef); e != nil {
				return view, e
			}
		}
	}
	return view, syncDir(parent)
}
