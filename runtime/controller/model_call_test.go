package controller

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
)

func TestModelCustodyIsOwnedByHostBeforeAndAfterDispatch(t *testing.T) {
	c := apiFixture(t)
	c.runtime = &Runtime{}
	calls := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		effects, err := c.work.Control.Effects(c.round.ID)
		if err != nil || len(effects) != 1 || effects[0].DispatchState != "attempted" {
			t.Error("HTTP before durable admission", effects, err)
		}
		w.Header().Set("Content-Type", "text/event-stream")
		raw, _ := json.Marshal(Object{"id": "fixture", "object": "chat.completion.chunk", "choices": []Object{{"index": 0, "delta": Object{"role": "assistant", "content": "received"}, "finish_reason": "stop"}}})
		fmt.Fprintf(w, "data: %s\n\ndata: [DONE]\n\n", raw)
	}))
	defer server.Close()
	worker, _ := filepath.Abs("../../components/model-resource-hub/model-invocation/pi/worker.mjs")
	c.runtime.ModelCommand = []string{"node", worker}
	c.runtime.APIKey = "test-only-key"
	c.runtime.Model = Object{"id": "fixture", "api": "openai-completions", "provider": "fixture", "input": []string{"text"}, "reasoning": false, "baseUrl": server.URL, "maxTokens": 64, "contextWindow": 4096, "cost": Object{"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}
	c.basePlan = Object{"timeout": 10}
	result, err := c.invokeModel(context.Background(), Object{"model": modelSemantics(c.runtime.Model), "context": Object{"messages": []Object{{"role": "user", "content": "hello", "timestamp": 0}}}, "options": Object{"maxTokens": 64}, "timeoutMs": 10000})
	if err != nil {
		t.Fatal(err)
	}
	effects, err := c.work.Control.Effects(c.round.ID)
	if err != nil || len(effects) != 1 || effects[0].Status != "completed" || c.modelEffect != nil || result["role"] != "assistant" || result["stopReason"] != "stop" || calls != 1 {
		t.Fatal("result returned before terminal custody", effects, result, err)
	}
}
func TestUnknownModelDispatchCannotBeRepeatedByDriver(t *testing.T) {
	c := apiFixture(t)
	c.runtime = &Runtime{}
	c.runtime.Model = Object{"id": "fixture"}
	c.runtime.ModelCommand = []string{"/usr/bin/false"}
	c.basePlan = Object{"timeout": 1}
	request := Object{"context": Object{"messages": []any{}}, "options": Object{}, "timeoutMs": 1000}
	if _, err := c.invokeModel(context.Background(), request); err == nil {
		t.Fatal("dead worker succeeded")
	}
	if _, err := c.invokeModel(context.Background(), request); err == nil {
		t.Fatal("unconfirmed dispatch replayed")
	}
	effects, err := c.work.Control.Effects(c.round.ID)
	if err != nil || len(effects) != 1 || effects[0].Status == "completed" {
		t.Fatal(effects, err)
	}
}
