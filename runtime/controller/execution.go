package controller

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"time"

	"loom/runtime/authority"
	"loom/runtime/execution"
	"loom/runtime/filesystem"
	"loom/runtime/store"
	"loom/runtime/work"
)

type workDomain struct {
	work       *work.Work
	authority  *authority.Authority
	scope      *execution.Scope
	binding    authority.Domain
	snapshot   string
	closed     bool
	recovering bool
}

func (r *Runtime) executionDomain(w *work.Work, round store.Round, role string) (*workDomain, error) {
	if r.Execution == nil {
		return nil, errors.New("not_ready: shared Linux Work facility is not configured")
	}
	cfg := *r.Execution
	if err := cfg.Check(); err != nil {
		return nil, err
	}
	if !filepath.IsAbs(cfg.StateDirectory) || cfg.StateDirectory == "/" {
		return nil, errors.New("host execution state_directory required")
	}
	if err := os.MkdirAll(cfg.StateDirectory, 0711); err != nil {
		return nil, err
	}
	resolved, err := filepath.EvalSymlinks(cfg.StateDirectory)
	if err != nil || resolved != cfg.StateDirectory {
		return nil, errors.New("execution state must be a real host directory")
	}
	// Only role-owned children are mounted. This parent permits traversal, not
	// directory listing, and must never contain host credentials or authority.
	if err = os.Chmod(cfg.StateDirectory, 0711); err != nil {
		return nil, err
	}
	identity, err := r.Authority.ExecutionIdentity(w, cfg.UIDBase, cfg.UIDCount)
	if err != nil {
		return nil, err
	}
	uid := identity.HarnessUID
	if role == "bash" {
		uid = identity.BashUID
	}
	id, err := store.ID()
	if err != nil {
		return nil, err
	}
	stage := filepath.Join(cfg.StateDirectory, id)
	if err = os.Mkdir(stage, 0711); err != nil {
		return nil, err
	}
	scope, err := cfg.NewScope(id, role, uid, uid)
	if err != nil {
		os.Remove(stage)
		return nil, err
	}
	d := &workDomain{work: w, authority: r.Authority, scope: scope, binding: authority.Domain{ID: id, WorkID: w.ID, RoundID: round.ID, Owner: round.Owner, Role: role, Cgroup: scope.Path, Staging: stage}}
	if err = r.Authority.SaveDomain(w, d.binding); err != nil {
		scope.Remove(context.Background())
		os.Remove(stage)
		return nil, err
	}
	// Once registered, failed setup is retained until fencing is confirmed.
	return d, nil
}

