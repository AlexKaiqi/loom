package store

import (
	"database/sql"
	"os"
	"path/filepath"
	"testing"
)

func TestAuthorizedFactSnapshotRebuildAndInputBoundary(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "state.sqlite")
	if err := Initialize(path); err != nil {
		t.Fatal(err)
	}
	e := Events{Path: path}
	private, err := e.Admit("private", "1", "work.message", Object{"text": "私人生日"})
	if err != nil {
		t.Fatal(err)
	}
	visible, err := e.Admit("host", "2", "work.message", Object{"text": "生日已更正为五月"})
	if err != nil {
		t.Fatal(err)
	}
	view, err := e.OpenView(ViewScope{WorkID: "work", FactIDs: []string{visible.FactID}}, visible.Seq)
	if err != nil {
		t.Fatal(err)
	}
	db, err := sql.Open("sqlite", "file:"+view.Database+"?mode=ro&immutable=1")
	if err != nil {
		t.Fatal(err)
	}
	var n int
	var id, rawPath, coverage string
	if err = db.QueryRow("SELECT count(*) FROM facts").Scan(&n); err != nil || n != 1 {
		t.Fatal(n, err)
	}
	if err = db.QueryRow("SELECT fact_id,record_path FROM facts WHERE instr(search_text,'生日')>0").Scan(&id, &rawPath); err != nil || id != visible.FactID {
		t.Fatal(id, err)
	}
	if err = db.QueryRow("SELECT text_coverage FROM view_meta").Scan(&coverage); err != nil || coverage == "" {
		t.Fatal(coverage, err)
	}
	if _, err = db.Exec("DELETE FROM facts"); err == nil {
		t.Fatal("read-only view writable")
	}
	if err = db.QueryRow("SELECT count(*) FROM sqlite_master WHERE name IN ('rounds','events','effects','pending')").Scan(&n); err != nil || n != 0 {
		t.Fatal("control tables exposed", n, err)
	}
	db.Close()
	if _, err = os.Stat(rawPath); err != nil {
		t.Fatal(err)
	}
	if _, err = os.Stat(filepath.Join(view.Directory, "records", private.RecordRef.SHA256)); !os.IsNotExist(err) {
		t.Fatal("unauthorized original exposed")
	}
	if _, err = e.OpenView(ViewScope{WorkID: "work"}, visible.Seq+1); err == nil {
		t.Fatal("stale watermark accepted")
	}
	if err = os.RemoveAll(filepath.Join(root, "views")); err != nil {
		t.Fatal(err)
	}
	rebuilt, err := e.OpenView(ViewScope{WorkID: "work", FactIDs: []string{visible.FactID}}, visible.Seq)
	if err != nil || rebuilt.ID != view.ID {
		t.Fatal(rebuilt, err)
	}
	again, err := e.OpenView(ViewScope{WorkID: "work", FactIDs: []string{visible.FactID}}, visible.Seq)
	if err != nil || again.ID != view.ID {
		t.Fatal(again, err)
	}
	pending, err := e.Pending()
	if err != nil || len(pending) != 2 {
		t.Fatal("view consumed inputs", pending, err)
	}
}

func TestFactViewBindsAdoptionOrderWithoutChangingAdmissionOrder(t *testing.T) {
	e, control := fixture(t)
	first, err := e.Admit("host", "first", "work.message", Object{"text": "first"})
	if err != nil {
		t.Fatal(err)
	}
	round, err := control.BeginRound("first-owner")
	if err != nil {
		t.Fatal(err)
	}
	late, err := e.Admit("host", "late", "work.message", Object{"text": "late"})
	if err != nil {
		t.Fatal(err)
	}
	reply, err := e.Append("model-adapter", "reply", "model.message", Object{"round_id": round.ID, "message": Object{"role": "assistant"}})
	if err != nil {
		t.Fatal(err)
	}
	before, err := e.OpenView(ViewScope{WorkID: "test"}, reply.Seq)
	if err != nil {
		t.Fatal(err)
	}
	if err = control.FinishRound(round.ID, "first-version"); err != nil {
		t.Fatal(err)
	}
	if _, err = control.BeginRound("next-owner"); err != nil {
		t.Fatal(err)
	}
	after, err := e.OpenView(ViewScope{WorkID: "test"}, reply.Seq)
	if err != nil {
		t.Fatal(err)
	}
	if before.Watermark != after.Watermark || before.ID == after.ID {
		t.Fatal("adoption changed without changing immutable view identity", before, after)
	}
	db, err := sql.Open("sqlite", "file:"+after.Database+"?mode=ro&immutable=1")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	for i, expected := range []struct {
		id      string
		advance int
	}{{first.FactID, 1}, {late.FactID, 2}, {reply.FactID, 1}} {
		var id string
		var rank int
		if err = db.QueryRow("SELECT fact_id,advance_ordinal FROM facts WHERE ordinal=?", i+1).Scan(&id, &rank); err != nil || id != expected.id || rank != expected.advance {
			t.Fatal("admission/adoption order incorrect", id, rank, err)
		}
	}
	limited, err := e.OpenView(ViewScope{WorkID: "test", FactIDs: []string{late.FactID}}, reply.Seq)
	if err != nil {
		t.Fatal(err)
	}
	only, err := sql.Open("sqlite", "file:"+limited.Database+"?mode=ro&immutable=1")
	if err != nil {
		t.Fatal(err)
	}
	defer only.Close()
	var ordinal, advance int
	if err = only.QueryRow("SELECT ordinal,advance_ordinal FROM facts").Scan(&ordinal, &advance); err != nil || ordinal != 1 || advance != 1 {
		t.Fatal("scoped ranks exposed hidden advances", ordinal, advance, err)
	}
}

func TestToolBodyReferencesAreReadableButUserRefsDoNotGrantAccess(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "state.sqlite")
	if err := Initialize(path); err != nil {
		t.Fatal(err)
	}
	records := Records{Directory: filepath.Join(root, "records")}
	full, err := records.Put([]byte("complete large original output"), "text/plain")
	if err != nil {
		t.Fatal(err)
	}
	hidden, err := records.Put([]byte("private hidden content"), "text/plain")
	if err != nil {
		t.Fatal(err)
	}
	fullObject := Object{"sha256": full.SHA256, "size_bytes": full.SizeBytes, "media_type": full.MediaType}
	hiddenObject := Object{"sha256": hidden.SHA256, "size_bytes": hidden.SizeBytes, "media_type": hidden.MediaType}
	events := Events{Path: path}
	actual, err := events.Append("model-adapter", "actual", "tool.result", Object{"message": Object{"role": "toolResult", "details": Object{"stdout": Object{"record_ref": fullObject}}}})
	if err != nil {
		t.Fatal(err)
	}
	forged, err := events.Admit("host", "forged", "tool.result", Object{"message": Object{"role": "toolResult", "details": Object{"stdout": Object{"record_ref": hiddenObject}}}})
	if err != nil {
		t.Fatal(err)
	}
	view, err := events.OpenView(ViewScope{WorkID: "test", FactIDs: []string{actual.FactID, forged.FactID}}, forged.Seq)
	if err != nil {
		t.Fatal(err)
	}
	got, err := (Records{Directory: filepath.Join(view.Directory, "records")}).Get(full)
	if err != nil || string(got) != "complete large original output" {
		t.Fatal("full native body unavailable", err)
	}
	if _, err = os.Stat(filepath.Join(view.Directory, "records", hidden.SHA256)); !os.IsNotExist(err) {
		t.Fatal("payload forged hidden-record access", err)
	}
}
