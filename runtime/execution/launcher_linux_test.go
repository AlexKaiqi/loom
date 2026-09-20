//go:build linux

package execution

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"golang.org/x/sys/unix"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func facility(t *testing.T) (Config, string) {
	t.Helper()
	root := os.Getenv("LOOM_TEST_CGROUP_ROOT")
	if root == "" {
		t.Skip("real delegated Linux cgroup not configured")
	}
	binary := "/usr/local/bin/nsjail"
	data, err := os.ReadFile(binary)
	if err != nil {
		t.Fatal(err)
	}
	h := sha256.Sum256(data)
	cfg := Config{Binary: binary, SHA256: hex.EncodeToString(h[:]), CgroupRoot: root, MemoryBytes: 128 << 20, Processes: 32, CPUMilliseconds: 500}
	if err = cfg.Check(); err != nil {
		t.Fatal(err)
	}
	work := t.TempDir()
	// Runtime staging ancestors are traversable by the assigned role; sensitive
	// control state is a separate root and never mounted into this namespace.
	if err = os.Chmod(filepath.Dir(work), 0711); err != nil {
		t.Fatal(err)
	}
	if err = os.Chmod(work, 0755); err != nil {
		t.Fatal(err)
	}
	return cfg, work
}
func scope(t *testing.T, c Config, role string) *Scope {
	t.Helper()
	s, err := c.NewScope(fmt.Sprintf("test-%d-%d", os.Getpid(), time.Now().UnixNano()), role, 100001, 100001)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		if err := s.Remove(ctx); err != nil {
			t.Error(err)
		}
	})
	return s
}
func TestRealWorkRoleIsolation(t *testing.T) {
	cfg, root := facility(t)
	surface := filepath.Join(root, "surface")
	harness := filepath.Join(root, "harness")
	for _, p := range []string{surface, harness} {
		if err := os.Mkdir(p, 0770); err != nil {
			t.Fatal(err)
		}
		if err := os.Chown(p, 100001, 100001); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.WriteFile(filepath.Join(harness, "policy.py"), []byte("immutable version"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.Chown(filepath.Join(harness, "policy.py"), 100001, 100001); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "host-secret"), []byte("not-mounted"), 0600); err != nil {
		t.Fatal(err)
	}
	for _, role := range []string{"harness", "bash"} {
		t.Run(role, func(t *testing.T) {
			s := scope(t, cfg, role)
			script := `import os,json,socket
out={"uid":os.getuid(),"secret_visible":os.path.exists("` + filepath.Join(root, "host-secret") + `")}
try: out["control"]=os.read(3,6).decode()
except OSError: out["control"]=None
try: os.chmod('/harness/policy.py',0o777);out['chmod']=True
except OSError: out['chmod']=False
try: open('/harness/policy.py','w').write('changed');out['policy_write']=True
except OSError:out['policy_write']=False
out['status']=open('/proc/self/status').read()
open('/work/surface/result','w').write('ordinary edit')
try:
 s=socket.socket();s.settimeout(.1);s.connect(('1.1.1.1',443));out['network']=True
except OSError:out['network']=False
print(json.dumps(out))`
			argv, err := s.Command([]string{"/usr/bin/python3", "-c", script}, []Mount{{harness, "/harness", false}, {surface, "/work/surface", true}}, "/work/surface", 10)
			if err != nil {
				t.Fatal(err)
			}
			fds, err := unix.Socketpair(unix.AF_UNIX, unix.SOCK_STREAM, 0)
			if err != nil {
				t.Fatal(err)
			}
			parent := os.NewFile(uintptr(fds[0]), "parent")
			child := os.NewFile(uintptr(fds[1]), "child")
			defer parent.Close()
			defer child.Close()
			if _, err = parent.Write([]byte("secret")); err != nil {
				t.Fatal(err)
			}
			cmd := exec.Command(argv[0], argv[1:]...)
			cmd.ExtraFiles = []*os.File{child}
			output, err := cmd.CombinedOutput()
			if err != nil {
				t.Fatalf("%v: %s", err, output)
			}
			var observed map[string]any
			if err = json.Unmarshal(output, &observed); err != nil {
				t.Fatalf("%v: %s", err, output)
			}
			if observed["uid"] != float64(100001) || observed["secret_visible"] != false || observed["chmod"] != false || observed["policy_write"] != false || observed["network"] != false {
				t.Fatal(observed)
			}
			if role == "bash" && observed["control"] != nil {
				t.Fatal("tool inherited policy authority", observed)
			}
			if role == "harness" && observed["control"] != "secret" {
				t.Fatal("policy channel missing", observed)
			}
			status := observed["status"].(string)
			if !strings.Contains(status, "NoNewPrivs:\t1") || !strings.Contains(status, "CapEff:\t0000000000000000") {
				t.Fatal(status)
			}
			t.Log(string(output))
		})
	}
}
func TestRealFreezeAndFenceDetachedWriter(t *testing.T) {
	cfg, root := facility(t)
	if err := os.Chown(root, 100001, 100001); err != nil {
		t.Fatal(err)
	}
	s := scope(t, cfg, "bash")
	code := `import os,time
if os.fork(): time.sleep(60)
else:
 os.setsid()
 f=open('/work/surface/writes','ab',buffering=0)
 while True:f.write(b'x');time.sleep(.005)`
	argv, err := s.Command([]string{"/usr/bin/python3", "-c", code}, []Mount{{root, "/work/surface", true}}, "/work/surface", 60)
	if err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command(argv[0], argv[1:]...)
	cmd.Stderr = os.Stderr
	if err = cmd.Start(); err != nil {
		t.Fatal(err)
	}
	defer cmd.Wait()
	filename := filepath.Join(root, "writes")
	deadline := time.Now().Add(3 * time.Second)
	for {
		if f, e := os.Stat(filename); e == nil && f.Size() > 0 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("writer did not start")
		}
		time.Sleep(10 * time.Millisecond)
	}
	children, err := filepath.Glob(filepath.Join(s.Path, "NSJAIL.*"))
	if err != nil || len(children) != 1 {
		t.Fatal(children, err)
	}
	for file, want := range map[string]string{"memory.max": "134217728", "pids.max": "32", "cpu.max": "500000 1000000"} {
		got, err := os.ReadFile(filepath.Join(children[0], file))
		if err != nil || strings.TrimSpace(string(got)) != want {
			t.Fatal(file, string(got), err)
		}
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	if err = s.Freeze(ctx); err != nil {
		t.Fatal(err)
	}
	before, err := os.ReadFile(filename)
	if err != nil {
		t.Fatal(err)
	}
	time.Sleep(100 * time.Millisecond)
	after, _ := os.ReadFile(filename)
	if string(before) != string(after) {
		t.Fatal("frozen domain kept writing")
	}
	if err = s.Thaw(); err != nil {
		t.Fatal(err)
	}
	time.Sleep(50 * time.Millisecond)
	if err = s.Fence(ctx); err != nil {
		t.Fatal(err)
	}
	before, _ = os.ReadFile(filename)
	time.Sleep(100 * time.Millisecond)
	after, _ = os.ReadFile(filename)
	if string(before) != string(after) {
		t.Fatal("detached writer survived cgroup fencing")
	}
	t.Logf("freeze and fence confirmed from cgroup.events; final bytes=%d", len(after))
}