func (d *workDomain) close() error {
	if d.closed {
		return nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if d.binding.State != "fenced" {
		if err := d.scope.Fence(ctx); err != nil {
			return err
		}
		if err := d.authority.SettleDomain(d.binding.ID, d.binding.Owner); err != nil {
			return err
		}
		d.binding.State = "fenced"
	}
	for _, name := range []string{"stdout", "stderr"} {
		bytes, e := os.ReadFile(filepath.Join(d.binding.Staging, name+".log"))
		if errors.Is(e, os.ErrNotExist) {
			continue
		}
		if e != nil {
			return e
		}
		ref, e := d.work.Artifact(bytes, ".txt")
		if e != nil {
			return e
		}
		if _, e = d.work.Events.Append("runtime", "domain-log:"+d.binding.ID+":"+name, "execution.diagnostics", Object{"scope": d.binding.ID, "stream": name, "record_ref": ref}); e != nil {
			return e
		}
	}
	if d.recovering {
		if _, e := os.Stat(d.binding.Staging); e == nil {
			ref, e := d.work.CaptureContent(d.binding.Staging)
			if e != nil {
				return e
			}
			if _, e = d.work.Events.Append("runtime", "domain-recovery:"+d.binding.ID, "execution.recovery", Object{"scope": d.binding.ID, "role": d.binding.Role, "record_ref": ref, "fenced": true}); e != nil {
				return e
			}
		} else if !errors.Is(e, os.ErrNotExist) {
			return e
		}
	}
	if err := d.scope.RemoveFenced(); err != nil {
		return err
	}
	if err := os.RemoveAll(d.binding.Staging); err != nil {
		return err
	}
	if err := d.authority.CleanDomain(d.binding.ID, d.binding.Owner); err != nil {
		return err
	}
	d.closed = true
	return nil
}

// accessibleCopy contains only previously authorized content. Permissions here
// affect an isolated copy; user directories and host secrets are never chmod'ed.
func accessibleCopy(source, destination string, uid int, writable bool) error {
	var archive bytes.Buffer
	if err := filesystem.Archive(source, &archive); err != nil {
		return err
	}
	if err := os.Mkdir(destination, 0700); err != nil {
		return err
	}
	if err := filesystem.Extract(&archive, destination); err != nil {
		return err
	}
	return rolePermissions(destination, uid, writable)
}
func rolePermissions(root string, uid int, writable bool) error {
	return filepath.WalkDir(root, func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		if err = os.Lchown(path, uid, uid); err != nil {
			return err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return nil
		}
		mode := os.FileMode(0400)
		if info.IsDir() {
			mode |= 0100
		} else {
			mode |= info.Mode().Perm() & 0100
		}
		if writable {
			mode = info.Mode().Perm()
		}
		return os.Chmod(path, mode)
	})
}
func (d *workDomain) harnessCommand(w *work.Work, round store.Round, argv []string) ([]string, error) {
	if round.HarnessRef == "" {
		return nil, errors.New("Round has no fixed strategy reference")
	}
	destination := filepath.Join(d.binding.Staging, "snapshot")
	if err := w.Materialize(round.HarnessRef, destination); err != nil {
		return nil, err
	}
	if err := rolePermissions(destination, d.scope.UID, false); err != nil {
		return nil, err
	}
	d.snapshot = destination
	for _, directory := range []string{"facts", "sources", "resources"} {
		root := filepath.Join(d.binding.Staging, directory)
		if err := os.Mkdir(root, 0500); err != nil {
			return nil, err
		}
		if err := os.Chown(root, d.scope.UID, d.scope.GID); err != nil {
			return nil, err
		}
	}
	output := filepath.Join(d.binding.Staging, "outputs")
	if err := os.Mkdir(output, 0700); err != nil {
		return nil, err
	}
	if err := os.Chown(output, d.scope.UID, d.scope.GID); err != nil {
		return nil, err
	}
	facts := filepath.Join(d.binding.Staging, "facts")
	mounts := []execution.Mount{{Source: filepath.Join(destination, "harness"), Destination: "/harness"}, {Source: filepath.Join(destination, "surface"), Destination: "/work/surface"}, {Source: facts, Destination: "/facts"}, {Source: filepath.Join(d.binding.Staging, "sources"), Destination: "/sources"}}
	return d.scope.Command(argv, mounts, "/harness", 3600)
}
func (d *workDomain) strategyDirectory() string {
	return filepath.Join(d.binding.Staging, "snapshot", "harness")
}

func (r *Runtime) fenceOldDomains(w *work.Work) error {
	domains, err := r.Authority.Domains(w)
	if err != nil {
		return err
	}
	if len(domains) > 0 {
		return fmt.Errorf("not_ready: %d retained execution domains require recovery fencing before another owner", len(domains))
	}
	return nil
}

// Recover is an explicit management operation. It first invalidates all old
// session epochs, then fences host-owned cgroups before enabling continuation.
func (r *Runtime) Recover(ctx context.Context, w *work.Work) (Object, error) {
	if err := r.Authority.Authorize(w); err != nil {
		return nil, err
	}
	if r.Execution == nil {
		return nil, errors.New("not_ready: shared Linux facility required for recovery")
	}
	if err := r.Execution.Check(); err != nil {
		return nil, err
	}
	owner, err := store.ID()
	if err != nil {
		return nil, err
	}
	round, err := w.Control.BeginRecovery(owner)
	if err != nil {
		return nil, err
	}
	w, err = w.ForStrategy(round.HarnessRef)
	if err != nil {
		return nil, err
	}
	domains, err := r.Authority.Domains(w)
	if err != nil {
		return nil, err
	}
	for _, binding := range domains {
		// Paths are from the host database, and must also belong to this deployment.
		if filepath.Dir(binding.Cgroup) != r.Execution.CgroupRoot || filepath.Dir(binding.Staging) != r.Execution.StateDirectory || !strings.HasSuffix(binding.Cgroup, binding.ID+"-"+binding.Role) {
			return nil, errors.New("permission_denied: recovery domain outside configured deployment")
		}
		d := &workDomain{work: w, authority: r.Authority, scope: &execution.Scope{Path: binding.Cgroup, Config: *r.Execution}, binding: binding, recovering: true}
		if err = d.close(); err != nil {
			return nil, err
		}
	}
	if err = w.RecoverContent(); err != nil {
		return nil, err
	}
	if round.Checkpoint["phase"] == "handoff_pending" {
		pending := &run{runtime: r, work: w, round: round}
		if err = pending.releaseAllocations(ctx); err != nil {
			return nil, err
		}
	}
	if err = w.Control.EndRecovery(round); err != nil {
		return nil, err
	}
	return r.Query(w)
}
