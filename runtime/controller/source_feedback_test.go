package controller

import (
	"crypto/sha256"
	"encoding/hex"
	"loom/runtime/authority"
	"loom/runtime/policy"
	"loom/runtime/store"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSourceAttributionRejectsHiddenFactsAndChangedFileBytes(t *testing.T) {
	c := apiFixture(t)
	stage := t.TempDir()
	c.domain = &workDomain{binding: authority.Domain{Staging: stage}}
	root := filepath.Join(stage, "sources/version/surface")
	if err := os.MkdirAll(root, 0700); err != nil {
		t.Fatal(err)
	}
	content := []byte("fixed template")
	if err := os.WriteFile(filepath.Join(root, "main.md"), content, 0400); err != nil {
		t.Fatal(err)
	}
	view, err := c.work.Events.OpenView(store.ViewScope{WorkID: c.work.ID, MountPath: "/facts"}, 1)
	if err != nil {
		t.Fatal(err)
	}
	c.api.views = map[string]boundFactView{view.ID: {FactView: view}}
	basis := projectionBasis{ContentRef: "version", ViewID: view.ID}
	sum := sha256.Sum256(content)
	source := Object{"kind": "template", "path": "surface/main.md", "sha256": hex.EncodeToString(sum[:]), "utf8_bytes": 14}
	candidate := Object{"sources": []Object{source, Object{"kind": "facts", "fact_ids": []any{"F1"}, "utf8_bytes": 5}}}
	if err = c.validateSources(candidate, basis); err != nil {
		t.Fatal(err)
	}
	source["sha256"] = strings.Repeat("0", 64)
	if err = c.validateSources(candidate, basis); err == nil {
		t.Fatal("forged file attribution accepted")
	}
	source["sha256"] = hex.EncodeToString(sum[:])
	source["path"] = "../private"
	if err = c.validateSources(candidate, basis); err == nil {
		t.Fatal("escaped attribution accepted")
	}
	source["path"] = "surface/main.md"
	candidate["sources"] = []Object{Object{"kind": "facts", "fact_ids": []any{"F999"}, "utf8_bytes": 1}}
	if err = c.validateSources(candidate, basis); err == nil {
		t.Fatal("ungranted fact attribution accepted")
	}
}
func TestBudgetFeedbackPersistsSourceAndEstimateLineage(t *testing.T) {
	c := apiFixture(t)
	c.policy = &policy.Client{}
	c.runtime = &Runtime{Model: Object{"id": "fixture", "contextWindow": 20000, "maxTokens": 512, "headers": Object{"secret": "must stay private"}}}
	c.projectionPlan = Object{"template_sha256": "template-v1", "sources": []Object{}, "selection": Object{"fact_ids": []string{"F1"}}, "content_version": "content-v1"}
	input := Object{"systemPrompt": "policy", "messages": []Object{{"role": "user", "content": "hello"}}}
	first, err := c.withBudget(input, Object{"maxTokens": 128})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(first["systemPrompt"].(string), "details_fact_id") || input["systemPrompt"] != "policy" {
		t.Fatal(first, input)
	}
	estimate := c.budgetEstimate
	ref := c.budgetRef
	c.lastTurn = Object{"message": Object{"usage": Object{"input": 7, "output": 3}}}
	input["messages"] = []Object{{"role": "user", "content": strings.Repeat("x", 500)}}
	if _, err = c.withBudget(input, Object{"maxTokens": 128}); err != nil {
		t.Fatal(err)
	}
	facts, err := c.work.Events.Events(0)
	if err != nil || len(facts) != 3 {
		t.Fatal(facts, err)
	}
	saved := facts[2].Payload
	delta, _ := number(saved["input_estimate_delta"])
	if int(delta) != c.budgetEstimate-estimate || object(saved["previous_feedback_ref"])["sha256"] != ref["sha256"] {
		t.Fatal(saved)
	}
	if object(saved["model_semantics"])["headers"] != nil || saved["template_sha256"] != "template-v1" || object(saved["previous_usage"])["input"] == nil {
		t.Fatal(saved)
	}
	db, err := store.OpenDB(c.work.DBPath)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	var n int
	if err = db.QueryRow("SELECT count(*) FROM effects").Scan(&n); err != nil || n != 0 {
		t.Fatal("feedback dispatched model", n, err)
	}
}
