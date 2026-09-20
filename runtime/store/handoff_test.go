package store

import (
	"fmt"
	"testing"
)

func TestPolicyHandoffSurvivesRestartAndSettlesOnlyNamedInputs(t *testing.T) {
	events, control := fixture(t)
	for _, key := range []string{"one", "two"} {
		if _, err := events.Admit("host", key, "input", Object{}); err != nil {
			t.Fatal(err)
		}
	}
	round, err := control.BeginRound("owner")
	if err != nil {
		t.Fatal(err)
	}
	bound := control.Bind(round)
	late, err := events.Admit("host", "late", "input", Object{})
	if err != nil {
		t.Fatal(err)
	}
	if _, err = bound.CommitCandidate(round.ID, "wrong", "version", []Object{}); err == nil {
		t.Fatal("accepted wrong predecessor")
	}
	cp, err := bound.CommitCandidate(round.ID, "", "version", []Object{})
	if err != nil {
		t.Fatal(err)
	}
	id := cp["checkpoint_id"].(string)
	for _, inputs := range [][]string{{fmt.Sprint("F", late.Seq)}, {"F1", "F1"}, {"F01"}} {
		if _, err = bound.RequestHandoff(round.ID, id, inputs, "wait"); err == nil {
			t.Fatal("accepted unadopted/duplicate input", inputs)
		}
	}
	if _, err = bound.RequestHandoff(round.ID, id, []string{"F1"}, "continue"); err == nil {
		t.Fatal("invented native continuation")
	}
	if _, err = bound.RequestHandoff(round.ID, id, []string{"F1"}, "wait"); err != nil {
		t.Fatal(err)
	}
	pending, err := events.Pending()
	if err != nil || len(pending) != 3 {
		t.Fatal("input settled before fencing", pending, err)
	}
	// Simulate controller death after acceptance, before its fencing confirmation.
	restarted := &Control{Path: control.Path}
	recovery, err := restarted.BeginRecovery("recovery")
	if err != nil {
		t.Fatal(err)
	}
	if err = bound.CompleteHandoff(round.ID); err == nil {
		t.Fatal("old epoch could settle handoff")
	}
	if err = restarted.EndRecovery(recovery); err != nil {
		t.Fatal(err)
	}
	pending, err = events.Pending()
	if err != nil || len(pending) != 2 || pending[0].Seq != 2 || pending[1].Seq != late.Seq {
		t.Fatal(pending, err)
	}
	rounds, err := restarted.Rounds()
	if err != nil || rounds[0].State != "handed_off" || rounds[0].Revision != "version" {
		t.Fatal(rounds, err)
	}
	cp, err = restarted.Checkpoint(cp["checkpoint_id"].(string))
	if err != nil || cp["phase"] != "policy_checkpoint" {
		t.Fatal("original checkpoint changed", cp, err)
	}
}

func TestCandidateRejectsUnknownEffectsAndChangedResourceCopies(t *testing.T) {
	events, control := fixture(t)
	if _, err := events.Admit("host", "one", "input", Object{}); err != nil {
		t.Fatal(err)
	}
	round, err := control.BeginRound("owner")
	if err != nil {
		t.Fatal(err)
	}
	bound := control.Bind(round)
	db, err := OpenDB(control.Path)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if _, err = db.Exec(`INSERT INTO resource_sources VALUES('app','{}')`); err != nil {
		t.Fatal(err)
	}
	if _, err = db.Exec(`INSERT INTO resource_copies VALUES('copy','app','default',2,'{"sha256":"saved","size_bytes":"1","media_type":"text/plain"}')`); err != nil {
		t.Fatal(err)
	}
	if _, err = bound.CommitCandidate(round.ID, "", "version", []Object{}); err == nil {
		t.Fatal("omitted live copy accepted")
	}
	checkpoints, err := control.Checkpoints()
	if err != nil || len(checkpoints) != 0 {
		t.Fatal("failed comparison published checkpoint", checkpoints, err)
	}
	basis, err := bound.HandoffBasis(round.ID)
	if err != nil {
		t.Fatal(err)
	}
	copies := basis["resource_copies"].([]Object)
	if _, err = bound.CommitCandidate(round.ID, "", "version", copies); err != nil {
		t.Fatal(err)
	}
	checkpoints, err = control.Checkpoints()
	if err != nil {
		t.Fatal(err)
	}
	if _, err = bound.PrepareEffect(round.ID, "unknown", "model", Object{"input": "fixed"}); err != nil {
		t.Fatal(err)
	}
	if _, err = bound.CommitCandidate(round.ID, checkpoints[0].ID, "version", copies); err == nil {
		t.Fatal("unknown effect accepted into candidate")
	}
}
