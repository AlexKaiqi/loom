package controller

import (
	"encoding/json"
	"errors"
	"github.com/AlexKaiqi/ondemand-sandbox/execution/contracts"
	"loom/runtime/store"
	"loom/runtime/work"
	"os"
	"path/filepath"
	"sort"
	"strconv"
)

type taskWorkspace struct {
	directory string
	target    string
	copies    []work.ResourceCopy
	readOnly  []string
	bindings  store.RecordRef
}

func (c *run) taskWorkspace(target string) (*taskWorkspace, error) {
	definition, ok := c.work.Definition.Targets[target]
	if !ok {
		return nil, errors.New("capability_missing: task target is not declared")
	}
	parent := filepath.Join(c.work.Path, ".loom", "views")
	if err := os.MkdirAll(parent, 0700); err != nil {
		return nil, err
	}
	directory, err := os.MkdirTemp(parent, ".target-")
	if err != nil {
		return nil, err
	}
	workspace := &taskWorkspace{directory: directory, target: target}
	success := false
	defer func() {
		if !success {
			os.RemoveAll(directory)
		}
	}()
	bindings := []Object{}
	aliases := append([]string(nil), definition.Userspaces...)
	sort.Strings(aliases)
	for _, alias := range aliases {
		grant, err := c.runtime.Authority.Resource(c.work, alias)
		if err != nil {
			return nil, err
		}
		copy, err := c.work.ResourceCopy(alias, target)
		if err != nil {
			return nil, err
		}
		if err = c.work.RestoreContent(copy.ContentRef, filepath.Join(directory, alias)); err != nil {
			return nil, err
		}
		scope, err := artifact(c.work, Object{"resource_id": grant.ID, "paths": []string{"."}, "access": grant.Access})
		if err != nil {
			return nil, err
		}
		bindings = append(bindings, Object{"alias": alias, "resource_scope": grant.Scope, "resource_id": grant.ID, "working_copy_id": copy.ID, "access": grant.Access, "scope_ref": scope, "base_ref": copy.ContentRef})
		workspace.copies = append(workspace.copies, copy)
		if grant.Access == "read" {
			workspace.readOnly = append(workspace.readOnly, alias)
		}
	}
	raw, err := json.Marshal(Object{"schema_version": 1, "bindings": bindings})
	if err != nil {
		return nil, err
	}
	workspace.bindings, err = (store.Records{Directory: c.work.ArtifactsDir()}).Put(raw, "application/vnd.loom.userspace-bindings+json")
	if err != nil {
		return nil, err
	}
	success = true
	return workspace, nil
}
func (c *run) saveTaskContents(ws *taskWorkspace, effect string) error {
	// Capture every result before committing any per-copy predecessor. The result
	// records survive a later conflict; another Target's copy is never consulted.
	updates := []work.CopyUpdate{}
	for _, copy := range ws.copies {
		ref, err := c.work.CaptureContent(filepath.Join(ws.directory, copy.Alias))
		if err != nil {
			return err
		}
		if c.work.Definition.Userspaces[copy.Alias].Access == "read" {
			if ref != copy.ContentRef {
				return errors.New("permission_denied: read-only resource content changed")
			}
		} else {
			updates = append(updates, work.CopyUpdate{Prior: copy, Ref: ref})
		}
	}
	return c.work.SaveResourceCopies(updates, effect)
}
func (c *run) saveAllocation(effect string, ws *taskWorkspace, binding contracts.Binding) (string, error) {
	id, err := store.ID()
	if err != nil {
		return "", err
	}
	body, err := json.Marshal(Object{"schema_version": 1, "target": ws.target, "allocation_id": id, "binding_generation": "1", "provider_scope": binding, "userspace_bindings_ref": ws.bindings, "work_id": c.work.ID, "round_id": c.round.ID, "epoch": strconv.FormatInt(c.round.Epoch, 10)})
	if err != nil {
		return "", err
	}
	err = c.work.Control.CreateAllocation(c.round.ID, id, effect, ws.target, string(body))
	return id, err
}

func (c *run) allocationObservation(id string, cp contracts.Checkpoint) error {
	body, err := json.Marshal(cp)
	if err != nil {
		return err
	}
	return c.work.Control.CheckpointAllocation(c.round.ID, id, cp.SandboxID, cp.ExecutionID, string(body))
}
