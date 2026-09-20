package model

import (
	"context"
	"encoding/json"
	"fmt"
	"loom/runtime/rpc"
	"loom/runtime/store"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestLargeNativeContextsAndResultsUseRecordsAcrossRealPi(t *testing.T) {
	node, err := exec.LookPath("node")
	if err != nil {
		t.Fatal("Node 24 is required for model composition checks", err)
	}
	worker, err := filepath.Abs("../../services/model/worker.mjs")
	if err != nil {
		t.Fatal(err)
	}
	input := strings.Repeat("long-context-", 360000)
	output := strings.Repeat("actual-output-", 320000)
	var calls, admitted atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := calls.Add(1)
		if admitted.Load() != n {
			t.Error("HTTP before native request custody", n, admitted.Load())
		}
		var request map[string]any
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Error(err)
		}
		text, _ := json.Marshal(request["messages"])
		if !strings.Contains(string(text), input) {
			t.Error("context bytes missing")
		}
		if r.Header.Get("Authorization") != "Bearer private-model-key" {
			t.Error("credential not bound")
		}
		chunk := func(delta any, finish any) {
			raw, _ := json.Marshal(map[string]any{"id": "native", "object": "chat.completion.chunk", "created": 1, "model": "fixture", "choices": []any{map[string]any{"index": 0, "delta": delta, "finish_reason": finish}}})
			fmt.Fprintf(w, "data: %s\n\n", raw)
		}
		w.Header().Set("Content-Type", "text/event-stream")
		if n == 1 {
			chunk(map[string]any{"role": "assistant", "tool_calls": []any{map[string]any{"index": 0, "id": "call-one", "type": "function", "function": map[string]any{"name": "probe", "arguments": "{}"}}}}, nil)
			chunk(map[string]any{}, "tool_calls")
		} else {
			chunk(map[string]any{"role": "assistant", "content": output}, nil)
			chunk(map[string]any{}, "stop")
		}
		fmt.Fprint(w, "data: [DONE]\n\n")
	}))
	defer server.Close()
	records := t.TempDir()
	native := Object{"id": "fixture", "name": "Fixture", "api": "openai-completions", "provider": "fixture", "baseUrl": server.URL, "reasoning": false, "input": []string{"text"}, "contextWindow": 10000000, "maxTokens": 4096, "cost": Object{"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}
	ctx := Object{"systemPrompt": "Use the supplied context", "messages": []Object{{"role": "user", "content": input, "timestamp": 0}}}
	callbacks := Callbacks{Event: func(event Object) error {
		if event["type"] == "model_request" {
			admitted.Add(1)
		}
		return nil
	},
		Continue: func(_ context.Context, turn Object) (bool, error) { return true, nil },
		Prepare: func(_ context.Context, turn Object) (Object, error) {
			return Object{"context": turn["context"], "model": native}, nil
		},
		Tool: func(context.Context, string, Object, string) (Object, error) {
			return Object{"content": []Object{{"type": "text", "text": "observed"}}, "isError": false}, nil
		},
	}
	messages, err := Run(context.Background(), []string{node, worker}, Request{Session: rpc.Session{RecordDirectory: records}, Context: ctx, Model: native, APIKey: "private-model-key", Options: Object{"maxTokens": 4096}, Tools: []Object{{"name": "probe", "description": "test tool", "parameters": Object{"type": "object", "properties": Object{}}}}, MaxTurns: 2, Timeout: 30 * time.Second}, callbacks)
	if err != nil {
		t.Fatal(err)
	}
	if calls.Load() != 2 || len(messages) != 3 {
		t.Fatal(calls.Load(), len(messages))
	}
	serialized, err := json.Marshal(messages[2])
	if err != nil || !strings.Contains(string(serialized), output) {
		t.Fatal("native result truncated", err)
	}
	files, err := os.ReadDir(records)
	if err != nil {
		t.Fatal(err)
	}
	if len(files) < 4 {
		t.Fatal("native exchange did not use records", len(files))
	}
	for _, file := range files {
		raw, err := os.ReadFile(filepath.Join(records, file.Name()))
		if err != nil {
			t.Fatal(err)
		}
		if strings.Contains(string(raw), "private-model-key") {
			t.Fatal("credential written to portable record")
		}
	}
}

func TestReferencedCallbackCannotConcealSessionIdentity(t *testing.T) {
	records := store.Records{Directory: t.TempDir()}
	ref, err := records.Put([]byte(`{"epoch":"2","name":"bash"}`), "application/json")
	if err != nil {
		t.Fatal(err)
	}
	envelope, err := json.Marshal(Object{"payload_ref": ref})
	if err != nil {
		t.Fatal(err)
	}
	var p Object
	if err = dereference(records, envelope, &p); err != nil {
		t.Fatal(err)
	}
	session := rpc.Session{WorkID: "work", RoundID: "round", Epoch: "3", Operations: []string{"tool.execute"}}
	if err = session.AuthorizePayload("tool.execute", p); err == nil {
		t.Fatal("stale epoch concealed in record")
	}
	ambiguous, err := json.Marshal(Object{"payload_ref": ref, "epoch": "3"})
	if err != nil {
		t.Fatal(err)
	}
	if err = dereference(records, ambiguous, &p); err == nil {
		t.Fatal("ambiguous reference envelope accepted")
	}
}
