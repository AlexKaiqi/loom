package controller

import (
	"context"
	"errors"
	"fmt"
	"loom/runtime/contracts"
	"loom/runtime/store"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"time"
	"unicode/utf8"
)

func (c *run) tool(ctx context.Context, name string, args Object, callID string) (answer Object, err error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if err = c.policy.ValidateTool(name, args); err != nil {
		return nil, err
	}
	if c.modelEffect != nil || c.turnNumber == 0 {
		return nil, errors.New("tool dispatch before durable assistant result")
	}
	return c.executeTool(ctx, fmt.Sprintf("tool:%d:%s", c.turnNumber, callID), args)
}

// Both strategy calls and the controlled model bridge use this one dispatch
// path. They cannot report execution success through the request interface.
func (c *run) executeTool(ctx context.Context, key string, args Object) (answer Object, err error) {
	r, w := c.runtime, c.work
	if err = r.Authority.Authorize(w); err != nil {
		return nil, err
	}
	prior, err := w.Control.EffectByKey(c.round.ID, key)
	if err != nil {
		return nil, err
	}
	if prior != nil {
		old, err := store.Canonical(prior.Request["arguments"])
		if err != nil {
			return nil, err
		}
		requested, err := store.Canonical(args)
		if err != nil {
			return nil, err
		}
		if old != requested {
			return nil, fmt.Errorf("%w: identity_conflict", store.ErrConflict)
		}
		if prior.Status == "completed" {
			return object(prior.Result["tool_result"]), nil
		}
		return nil, store.ErrUnknownEffect
	}
	if c.repairMode && args["environment"] != "work" {
		return Object{"content": []Object{{"type": "text", "text": "Context repair is active. Only Work Bash is available; repair surface/main.md before business execution."}}, "isError": true, "details": Object{"rejected_before_dispatch": true}}, nil
	}
	if err = c.clearEffects(); err != nil {
		return nil, err
	}
	environment, _ := args["environment"].(string)
	target, _ := args["target"].(string)
	if environment != "work" && environment != "sandbox" {
		return nil, errors.New("environment must be work or sandbox")
	}
	if environment == "work" && target != "" {
		return nil, errors.New("Work Bash has no Sandbox target")
	}
	if environment == "sandbox" && target == "" {
		target = "default"
	}
	seconds := float64(60)
	if value, ok := args["timeout"]; ok {
		seconds, err = number(value)
		if err != nil {
			return nil, err
		}
	}
	if seconds <= 0 || seconds > float64((1<<63-1)/int64(time.Second)) || math.IsNaN(seconds) || math.IsInf(seconds, 0) {
		return nil, errors.New("tool timeout must be positive and fit a duration")
	}
	script, ok := args["script"].(string)
	if !ok {
		return nil, errors.New("tool script required")
	}
	request := copyObject(args)
	request["arguments"] = copyObject(args)
	request["execution_scope"] = Object{"work_id": w.ID, "round_id": c.round.ID, "epoch": strconv.FormatInt(c.round.Epoch, 10)}
	var executor contracts.TaskExecutor
	var workspace *taskWorkspace
	var reusable *store.Allocation
	var localDomain *workDomain
	dispatchedLocal := false
	if environment == "work" {
		localDomain, err = r.executionDomain(w, c.round, "bash")
		if err != nil {
			return nil, err
		}
		defer func() {
			if !dispatchedLocal {
				err = errors.Join(err, localDomain.close())
			}
		}()
		object(request["execution_scope"])["domain_id"] = localDomain.binding.ID
		object(request["execution_scope"])["role"] = "bash"
	}
	if environment == "sandbox" {
		executor = r.Targets[target]
		var original contracts.TaskExecutor
		reusable, original, err = c.reusableAllocation(target)
		if err != nil {
			return nil, err
		}
		if reusable != nil {
			executor = original
			request["allocation_id"] = reusable.ID
		}
		if executor == nil {
			return nil, errors.New("capability_missing: task target is not available")
		}
		workspace, err = c.taskWorkspace(target)
		if err != nil {
			return nil, err
		}
		defer os.RemoveAll(workspace.directory) // All necessary bytes have record refs.
		request["target"] = target
		request["provider_scope"] = executor.Binding()
		request["userspace_bindings_ref"] = workspace.bindings
	}
	effect, err := w.Control.PrepareEffect(c.round.ID, key, "tool.exec", request)
	if err != nil {
		return nil, err
	}
	if effect.Status == "completed" {
		return object(effect.Result["tool_result"]), nil
	}
	var allocation string
	if workspace != nil {
		if reusable != nil {
			allocation = reusable.ID
		} else {
			allocation, err = c.saveAllocation(effect.ID, workspace, executor.Binding())
		}
		if err != nil {
			return nil, err
		}
	}
	if _, err = c.acceptedEffect(effect); err != nil {
		return nil, err
	}
	if err = w.Control.AttemptEffect(effect.ID, c.round.Owner); err != nil {
		return nil, err
	}
	defer func() {
		if err != nil {
			_ = w.Control.UnknownEffect(effect.ID, "dispatch or result persistence failed; reconcile original binding")
		}
	}()
	if environment == "work" {
		dispatchedLocal = true
		return c.workBash(ctx, localDomain, effect, script, time.Duration(seconds*float64(time.Second)))
	}
	req := contracts.Request{OperationID: effect.ID, Target: target, Script: script, Timeout: time.Duration(seconds * float64(time.Second)), Directory: workspace.directory, ReadOnlyPaths: workspace.readOnly, ArtifactsDir: filepath.Join(w.ArtifactsDir(), effect.ID)}
	if reusable != nil {
		req.SandboxID, req.AllocationRequestID = reusable.SandboxID, reusable.EffectID
	}
	receipt, err := executor.Execute(ctx, req, func(cp contracts.Checkpoint) error {
		if err := c.allocationObservation(allocation, cp); err != nil {
			return err
		}
		obj, err := asObject(cp)
		if err != nil {
			return err
		}
		if cp.Phase == "prepared" && cp.Readiness != nil {
			saved, err := c.saveAdapterArtifacts(cp.Artifacts)
			if err != nil {
				return err
			}
			if _, err = w.Events.AppendOwned("runtime", "target-ready:"+effect.ID, "target.ready", Object{
				"target": target, "allocation_id": allocation, "effect_id": effect.ID,
				"binding": cp.Binding, "sandbox_id": cp.SandboxID, "execution_id": cp.ExecutionID,
				"readiness": cp.Readiness, "artifacts": saved,
			}); err != nil {
				return err
			}
		}
		if cp.NativeResult != nil {
			saved, e := c.saveAdapterArtifacts(cp.Artifacts)
			if e != nil {
				return e
			}
			native := copyObject(cp.NativeResult)
			native["artifacts"] = saved
			if e = w.Control.NativeEffect(effect.ID, native); e != nil {
				return e
			}
		}
		return w.Control.CheckpointEffect(effect.ID, obj)
	})
	if err != nil {
		return nil, err
	}
	data, err := asObject(receipt)
	if err != nil {
		return nil, err
	}
	// Transfer artifacts are converted to verified immutable records before any
	// ToolResult or content-delivery confirmation becomes visible to the model.
	saved, err := c.saveAdapterArtifacts(receipt.Artifacts)
	if err != nil {
		return nil, err
	}
	data["artifacts"] = saved
	if err = w.Control.CheckpointEffect(effect.ID, Object{"binding": receipt.Binding, "allocation_id": allocation, "sandbox_id": receipt.SandboxID, "execution_id": receipt.ExecutionID, "observation": data}); err != nil {
		return nil, err
	}
	if receipt.State != "completed" {
		return nil, store.ErrUnknownEffect
	}
	if err = c.saveTaskContents(workspace, effect.ID); err != nil {
		return nil, err
	}
	data["stdout_ref"], err = w.Artifact([]byte(receipt.Stdout), ".txt")
	if err != nil {
		return nil, err
	}
	data["stderr_ref"], err = w.Artifact([]byte(receipt.Stderr), ".txt")
	if err != nil {
		return nil, err
	}
	view := Object{"exit_code": receipt.ExitCode, "stdout": outputPreview(receipt.Stdout, data["stdout_ref"]), "stderr": outputPreview(receipt.Stderr, data["stderr_ref"]), "artifacts": saved, "target": target, "workspace": "/workspace/task", "resource_paths": resourcePaths(workspace), "output_stream": "combined (executor does not distinguish stdout/stderr)"}
	if receipt.Readiness != nil {
		view["readiness"] = receipt.Readiness
	}
	text, err := store.Canonical(view)
	if err != nil {
		return nil, err
	}
	result := Object{"content": []Object{{"type": "text", "text": text}}, "details": view, "isError": receipt.ExitCode != nil && *receipt.ExitCode != 0}
	if err = w.Control.CompleteEffect(effect.ID, Object{"receipt": data, "tool_result": result}); err != nil {
		return nil, err
	}
	if reusable == nil {
		if err = w.Control.AllocationReleaseObserved(allocation, receipt.Released); err != nil {
			return nil, err
		}
	}
	return result, nil
}
func resourcePaths(ws *taskWorkspace) Object {
	paths := Object{}
	for _, copy := range ws.copies {
		paths[copy.Alias] = "/workspace/task/" + copy.Alias
	}
	return paths
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

func (c *run) saveAdapterArtifacts(artifacts []contracts.Artifact) ([]Object, error) {
	saved := []Object{}
	for _, item := range artifacts {
		raw, e := os.ReadFile(item.Path)
		if e != nil {
			return nil, e
		}
		ref, e := (store.Records{Directory: c.work.ArtifactsDir()}).Put(raw, item.MIMEType)
		if e != nil {
			return nil, e
		}
		if ref.SHA256 != item.SHA256 {
			return nil, errors.New("adapter artifact digest changed")
		}
		saved = append(saved, Object{"name": filepath.Base(item.Path), "record_ref": ref})
	}
	return saved, nil
}
