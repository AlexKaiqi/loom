package controller

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"path/filepath"
	"testing"

	"loom/runtime/rpc"
	"loom/runtime/store"
	"loom/runtime/work"
)

func apiFixture(t *testing.T) *run {
	t.Helper()
	root := t.TempDir()
	path := filepath.Join(root, ".loom", "state.sqlite")
	if err := store.Initialize(path); err != nil {
		t.Fatal(err)
	}
	events := &store.Events{Path: path}
	control := &store.Control{Path: path}
	if _, err := events.Admit("host", "first", "work.text", Object{"text": "hello"}); err != nil {
		t.Fatal(err)
	}
	round, err := control.BeginRound("owner")
	if err != nil {
		t.Fatal(err)
	}
	bound := control.Bind(round)
	return &run{work: &work.Work{Path: root, ID: "test-work", DBPath: path, Control: bound, Events: &store.Events{Path: path, Control: bound}}, round: round}
}

func apiCall(c *run, method string, p Object) (any, error) {
	p["protocol_version"], p["schema_version"] = "loom/1", 1
	raw, err := json.Marshal(p)
	if err != nil {
		return nil, err
	}
	return c.harnessCall(context.Background(), method, raw)
}

func requireAPIKind(t *testing.T, err error, kind string) {
	t.Helper()
	var protocol *rpc.Error
	if !errors.As(err, &protocol) || protocol.Kind != kind {
		t.Fatalf("want %s, got %v", kind, err)
	}
}

func TestHarnessRecordAuthorityAndProjectionBoundary(t *testing.T) {
	c := apiFixture(t)
	c.api.basis = projectionBasis{ContentRef: "fixed-content", ViewID: "fixed-view", Watermark: "1", Resources: Object{}}
	private, err := (store.Records{Directory: c.work.ArtifactsDir()}).Put([]byte("private object"), "text/plain")
	if err != nil {
		t.Fatal(err)
	}
	_, err = apiCall(c, "record.get", Object{"record_ref": private, "offset": "0", "length": 100})
	requireAPIKind(t, err, "permission_denied")
	// A matching digest is not enough to acquire authority through a forged ref.
	value, err := apiCall(c, "record.put", Object{"media_type": "application/json", "data_base64": base64.StdEncoding.EncodeToString([]byte(`{"context":{"messages":[]},"content_version":"forged"}`))})
	if err != nil {
		t.Fatal(err)
	}
	ref := value.(store.RecordRef)
	forged := ref
	forged.SizeBytes = "1"
	_, err = apiCall(c, "record.get", Object{"record_ref": forged, "offset": "0", "length": 100})
	requireAPIKind(t, err, "permission_denied")
	_, err = apiCall(c, "projection.publish", Object{"record_ref": ref, "content_version": "wrong", "view_id": "fixed-view", "harness_ref": c.round.HarnessRef})
	requireAPIKind(t, err, "baseline_conflict")
	value, err = apiCall(c, "projection.publish", Object{"record_ref": ref, "content_version": "fixed-content", "view_id": "fixed-view", "harness_ref": c.round.HarnessRef})
	if err != nil {
		t.Fatal(err)
	}
	published := value.(Object)["projection_ref"].(store.RecordRef)
	raw, err := (store.Records{Directory: c.work.ArtifactsDir()}).Get(published)
	if err != nil {
		t.Fatal(err)
	}
	var projection Object
	if err = json.Unmarshal(raw, &projection); err != nil {
		t.Fatal(err)
	}
	if projection["content_version"] != "fixed-content" || projection["fact_watermark"] != "1" {
		t.Fatal(projection)
	}
	// Inspect the real ledger, not the operation's claimed success.
	db, err := store.OpenDB(c.work.DBPath)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	var count int
	if err = db.QueryRow("SELECT count(*) FROM events WHERE kind='projection.published'").Scan(&count); err != nil || count != 1 {
		t.Fatal(count, err)
	}
	if _, err = apiCall(c, "projection.publish", Object{"record_ref": ref, "content_version": "fixed-content", "view_id": "fixed-view", "harness_ref": c.round.HarnessRef}); err != nil {
		t.Fatal(err)
	}
	if err = db.QueryRow("SELECT count(*) FROM events WHERE kind='projection.published'").Scan(&count); err != nil || count != 1 {
		t.Fatal("idempotence", count, err)
	}
	_, err = apiCall(c, "model.start", Object{"projection_ref": private, "request_key": "one"})
	requireAPIKind(t, err, "permission_denied")
	value, err = apiCall(c, "model.start", Object{"projection_ref": published, "request_key": "one"})
	if err != nil || value.(Object)["accepted"] != true {
		t.Fatal(value, err)
	}
	rounds, err := c.work.Control.Rounds()
	if err != nil {
		t.Fatal(err)
	}
	if rounds[0].Checkpoint["phase"] != "model_ready" || object(rounds[0].Checkpoint["plan"])["content_version"] != "fixed-content" {
		t.Fatal(rounds)
	}
	// Acceptance is durable, but it is neither a model dispatch nor a result.
	if err = db.QueryRow("SELECT count(*) FROM effects").Scan(&count); err != nil || count != 0 {
		t.Fatal(count, err)
	}
	_, err = apiCall(c, "model.start", Object{"projection_ref": published, "request_key": "other"})
	requireAPIKind(t, err, "identity_conflict")
	if _, err = (&store.Control{Path: c.work.DBPath}).BeginRecovery("replacement"); err != nil {
		t.Fatal(err)
	}
	_, err = apiCall(c, "record.put", Object{"media_type": "text/plain", "data_base64": ""})
	requireAPIKind(t, err, "stale_epoch")
}
