// Package execution delegates isolation to NsJail and lifecycle fencing to Linux
// cgroup v2. No shell text is interpreted by the controller to infer authority.
package execution

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	PythonEnvironment string `toml:"python_environment,omitempty"`
	StateDirectory    string `toml:"state_directory"`
	UIDBase           int    `toml:"uid_base"`
	UIDCount          int    `toml:"uid_count"`
	Binary            string `toml:"launcher"`
	SHA256            string `toml:"launcher_sha256"`
	CgroupRoot        string `toml:"cgroup_root"`
	MemoryBytes       int64  `toml:"memory_bytes"`
	Processes         int    `toml:"processes"`
	CPUMilliseconds   int    `toml:"cpu_milliseconds"`
}
type Mount struct {
	Source, Destination string
	Writable            bool
}
type Scope struct {
	Path     string
	Config   Config
	UID, GID int
	Role     string
}

func (c Config) Check() error {
	if runtime.GOOS != "linux" {
		return errors.New("not_ready: Work execution requires the shared Linux facility")
	}
	if os.Geteuid() != 0 {
		return errors.New("not_ready: launcher requires the deployment's privileged controller identity")
	}
	if c.PythonEnvironment != "" {
		resolved, err := filepath.EvalSymlinks(c.PythonEnvironment)
		info, statErr := os.Stat(c.PythonEnvironment)
		if err != nil || statErr != nil || !info.IsDir() || !filepath.IsAbs(c.PythonEnvironment) || resolved != c.PythonEnvironment || strings.ContainsAny(c.PythonEnvironment, ":\n\x00") {
			return errors.New("invalid deployment Python environment")
		}
	}
	if !filepath.IsAbs(c.Binary) || !filepath.IsAbs(c.CgroupRoot) || filepath.Clean(c.CgroupRoot) == "/sys/fs/cgroup" || c.MemoryBytes <= 0 || c.Processes <= 0 || c.CPUMilliseconds <= 0 {
		return errors.New("invalid Work execution configuration; delegated cgroup and explicit limits required")
	}
	data, err := os.ReadFile(c.Binary)
	if err != nil {
		return err
	}
	sum := sha256.Sum256(data)
	if len(c.SHA256) != 64 || hex.EncodeToString(sum[:]) != c.SHA256 {
		return errors.New("execution launcher does not match deployment lock")
	}
	resolved, err := filepath.EvalSymlinks(c.CgroupRoot)
	if err != nil {
		return err
	}
	if resolved != c.CgroupRoot {
		return errors.New("symbolic cgroup root refused")
	}
	active, err := os.ReadFile(filepath.Join(c.CgroupRoot, "cgroup.subtree_control"))
	if err != nil {
		return err
	}
	for _, controller := range []string{"cpu", "memory", "pids"} {
		found := false
		for _, name := range strings.Fields(string(active)) {
			if name == controller {
				found = true
			}
		}
		if !found {
			return fmt.Errorf("not_ready: delegated cgroup lacks active %s controller", controller)
		}
	}
	return nil
}

// NewScope is called with host-assigned role IDs. Work data cannot select them.
// The unique scope is persisted by the controller before starting its process.
func (c Config) NewScope(id, role string, uid, gid int) (*Scope, error) {
	if err := c.Check(); err != nil {
		return nil, err
	}
	if id == "" || strings.Trim(id, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_") != "" || len(id) > 160 || uid < 1000 || gid < 1000 || (role != "harness" && role != "bash") {
		return nil, errors.New("invalid execution identity")
	}
	path := filepath.Join(c.CgroupRoot, id+"-"+role)
	if err := os.Mkdir(path, 0700); err != nil {
		return nil, err
	}
	return &Scope{Path: path, Config: c, UID: uid, GID: gid, Role: role}, nil
}

