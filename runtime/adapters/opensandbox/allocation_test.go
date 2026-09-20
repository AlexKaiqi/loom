package opensandbox

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/url"
	"sync/atomic"
	"testing"
)

func TestAllocationReconciliationUsesNativeFilterWithoutCreateReplay(t *testing.T) {
	var creates atomic.Int32
	var mode atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.Method == "POST" {
			creates.Add(1)
			var body struct {
				Metadata map[string]string `json:"metadata"`
			}
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				t.Error(err)
			}
			if body.Metadata["loom.operation"] != "original-request" || body.Metadata["loom.target"] != "backend" {
				t.Error(body)
			}
			w.WriteHeader(503)
			fmt.Fprint(w, `{"message":"response lost"}`)
			return
		}
		if r.Method != "GET" {
			t.Error("unexpected mutation", r.Method)
		}
		if r.URL.Path == "/v1/sandboxes/missing" {
			w.WriteHeader(404)
			fmt.Fprint(w, `{"message":"gone"}`)
			return
		}
		metadata, err := url.ParseQuery(r.URL.Query().Get("metadata"))
		if err != nil || metadata.Get("loom.operation") != "original-request" {
			t.Error("unscoped lookup", r.URL)
		}
		switch mode.Load() {
		case 0:
			fmt.Fprint(w, `{"items":[],"pagination":{"totalItems":0}}`)
		case 1:
			fmt.Fprint(w, `{"items":[{"id":"original","metadata":{"loom.operation":"original-request"}}],"pagination":{"totalItems":1}}`)
		case 2:
			fmt.Fprint(w, `{"items":[{"id":"wrong","metadata":{"loom.operation":"other-request"}}],"pagination":{"totalItems":1}}`)
		default:
			fmt.Fprint(w, `{"items":[{"id":"original","metadata":{"loom.operation":"original-request"}}],"pagination":{"totalItems":2,"hasNextPage":true}}`)
		}
	}))
	defer server.Close()
	c, err := New(Config{ServiceID: "fixture", Endpoint: server.URL, APIKey: "secret", Image: testImage})
	if err != nil {
		t.Fatal(err)
	}
	if _, err = c.Acquire(context.Background(), "original-request", "backend"); err == nil {
		t.Fatal("lost create reported success")
	}
	empty, err := c.InspectAllocation(context.Background(), "original-request", "")
	if err != nil || empty.State != "unknown" {
		t.Fatal(empty, err)
	}
	mode.Store(1)
	found, err := c.InspectAllocation(context.Background(), "original-request", "")
	if err != nil || found.ID != "original" {
		t.Fatal(found, err)
	}
	mode.Store(2)
	if _, err = c.InspectAllocation(context.Background(), "original-request", ""); err == nil {
		t.Fatal("foreign allocation accepted")
	}
	mode.Store(3)
	duplicate, err := c.InspectAllocation(context.Background(), "original-request", "")
	if err != nil || duplicate.State != "unknown" {
		t.Fatal(duplicate, err)
	}
	gone, err := c.InspectAllocation(context.Background(), "original-request", "missing")
	if err != nil || gone.State != "absent" {
		t.Fatal(gone, err)
	}
	if creates.Load() != 1 {
		t.Fatal("create replayed", creates.Load())
	}
}
