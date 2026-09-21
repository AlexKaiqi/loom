package opensandbox

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

const testImage = "python@sha256:97bb82da414a3216a18949f7d4a9c2a2860296027a05e2dcdcb6a9801d019fc5"

func TestUnavailableServiceNeverRetries(t *testing.T) {
	var count atomic.Int32
	base := t.TempDir()
	content := filepath.Join(base, "content")
	os.Mkdir(content, 0700)
	artifacts := filepath.Join(base, "artifacts")
	var planned *Checkpoint
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		count.Add(1)
		if planned == nil || planned.Phase != "planned" || planned.Binding.ServiceID != "test-sandbox" {
			t.Error("destination was not checkpointed before HTTP")
		}
		input, err := os.ReadFile(filepath.Join(artifacts, "input.tar"))
		if err != nil || len(input) == 0 {
			t.Error("input missing before dispatch", err)
		}
		w.WriteHeader(http.StatusServiceUnavailable)
		fmt.Fprint(w, `{"code":"synthetic","message":"controlled failure"}`)
	}))
	defer server.Close()
	c, err := New(Config{ServiceID: "test-sandbox", Endpoint: server.URL, APIKey: "synthetic-secret", Image: testImage})
	if err != nil {
		t.Fatal(err)
	}
	result, err := c.Execute(context.Background(), Request{OperationID: "test-one", Target: "surface", Script: "must not execute", Timeout: time.Second, Directory: content, ArtifactsDir: artifacts}, func(p Checkpoint) error { planned = &p; return nil })
	if err != nil || result.State != "unknown" || count.Load() != 1 {
		t.Fatal(result, err, count.Load())
	}
	var options Options
	if err = json.Unmarshal([]byte(result.Binding.OptionsJSON), &options); err != nil {
		t.Fatal(err)
	}
	if result.Binding != c.Binding() || planned.Binding != result.Binding || result.Binding.Provider != Provider || options.Image != testImage || options.Profile != "code" || options.CPU != "1" || options.Memory != "512Mi" || options.LeaseSeconds != 600 || options.RequestTimeoutSeconds != 30 {
		t.Fatal(result.Binding, planned)
	}

	data, err := json.Marshal(result)
	if err != nil || strings.Contains(string(data), "synthetic-secret") {
		t.Fatal("binding leaked secret", err)
	}
}

func TestPlannedPersistenceFailurePreventsHTTP(t *testing.T) {
	var count atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { count.Add(1) }))
	defer server.Close()
	c, err := New(Config{ServiceID: "test-sandbox", Endpoint: server.URL, APIKey: "secret", Image: testImage})
	if err != nil {
		t.Fatal(err)
	}
	base := t.TempDir()
	content := filepath.Join(base, "content")
	if err := os.Mkdir(content, 0700); err != nil {
		t.Fatal(err)
	}
	_, err = c.Execute(context.Background(), Request{OperationID: "must-not-dispatch", Target: "surface", Timeout: time.Second, Directory: content, ArtifactsDir: filepath.Join(base, "artifacts")}, func(p Checkpoint) error {
		if p.Phase != "planned" || p.SandboxID != "" || p.Binding != c.Binding() {
			t.Fatal(p)
		}
		return errors.New("durable checkpoint unavailable")
	})
	if err == nil || count.Load() != 0 {
		t.Fatal(err, count.Load())
	}
}

func TestRemoteReferenceCannotMoveToAnotherDestination(t *testing.T) {
	var count atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { count.Add(1) }))
	defer server.Close()
	c, err := New(Config{ServiceID: "test-sandbox", Endpoint: server.URL, APIKey: "secret", Image: testImage})
	if err != nil {
		t.Fatal(err)
	}
	for _, mutate := range []func(*Binding){func(b *Binding) { b.ServiceID = "other-service" }, func(b *Binding) { b.Endpoint = "https://127.0.0.1:443" }, func(b *Binding) { b.Endpoint += "/wrong" }} {
		expected := c.Binding()
		mutate(&expected)
		if _, err := c.Query(context.Background(), "original-sandbox", "session/run", expected); err == nil {
			t.Fatal("query accepted changed destination")
		}
		if _, err := c.Cancel(context.Background(), "original-sandbox", "session/run", expected); err == nil {
			t.Fatal("cancel accepted changed destination")
		}
	}
	if count.Load() != 0 {
		t.Fatal("mismatched binding touched network", count.Load())
	}
}
func TestLostCreatedCheckpointKeepsID(t *testing.T) {
	var count atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		count.Add(1)
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprint(w, `{"id":"remote-created","status":{"state":"Running"},"createdAt":"2026-09-19T00:00:00Z"}`)
	}))
	defer server.Close()
	c, _ := New(Config{ServiceID: "test-sandbox", Endpoint: server.URL, APIKey: "synthetic-secret", Image: testImage})
	base := t.TempDir()
	content := filepath.Join(base, "content")
	os.Mkdir(content, 0700)
	result, err := c.Execute(context.Background(), Request{OperationID: "created", Target: "surface", Timeout: time.Second, Directory: content, ArtifactsDir: filepath.Join(base, "artifacts")}, func(p Checkpoint) error {
		if p.Phase == "planned" {
			return nil
		}
		if p.SandboxID != "remote-created" {
			t.Fatal(p)
		}
		return errors.New("synthetic-secret callback loss")
	})
	if err != nil || result.State != "unknown" || result.SandboxID != "remote-created" || result.Released || count.Load() != 1 || strings.Contains(result.Error, "synthetic-secret") {
		t.Fatal(result, err, count.Load())
	}
}
func TestReleaseUsesOnlyLifecycle(t *testing.T) {
	var path string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { path = r.Method + " " + r.URL.Path; w.WriteHeader(204) }))
	defer server.Close()
	c, _ := New(Config{ServiceID: "test-sandbox", Endpoint: server.URL, APIKey: "key", Image: testImage})
	if err := c.Release(context.Background(), "dead-execd"); err != nil {
		t.Fatal(err)
	}
	if path != "DELETE /v1/sandboxes/dead-execd" {
		t.Fatal(path)
	}
}
func TestInputArtifactFailurePreventsDispatch(t *testing.T) {
	var count atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { count.Add(1) }))
	defer server.Close()
	c, _ := New(Config{ServiceID: "test-sandbox", Endpoint: server.URL, APIKey: "key", Image: testImage})
	base := t.TempDir()
	content := filepath.Join(base, "content")
	os.Mkdir(content, 0700)
	artifacts := filepath.Join(base, "artifacts")
	os.MkdirAll(filepath.Join(artifacts, "input.tar"), 0700)
	_, err := c.Execute(context.Background(), Request{OperationID: "input-failure", Target: "surface", Timeout: time.Second, Directory: content, ArtifactsDir: artifacts}, nil)
	if err == nil || count.Load() != 0 {
		t.Fatal(err, count.Load())
	}
}