func (s *Scope) Command(argv []string, mounts []Mount, cwd string, seconds int) ([]string, error) {
	if len(argv) == 0 || argv[0] == "" || seconds <= 0 || !filepath.IsAbs(cwd) {
		return nil, errors.New("execution argv, deadline and absolute cwd required")
	}
	argv = append([]string(nil), argv...)
	if argv[0] == "python3" && s.Config.PythonEnvironment != "" {
		argv[0] = "/opt/loom-python/bin/python3"
	}
	// NsJail intentionally uses execve, not a host shell or PATH lookup. Resolve
	// bare executables only in the deployment's mounted toolchain directories.
	if !strings.ContainsRune(argv[0], '/') {
		found := false
		for _, directory := range []string{"/usr/local/loom-python/bin", "/usr/local/bin", "/usr/bin", "/bin"} {
			candidate := filepath.Join(directory, argv[0])
			if info, err := os.Stat(candidate); err == nil && info.Mode().IsRegular() && info.Mode().Perm()&0111 != 0 {
				argv[0], found = candidate, true
				break
			}
		}
		if !found {
			return nil, errors.New("capability_missing: executable absent from locked Work toolchain")
		}
	}
	toolPath := "/usr/local/loom-python/bin:/usr/local/bin:/usr/bin:/bin"
	if s.Config.PythonEnvironment != "" {
		toolPath = "/opt/loom-python/bin:/usr/local/bin:/usr/bin:/bin"
	}
	args := []string{s.Config.Binary, "-Mo", "-q", "--user", fmt.Sprintf("%d:%d:1", s.UID, s.UID), "--group", fmt.Sprintf("%d:%d:1", s.GID, s.GID), "--time_limit", strconv.Itoa(seconds), "--rlimit_as", "max", "--rlimit_fsize", "256", "--rlimit_nofile", "256", "--rlimit_nproc", strconv.Itoa(s.Config.Processes), "--use_cgroupv2", "--cgroupv2_mount", s.Path, "--cgroup_mem_max", strconv.FormatInt(s.Config.MemoryBytes, 10), "--cgroup_pids_max", strconv.Itoa(s.Config.Processes), "--cgroup_cpu_ms_per_sec", strconv.Itoa(s.Config.CPUMilliseconds), "--cwd", cwd, "--env", "PATH=" + toolPath, "--env", "LANG=C.UTF-8", "--env", "HOME=/tmp", "--tmpfsmount", "/tmp", "--iface_no_lo"}
	// These are the deployment's read-only toolchain, never its home or secrets.
	if s.Config.PythonEnvironment != "" {
		args = append(args, "--bindmount_ro", s.Config.PythonEnvironment+":/opt/loom-python")
	}
	for _, path := range []string{"/usr", "/bin", "/lib", "/lib64"} {
		if _, err := os.Stat(path); err == nil {
			args = append(args, "--bindmount_ro", path)
		}
	}
	destinations := map[string]bool{}
	for _, mount := range mounts {
		if !filepath.IsAbs(mount.Source) || !filepath.IsAbs(mount.Destination) || strings.ContainsAny(mount.Source+mount.Destination, ":\n\x00") || filepath.Clean(mount.Destination) != mount.Destination || mount.Destination == "/" || destinations[mount.Destination] {
			return nil, errors.New("invalid or duplicate execution mount")
		}
		if mount.Destination != "/outputs" && mount.Destination != "/resources" && mount.Destination != "/sources" && mount.Destination != "/harness" && mount.Destination != "/work/work.toml" && mount.Destination != "/work/surface" && mount.Destination != "/work/harness" && mount.Destination != "/facts" && !strings.HasPrefix(mount.Destination, "/resources/") {
			return nil, errors.New("mount outside allowed Work view")
		}
		if mount.Writable && mount.Destination != "/work/surface" && mount.Destination != "/work/harness" && !(s.Role == "harness" && mount.Destination == "/outputs") {
			return nil, errors.New("Work role cannot write resource or control mounts")
		}
		if mount.Destination == "/harness" && mount.Writable {
			return nil, errors.New("executing strategy must be read only")
		}
		resolved, err := filepath.EvalSymlinks(mount.Source)
		if err != nil {
			return nil, err
		}
		if resolved != mount.Source {
			return nil, errors.New("symbolic mount root refused")
		}
		flag := "--bindmount_ro"
		if mount.Writable {
			flag = "--bindmount"
		}
		args = append(args, flag, mount.Source+":"+mount.Destination)
		destinations[mount.Destination] = true
	}
	if s.Role == "harness" {
		args = append(args, "--pass_fd", "3")
	}
	args = append(args, "--env", "FACTS_DB=/facts/facts.sqlite", "--")
	return append(args, argv...), nil
}

func (s *Scope) wait(ctx context.Context, property string, value string) error {
	timer := time.NewTicker(10 * time.Millisecond)
	defer timer.Stop()
	for {
		data, err := os.ReadFile(filepath.Join(s.Path, "cgroup.events"))
		if err != nil {
			return err
		}
		for _, line := range strings.Split(string(data), "\n") {
			if line == property+" "+value {
				return nil
			}
		}
		select {
		case <-ctx.Done():
			return fmt.Errorf("execution fencing unconfirmed: %w", ctx.Err())
		case <-timer.C:
		}
	}
}
func (s *Scope) Freeze(ctx context.Context) error {
	if err := os.WriteFile(filepath.Join(s.Path, "cgroup.freeze"), []byte("1"), 0600); err != nil {
		return err
	}
	return s.wait(ctx, "frozen", "1")
}
func (s *Scope) Thaw() error {
	return os.WriteFile(filepath.Join(s.Path, "cgroup.freeze"), []byte("0"), 0600)
}

// Fence kills the entire owned domain, including detached descendants. A process
// exit or successful write to cgroup.kill alone is not the completion evidence.
func (s *Scope) Fence(ctx context.Context) error {
	if err := os.WriteFile(filepath.Join(s.Path, "cgroup.kill"), []byte("1"), 0600); err != nil {
		return err
	}
	return s.wait(ctx, "populated", "0")
}
func (s *Scope) Remove(ctx context.Context) error {
	if err := s.Fence(ctx); err != nil {
		return err
	}
	return s.RemoveFenced()
}

// RemoveFenced requires a durable host fencing certificate. Missing directories
// are idempotent only on this post-fence cleanup path.
func (s *Scope) RemoveFenced() error {
	if _, err := os.Lstat(s.Path); errors.Is(err, os.ErrNotExist) {
		return nil
	}
	var directories []string
	err := filepath.WalkDir(s.Path, func(name string, entry os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			directories = append(directories, name)
		}
		return nil
	})
	if err != nil {
		return err
	}
	for i := len(directories) - 1; i >= 0; i-- {
		if err = os.Remove(directories[i]); err != nil {
			return err
		}
	}
	return nil
}
