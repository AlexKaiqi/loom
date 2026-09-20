package controller

import (
	"encoding/json"
	"errors"
	"loom/runtime/execution"
	"loom/runtime/work"
	"os"
	"path/filepath"
)

// Resource views expose retained bytes only. No path traverses a live task
// environment or mounts the shared project into Work Bash.
func (c *run) resourceViews(domain *workDomain) (Object, execution.Mount, error) {
	root := filepath.Join(domain.binding.Staging, "resources")
	if err := os.MkdirAll(root, 0711); err != nil {
		return nil, execution.Mount{}, err
	}
	views := Object{}
	for alias := range c.work.Definition.Userspaces {
		grant, err := c.runtime.Authority.Resource(c.work, alias)
		if err != nil {
			return nil, execution.Mount{}, err
		}
		source, err := c.work.ResourceSource(alias)
		if err != nil {
			return nil, execution.Mount{}, err
		}
		if source == nil {
			return nil, execution.Mount{}, errors.New("dependency_missing: resource source missing")
		}
		versions := map[string]work.ResourceCopy{"source": {Alias: alias, Target: "@read", ContentRef: source.BaseRef}}
		for target, definition := range c.work.Definition.Targets {
			for _, allowed := range definition.Userspaces {
				if allowed == alias {
					copy, err := c.work.ResourceCopy(alias, target)
					if err != nil {
						return nil, execution.Mount{}, err
					}
					versions[target] = copy
				}
			}
		}
		bindings := Object{}
		for target, copy := range versions {
			// A hash-named directory is immutable for the lifetime of this domain.
			destination := filepath.Join(root, copy.ContentRef.SHA256)
			if _, err := os.Lstat(destination); errors.Is(err, os.ErrNotExist) {
				if err = c.work.RestoreContent(copy.ContentRef, destination); err != nil {
					return nil, execution.Mount{}, err
				}
				if err = rolePermissions(destination, domain.scope.UID, false); err != nil {
					return nil, execution.Mount{}, err
				}
			} else if err != nil {
				return nil, execution.Mount{}, err
			}
			bindings[target] = Object{"root": "/resources/" + copy.ContentRef.SHA256, "base_ref": copy.ContentRef, "working_copy_id": copy.ID, "resource_id": grant.ID, "resource_scope": grant.Scope, "access": "read"}
		}
		views[alias] = bindings
	}
	grants, err := c.runtime.Authority.ReadGrants(c.work)
	if err != nil {
		return nil, execution.Mount{}, err
	}
	for _, grant := range grants {
		if _, exists := views[grant.Alias]; exists {
			return nil, execution.Mount{}, errors.New("read alias conflicts with Userspace")
		}
		version, err := grant.Source.CurrentContent()
		if err != nil {
			return nil, execution.Mount{}, err
		}
		refDir := filepath.Join(root, grant.Source.ID+"-"+version)
		if _, err = os.Lstat(refDir); errors.Is(err, os.ErrNotExist) {
			temp, err := os.MkdirTemp(domain.binding.Staging, "source-work-")
			if err != nil {
				return nil, execution.Mount{}, err
			}
			snapshot := filepath.Join(temp, "content")
			err = grant.Source.Materialize(version, snapshot)
			if err == nil {
				err = accessibleCopy(filepath.Join(snapshot, "surface"), refDir, domain.scope.UID, false)
			}
			os.RemoveAll(temp)
			if err != nil {
				return nil, execution.Mount{}, err
			}
		} else if err != nil {
			return nil, execution.Mount{}, err
		}
		// Retain the exact authorized bytes in the receiving Work, because actual
		// model input must remain inspectable after the source disappears.
		ref, err := c.work.CaptureContent(refDir)
		if err != nil {
			return nil, execution.Mount{}, err
		}
		views[grant.Alias] = Object{"source": Object{"root": "/resources/" + filepath.Base(refDir), "base_ref": ref, "source_work_id": grant.Source.ID, "content_ref": version, "access": "read", "scope": "surface"}}
	}
	raw, err := asObject(views)
	if err != nil {
		return nil, execution.Mount{}, err
	}
	body, err := json.MarshalIndent(raw, "", "  ")
	if err != nil {
		return nil, execution.Mount{}, err
	}
	// The index is per-boundary data. Its bytes are saved with the projection;
	// previously published source directories are never changed in place.
	if err = os.WriteFile(filepath.Join(root, "bindings.json"), body, 0444); err != nil {
		return nil, execution.Mount{}, err
	}
	return views, execution.Mount{Source: root, Destination: "/resources"}, nil
}

func (c *run) validateSavedViews(plan Object) error {
	views := object(plan["resource_views"])
	if len(views) == 0 {
		return nil
	}
	grants, err := c.runtime.Authority.ReadGrants(c.work)
	if err != nil {
		return err
	}
	allowed := map[string]string{}
	for _, grant := range grants {
		allowed[grant.Alias] = grant.Source.ID
	}
	for alias, raw := range views {
		source := object(object(raw)["source"])
		if id, ok := source["source_work_id"].(string); ok && allowed[alias] != id {
			return errors.New("permission_denied: saved projection's cross-Work read grant was revoked")
		}
	}
	return nil
}
