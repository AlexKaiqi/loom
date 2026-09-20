package controller

import (
	"bytes"
	"context"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"time"

	"loom/runtime/execution"
	"loom/runtime/filesystem"
	"loom/runtime/store"
	"loom/runtime/work"
)

// workBash runs standard Bash in the Work namespace. It never receives a policy
// control channel, provider credential, authority database or host-home mount.
func (c *run) workBash(ctx context.Context, d *workDomain, effect store.Effect, script string, timeout time.Duration) (result Object, err error) {
	durable := false
	defer func() {
		if durable {
			err = errors.Join(err, d.close())
			return
		}
		// Unknown progress is fenced, but its registered staging and responsibility
		// remain available to recovery. Never discard the only possible result.
		stop, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		err = errors.Join(err, d.scope.Fence(stop))
	}()
	mount := []execution.Mount{}
	_, resourceMount, err := c.resourceViews(d)
	if err != nil {
		return nil, err
	}
	mount = append(mount, resourceMount)
	selected := filepath.Join(d.binding.Staging, "executing-harness")
	if err = accessibleCopy(c.domain.strategyDirectory(), selected, d.scope.UID, false); err != nil {
		return nil, err
	}
	mount = append(mount, execution.Mount{Source: selected, Destination: "/harness"})
	definition, err := os.ReadFile(filepath.Join(c.domain.snapshot, "work.toml"))
	if err != nil {
		return nil, err
	}
	definitionPath := filepath.Join(d.binding.Staging, "work.toml")
	if err = os.WriteFile(definitionPath, definition, 0400); err != nil {
		return nil, err
	}
	if err = os.Chown(definitionPath, d.scope.UID, d.scope.GID); err != nil {
		return nil, err
	}
	mount = append(mount, execution.Mount{Source: definitionPath, Destination: "/work/work.toml"})
	type source struct {
		name, path, stage, digest string
		info                      os.FileInfo
	}
	sources := []source{}
	for _, name := range []string{"surface", "harness"} {
		path := c.work.Surface
		if name == "harness" {
			path = c.work.Harness
		}
		stage := filepath.Join(d.binding.Staging, name)
		info, e := os.Lstat(path)
		if e != nil {
			return nil, e
		}
		digest, e := filesystem.TreeDigest(path)
		if e != nil {
			return nil, e
		}
		if err = accessibleCopy(path, stage, d.scope.UID, true); err != nil {
			return nil, err
		}
		sources = append(sources, source{name, path, stage, digest, info})
		mount = append(mount, execution.Mount{Source: stage, Destination: "/work/" + name, Writable: true})
	}
	view, err := c.work.Events.OpenView(store.ViewScope{WorkID: c.work.ID, MountPath: "/facts"}, c.round.InputSeq)
	if err != nil {
		return nil, err
	}
	facts := filepath.Join(d.binding.Staging, "facts")
	if err = accessibleCopy(view.Directory, facts, d.scope.UID, false); err != nil {
		return nil, err
	}
	if err = c.writeInterface(facts, d.scope.UID, d.scope.GID); err != nil {
		return nil, err
	}
	mount = append(mount, execution.Mount{Source: facts, Destination: "/facts"})
	argv, err := d.scope.Command([]string{"/bin/bash", "--noprofile", "--norc", "-c", script}, mount, "/work", int(timeout.Seconds())+1)
	if err != nil {
		return nil, err
	}
	out, err := os.OpenFile(filepath.Join(d.binding.Staging, "stdout"), os.O_CREATE|os.O_EXCL|os.O_RDWR, 0600)
	if err != nil {
		return nil, err
	}
	defer out.Close()
	stderr, err := os.OpenFile(filepath.Join(d.binding.Staging, "stderr"), os.O_CREATE|os.O_EXCL|os.O_RDWR, 0600)
	if err != nil {
		return nil, err
	}
	defer stderr.Close()
	requestCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	cmd := exec.CommandContext(requestCtx, argv[0], argv[1:]...)
	cmd.Env = []string{}
	cmd.Stdout = out
	cmd.Stderr = stderr
	started := cmd.Run()
	stop, stopCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer stopCancel()
	if err = d.scope.Fence(stop); err != nil {
		return nil, err
	}
	if requestCtx.Err() != nil {
		return nil, errors.New("outcome_unknown: Work Bash deadline; execution stopped, result requires reconciliation")
	}
	code := 0
	if started != nil {
		var exit *exec.ExitError
		if !errors.As(started, &exit) {
			return nil, started
		}
		code = exit.ExitCode()
	}
	if err = errors.Join(out.Sync(), stderr.Sync()); err != nil {
		return nil, err
	}
	stdoutBytes, err := os.ReadFile(out.Name())
	if err != nil {
		return nil, err
	}
	stderrBytes, err := os.ReadFile(stderr.Name())
	if err != nil {
		return nil, err
	}
	records := store.Records{Directory: c.work.ArtifactsDir()}
	stdoutRef, err := records.Put(stdoutBytes, "text/plain")
	if err != nil {
		return nil, err
	}
	stderrRef, err := records.Put(stderrBytes, "text/plain")
	if err != nil {
		return nil, err
	}
	changes := []work.ContentChange{}
	// Save every candidate before changing any Work file. A conflict leaves the
	// full observed result recoverable and does not silently overwrite local edits.
	for _, s := range sources {
		var archive bytes.Buffer
		if err = filesystem.Archive(s.stage, &archive); err != nil {
			return nil, err
		}
		ref, e := records.Put(archive.Bytes(), "application/x-tar")
		if e != nil {
			return nil, e
		}
		changes = append(changes, work.ContentChange{Root: s.name, Expected: s.digest, Ref: ref})
	}
	receipt := Object{"environment": "work", "scope": d.binding.ID, "exit_code": code, "stdout_ref": stdoutRef, "stderr_ref": stderrRef, "changes": changes, "cancellation": "stop_confirmed", "view_id": view.ID}
	if err = c.work.Control.NativeEffect(effect.ID, receipt); err != nil {
		return nil, err
	}
	if err = c.work.Control.CheckpointEffect(effect.ID, receipt); err != nil {
		return nil, err
	}
	for _, s := range sources {
		if err = filesystem.Unchanged(s.path, s.info, s.digest); err != nil {
			return nil, err
		}
	}
	revision, err := c.work.PublishContent(effect.ID, changes)
	if err != nil {
		return nil, err
	}
	viewResult := Object{"exit_code": code, "stdout": outputPreview(string(stdoutBytes), stdoutRef), "stderr": outputPreview(string(stderrBytes), stderrRef), "content_version": revision}
	text, err := store.Canonical(viewResult)
	if err != nil {
		return nil, err
	}
	result = Object{"content": []Object{{"type": "text", "text": text}}, "details": viewResult, "isError": code != 0}
	receipt["tool_result"] = result
	if err = c.work.Control.CompleteEffect(effect.ID, receipt); err != nil {
		return nil, err
	}
	durable = true
	return result, nil
}

// Bounded display is an explicit tool result with a complete immutable source,
// never an invisible crop of the fact selected by the Harness.
func outputPreview(text string, ref any) Object {
	snippet := preview(text)
	return Object{"text": snippet, "record_ref": ref, "total_bytes": strconv.Itoa(len(text)), "visible_bytes": strconv.Itoa(len(snippet)), "truncated": len(snippet) != len(text)}
}
