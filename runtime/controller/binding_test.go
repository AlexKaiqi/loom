package controller

import "testing"

func TestContinuationResolvesNewTransportWithoutChangingDeclaredModel(t *testing.T) {
	current := Object{"id": "fixed", "api": "openai-completions", "provider": "fixture", "baseUrl": "https://new.example/v1", "headers": Object{"Authorization": "new-secret"}, "contextWindow": float64(100)}
	r := Runtime{Model: current}
	prior := Object{"id": "fixed", "api": "openai-completions", "provider": "fixture", "baseUrl": "https://old.example/v1", "contextWindow": 100}
	rebound, err := r.bindModel(prior)
	if err != nil {
		t.Fatal(err)
	}
	if rebound["baseUrl"] != current["baseUrl"] || object(rebound["headers"])["Authorization"] != "new-secret" {
		t.Fatal("continuation retained old host transport")
	}
	if prior["baseUrl"] != "https://old.example/v1" || prior["headers"] != nil {
		t.Fatal("durable checkpoint was mutated")
	}
	prior["id"] = "undeclared"
	if _, err = r.bindModel(prior); err == nil {
		t.Fatal("undeclared model accepted")
	}
	prior["id"] = "fixed"
	prior["contextWindow"] = 999
	if _, err = r.bindModel(prior); err == nil {
		t.Fatal("undeclared model capabilities accepted")
	}
}
