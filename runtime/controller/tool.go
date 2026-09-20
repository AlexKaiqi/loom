package controller

import (
	"context"
	"errors"
	"fmt"
	"loom/runtime/authority"
	"loom/runtime/sandbox"
	"loom/runtime/store"
	"math"
	"path/filepath"
	"strings"
	"time"
	"unicode/utf8"
)

func (c *run) tool(ctx context.Context, name string, args Object, callID string) (answer Object, err error) {
	// Pi's tool execution is sequential; the mutex also protects custody if a
	// malformed/custom worker sends concurrent callbacks.
	c.mu.Lock()
	defer c.mu.Unlock()
	r, w := c.runtime, c.work
	if err = r.Authority.Authorize(w); err != nil {
		return nil, err
	}
	if err = c.policy.ValidateTool(name, args); err != nil {
		return nil, err
	}
	target, _ := args["target"].(string)
	directory := w.Surface
	switch target {
	case "surface":
	case "userspace":
		directory, err = r.Authority.Userspace(w)
		if err != nil {
			return nil, err
		}
	default:
		return nil, errors.New("ungranted file domain")
	}
	old, err := authority.StatIdentity(directory)
	if err != nil {
		return nil, err
	}
	if c.modelEffect != nil || c.turnNumber == 0 {
		return nil, errors.New("tool dispatch before durable assistant result")
	}
	seconds := float64(60)
	if value, ok := args["timeout"]; ok {
		seconds, err = number(value)
		if err != nil {
			return nil, err
		}
	}
	script, ok := args["script"].(string)
	if !ok {
		return nil, errors.New("tool script is required")
	}
	if r.Sandbox == nil {
		return nil, errors.New("sandbox is not configured")
	}
	if seconds <= 0 || seconds > float64((1<<63-1)/int64(time.Second)) || math.IsNaN(seconds) || math.IsInf(seconds, 0) {
		return nil, errors.New("tool timeout must be positive and fit a duration")
	}
	effect, err := w.Control.PrepareEffect(c.round.ID, fmt.Sprintf("tool:%d:%s", c.turnNumber, callID), "sandbox.shell", args)
	if err != nil {
		return nil, err
	}
	if effect.Status == "completed" {
		return object(effect.Result["tool_result"]), nil
	}
	defer func() {
		if err != nil {
			_ = w.Control.UnknownEffect(effect.ID, "remote dispatch or result persistence failed")
		}
	}()
	receipt, err := r.Sandbox.Execute(ctx, sandbox.Request{OperationID: effect.ID, Target: target, Script: script, Timeout: time.Duration(seconds * float64(time.Second)), Directory: directory, ArtifactsDir: filepath.Join(w.ArtifactsDir(), effect.ID)}, func(cp sandbox.Checkpoint) error {
		obj, err := asObject(cp)
		if err != nil {
			return err
		}
		return w.Control.CheckpointEffect(effect.ID, obj)
	})
	if err != nil {
		return nil, err
	}
	for i := range receipt.Artifacts {
		path, err := filepath.Rel(w.Path, receipt.Artifacts[i].Path)
		if err != nil || path == ".." || strings.HasPrefix(path, ".."+string(filepath.Separator)) {
			return nil, errors.New("artifact escaped Work")
		}
		receipt.Artifacts[i].Path = filepath.ToSlash(path)
	}
	data, err := asObject(receipt)
	if err != nil {
		return nil, err
	}
	if err = w.Control.CheckpointEffect(effect.ID, Object{"binding": receipt.Binding, "sandbox_id": receipt.SandboxID, "execution_id": receipt.ExecutionID, "observation": data}); err != nil {
		return nil, err
	}
	if receipt.State != "completed" || !receipt.Released {
		return nil, store.ErrUnknownEffect
	}
	if target == "userspace" {
		if err = r.Authority.RefreshGrant(w, old); err != nil {
			return nil, err
		}
	}
	data["stdout_ref"], err = w.Artifact([]byte(receipt.Stdout), ".txt")
	if err != nil {
		return nil, err
	}
	data["stderr_ref"], err = w.Artifact([]byte(receipt.Stderr), ".txt")
	if err != nil {
		return nil, err
	}
	view := Object{"exit_code": receipt.ExitCode, "stdout": preview(receipt.Stdout), "stderr": preview(receipt.Stderr), "artifacts": receipt.Artifacts}
	text, err := store.Canonical(view)
	if err != nil {
		return nil, err
	}
	result := Object{"content": []Object{{"type": "text", "text": text}}, "details": view}
	if err = w.Control.CompleteEffect(effect.ID, Object{"receipt": data, "tool_result": result}); err != nil {
		return nil, err
	}
	return result, nil
}
func preview(text string) string {
	if len(text) <= 16384 {
		return text
	}
	text = text[:16384]
	for !utf8.ValidString(text) {
		text = text[:len(text)-1]
	}
	return text
}
