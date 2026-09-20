package controller

import (
	"loom/runtime/authority"
	"loom/runtime/execution"
	"loom/runtime/store"
	"os"
	"path/filepath"
	"testing"
)

func TestPolicyTurnPublicationIsImmutableAcrossCallbacks(t *testing.T) {
	c := apiFixture(t)
	stage := t.TempDir()
	c.domain = &workDomain{binding: authority.Domain{Staging: stage}, scope: &execution.Scope{UID: os.Getuid(), GID: os.Getgid()}}
	turn := Object{"message": Object{"stopReason": "toolUse"}, "context": Object{"messages": []Object{{"role": "user", "content": "fixed native bytes"}}}}
	first, err := c.policyTurn(turn)
	if err != nil {
		t.Fatal(err)
	}
	ref := first["turn_ref"].(store.RecordRef)
	path := filepath.Join(stage, "sources", ref.SHA256)
	before, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = c.policyTurn(turn); err != nil {
		t.Fatal(err)
	}
	after, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if !os.SameFile(before, after) || !before.ModTime().Equal(after.ModTime()) {
		t.Fatal("previously published source was rewritten")
	}
	if err = os.Chmod(path, 0600); err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(path, []byte("corrupt"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = c.policyTurn(turn); err == nil {
		t.Fatal("corrupt published source silently repaired")
	}
}
