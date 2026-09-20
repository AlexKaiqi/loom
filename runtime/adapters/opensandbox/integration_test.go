package opensandbox

import (
	"context"

	"encoding/json"
	"errors"
	"fmt"
	"loom/runtime/filesystem"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// Real tests are opt-in: they require the separately deployed official service.
// Docker is a direct test observer/fault injector for this batch's containers.
func realClient(t *testing.T) (*Client, string) {
	t.Helper()
	endpoint := os.Getenv("LOOM_SANDBOX_ENDPOINT")
	if endpoint == "" {
		t.Skip("real OpenSandbox service not requested")
	}
	key, err := os.ReadFile(os.Getenv("LOOM_SANDBOX_KEY_FILE"))
	if err != nil {
		t.Fatal(err)
	}
	c, err := New(Config{ServiceID: "work-directory-validation", Endpoint: endpoint, APIKey: strings.TrimSpace(string(key)), Image: testImage})
	if err != nil {
		t.Fatal(err)
	}
	batch := os.Getenv("LOOM_SANDBOX_EVIDENCE")
	if batch == "" {
		t.Fatal("new evidence directory required")
	}
	out := filepath.Join(batch, t.Name())
	if err = os.MkdirAll(filepath.Dir(out), 0700); err != nil {
		t.Fatal(err)
	}
	if err = os.Mkdir(out, 0700); err != nil {
		t.Fatal(err)
	}
	return c, out
}
func observation(t *testing.T, out, name string, value any) {
	t.Helper()
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(out, name+".json"), data, 0600); err != nil {
		t.Fatal(err)
	}
}
func docker(t *testing.T, args ...string) string {
	t.Helper()
	value, err := exec.Command("docker", args...).CombinedOutput()
	if err != nil {
		t.Fatalf("docker %v: %s %v", args, value, err)
	}
	return string(value)
}
func operation(t *testing.T) string {
	return fmt.Sprintf("loom-go-%.30s-%d", strings.ToLower(t.Name()), time.Now().UnixNano())
}
func cleanup(t *testing.T, c *Client, result Result) {
	t.Helper()
	if result.SandboxID != "" && !result.Released {
		if err := c.Release(context.Background(), result.SandboxID); err != nil {
			t.Error(err)
		}
	}
}
func request(t *testing.T, out, target, script string) Request {
	t.Helper()
	content := filepath.Join(out, target)
	if err := os.Mkdir(content, 0700); err != nil {
		t.Fatal(err)
	}
	return Request{OperationID: operation(t), Target: target, Script: script, Timeout: 15 * time.Second, Directory: content, ArtifactsDir: filepath.Join(out, target+"-artifacts")}
}

func TestRealTargets(t *testing.T) {
	c, out := realClient(t)
	ctx := context.Background()
	var results []Result
	t.Setenv("LOOM_SYNTHETIC_PROVIDER_KEY", "must-not-reach-task")
	for _, target := range []string{"alpha", "beta"} {
		req := request(t, out, target, `python - <<'PY'
import os,socket,pathlib
assert os.getuid()==65534
status=pathlib.Path('/proc/self/status').read_text()
for field in ('CapEff','CapPrm','CapAmb'):
 assert int(status.split(field+':')[1].split()[0],16)==0,status
assert status.split('NoNewPrivs:')[1].split()[0]=='1',status
assert 'LOOM_SYNTHETIC_PROVIDER_KEY' not in os.environ
assert not pathlib.Path('/var/run/docker.sock').exists()
for target in ('alpha','beta'):
 if pathlib.Path.cwd().name!=target: assert not pathlib.Path('/workspace',target).exists()
try: socket.socket()
except PermissionError: pass
else: raise AssertionError('network allowed')
try: pathlib.Path('/etc/loom-execd.toml').write_text('tamper')
except OSError: pass
else: raise AssertionError('public config writable')
pathlib.Path('report').write_text(str(sum(map(int,pathlib.Path('input').read_text().split()))))
pathlib.Path('delete').unlink()
print('uid=65534;sum=10;network=denied')
PY`)
		os.WriteFile(filepath.Join(req.Directory, "input"), []byte("2 3 5"), 0600)
		os.WriteFile(filepath.Join(req.Directory, "delete"), []byte("old"), 0600)
		var checkpoints []Checkpoint
		result, err := c.Execute(ctx, req, func(p Checkpoint) error {
			if p.Binding != c.Binding() {
				return errors.New("checkpoint lost original execution binding")
			}
			checkpoints = append(checkpoints, p)
			observation(t, out, target+"-checkpoints", checkpoints)
			if p.Phase == "created" {
				raw := docker(t, "inspect", "sandbox-"+p.SandboxID)
				var inspect []map[string]any
				if err := json.Unmarshal([]byte(raw), &inspect); err != nil {
					return err
				}
				observation(t, out, target+"-container", inspect)
				for _, m := range inspect[0]["Mounts"].([]any) {
					mount := m.(map[string]any)
					if mount["Type"] == "bind" && (mount["Destination"] != "/etc/loom-execd.toml" || mount["RW"] != false) {
						return errors.New("unexpected task bind")
					}
				}
				env := inspect[0]["Config"].(map[string]any)["Env"].([]any)
				for _, e := range env {
					if strings.Contains(e.(string), "LOOM_SYNTHETIC_PROVIDER_KEY") {
						return errors.New("secret leaked")
					}
				}
			}
			return nil
		})
		results = append(results, result)
		observation(t, out, "results", results)
		cleanup(t, c, result)
		if err != nil || result.State != "completed" || !result.Released || result.ExitCode == nil || *result.ExitCode != 0 {
			t.Fatalf("%+v %v", result, err)
		}
		if result.Binding != c.Binding() || len(checkpoints) != 7 || checkpoints[0].SandboxID != "" {
			t.Fatal("destination history incomplete", result.Binding, checkpoints)
		}
		for i, phase := range []string{"planned", "created", "session_created", "prepared", "accepted", "native_result", "execution_fenced"} {
			if checkpoints[i].Phase != phase || (i > 0 && checkpoints[i].SandboxID != result.SandboxID) {
				t.Fatal("execution custody ordering or destination changed", checkpoints)
			}
		}
		if checkpoints[5].NativeResult["exit_code"] == nil || len(checkpoints[5].Artifacts) != 5 || checkpoints[6].ExecutionID != result.ExecutionID {
			t.Fatal("native outcome was not retained before execution fencing", checkpoints)
		}
		if ready := checkpoints[3].Readiness; ready == nil || ready.Platform != "linux" || ready.Architecture == "" || ready.UID != 65534 || ready.Network != "denied" || ready.Tools["python"] == "" {
			t.Fatal("actual execution capabilities not retained before task dispatch", ready)
		}
		got, _ := os.ReadFile(filepath.Join(req.Directory, "report"))
		if string(got) != "10" {
			t.Fatal(string(got))
		}
		if _, err := os.Stat(filepath.Join(req.Directory, "delete")); !os.IsNotExist(err) {
			t.Fatal("remote deletion not published", err)
		}
		for _, a := range result.Artifacts {
			data, err := os.ReadFile(a.Path)
			if err != nil || digestBytes(data) != a.SHA256 {
				t.Fatal("artifact digest", a, err)
			}
		}
		remaining := docker(t, "ps", "-aq", "--filter", "label=loom.operation="+req.OperationID)
		observation(t, out, target+"-remaining", remaining)
		if strings.TrimSpace(remaining) != "" {
			t.Fatal("container retained")
		}
	}
	if results[0].SandboxID == results[1].SandboxID {
		t.Fatal("domains share instance")
	}
}
func TestRealLostAcceptanceCancel(t *testing.T) {
	c, out := realClient(t)
	ctx := context.Background()
	req := request(t, out, "userspace", "echo once >> dispatch-count; (while :; do echo child >> heartbeat; sleep .1; done) & wait")
	result, err := c.Execute(ctx, req, func(p Checkpoint) error {
		if p.Phase == "accepted" {
			return errors.New("injected accepted-checkpoint loss")
		}
		return nil
	})
	observation(t, out, "result", result)
	defer cleanup(t, c, result)
	if err != nil || result.State != "unknown" || result.Released || result.ExecutionID == "" {
		t.Fatal(result, err)
	}
	status, err := c.Query(ctx, result.SandboxID, result.ExecutionID, result.Binding)
	observation(t, out, "query", status)
	if err != nil || status["running"] != true {
		t.Fatal(status, err)
	}
	stopped, err := c.Cancel(ctx, result.SandboxID, result.ExecutionID, result.Binding)
	observation(t, out, "cancel", stopped)
	if err != nil {
		t.Fatal(err)
	}
	assertNoTaskProcess(t, out, result.SandboxID)
	marker := docker(t, "exec", "sandbox-"+result.SandboxID, "cat", "/workspace/task/dispatch-count")
	observation(t, out, "dispatch-count", marker)
	if marker != "once\n" {
		t.Fatal(marker)
	}
	entries, _ := os.ReadDir(req.Directory)
	if len(entries) != 0 {
		t.Fatal("unknown published files")
	}
}
func assertNoTaskProcess(t *testing.T, out, id string) {
	t.Helper()
	processes := docker(t, "top", "sandbox-"+id, "-eo", "uid,pid,ppid,args")
	observation(t, out, "processes", processes)
	for _, line := range strings.Split(processes, "\n") {
		parts := strings.Fields(line)
		if len(parts) > 0 && parts[0] == "65534" {
			t.Fatalf("task process survived: %s", processes)
		}
	}
}
func TestRealTimeoutChildren(t *testing.T) {
	c, out := realClient(t)
	req := request(t, out, "userspace", "(while :; do echo child >> heartbeat; sleep .1; done) & wait")
	req.Timeout = 600 * time.Millisecond
	result, err := c.Execute(context.Background(), req, nil)
	observation(t, out, "result", result)
	defer cleanup(t, c, result)
	if err != nil || result.State != "unknown" || result.Released || !strings.Contains(result.Error, "deadline") {
		t.Fatal(result, err)
	}
	assertNoTaskProcess(t, out, result.SandboxID)
}
func TestRealRetention(t *testing.T) {
	c, out := realClient(t)
	req := request(t, out, "userspace", `echo once >> dispatch-count; python -c "import sys; sys.stdout.write('x'*(17*1024*1024))"`)
	result, err := c.Execute(context.Background(), req, nil)
	observation(t, out, "result", result)
	defer cleanup(t, c, result)
	if err != nil || result.State != "unknown" || result.Released || !strings.Contains(result.Error, "retention") {
		t.Fatal(result.State, result.Error, err)
	}
	marker := docker(t, "exec", "sandbox-"+result.SandboxID, "cat", "/workspace/task/dispatch-count")
	observation(t, out, "dispatch-count", marker)
	if marker != "once\n" {
		t.Fatal(marker)
	}
}
func TestRealDeadExecdRelease(t *testing.T) {
	c, out := realClient(t)
	req := request(t, out, "userspace", "echo never")
	result, err := c.Execute(context.Background(), req, func(p Checkpoint) error {
		if p.Phase == "prepared" {
			return errors.New("controlled pause before task")
		}
		return nil
	})
	observation(t, out, "result", result)
	if err != nil || result.SandboxID == "" || !strings.HasSuffix(result.ExecutionID, "/") || !strings.Contains(result.Error, "controlled pause") {
		t.Fatal(result, err)
	}
	docker(t, "exec", "sandbox-"+result.SandboxID, "pkill", "execd")
	running := docker(t, "inspect", "sandbox-"+result.SandboxID, "--format", "{{.State.Running}}")
	if strings.TrimSpace(running) != "true" {
		t.Fatal("container must survive fault")
	}
	if err = c.Release(context.Background(), result.SandboxID); err != nil {
		t.Fatal(err)
	}
	remaining := docker(t, "ps", "-aq", "--filter", "name=^/sandbox-"+result.SandboxID+"$")
	observation(t, out, "release", map[string]any{"container_after_execd_death": running, "remaining": remaining})
	if strings.TrimSpace(remaining) != "" {
		t.Fatal("lifecycle release failed")
	}
}
func TestRealPublicationConflict(t *testing.T) {
	c, out := realClient(t)
	for _, mode := range []string{"edit", "identity"} {
		batch := filepath.Join(out, mode)
		os.Mkdir(batch, 0700)
		req := request(t, batch, "userspace", "sleep .2; printf remote > report")
		os.WriteFile(filepath.Join(req.Directory, "notes"), []byte("initial"), 0600)
		result, err := c.Execute(context.Background(), req, func(p Checkpoint) error {
			if p.Phase == "accepted" {
				if mode == "identity" {
					if err := os.Rename(req.Directory, req.Directory+"-old"); err != nil {
						return err
					}
					if err := os.Mkdir(req.Directory, 0700); err != nil {
						return err
					}
				}
				return os.WriteFile(filepath.Join(req.Directory, "notes"), []byte("human edit"), 0600)
			}
			return nil
		})
		observation(t, batch, "result", result)
		defer cleanup(t, c, result)
		if err != nil || result.State != "unknown" || result.Released || !strings.Contains(result.Error, "changed") || result.ExitCode == nil || *result.ExitCode != 0 {
			t.Fatal(result, err)
		}
		// A publication conflict keeps the original allocation for reconciliation;
		// the completed execution domain is fenced independently of that retention.
		remaining := docker(t, "ps", "-q", "--filter", "name=^/sandbox-"+result.SandboxID+"$")
		observation(t, batch, "retained-allocation", remaining)
		if strings.TrimSpace(remaining) == "" {
			t.Fatal("unresolved content delivery lost its allocation")
		}
		assertNoTaskProcess(t, batch, result.SandboxID)
		got, _ := os.ReadFile(filepath.Join(req.Directory, "notes"))
		if string(got) != "human edit" {
			t.Fatal("human bytes lost")
		}
		if _, err := os.Stat(filepath.Join(req.Directory, "report")); !os.IsNotExist(err) {
			t.Fatal("remote output overwritten local")
		}
		a, err := os.Open(filepath.Join(req.ArtifactsDir, "workspace.tar"))
		if err != nil {
			t.Fatal(err)
		}
		staged := filepath.Join(batch, "observed-remote")
		os.Mkdir(staged, 0700)
		if err = filesystem.Extract(a, staged); err != nil {
			t.Fatal(err)
		}
		a.Close()
		got, _ = os.ReadFile(filepath.Join(staged, "report"))
		if string(got) != "remote" {
			t.Fatal("remote archive lost")
		}
	}
}
func TestRealArtifactFailure(t *testing.T) {
	c, out := realClient(t)
	req := request(t, out, "userspace", "echo confirmed; printf data > result")
	result, err := c.Execute(context.Background(), req, func(p Checkpoint) error {
		if p.Phase == "accepted" {
			return os.Mkdir(filepath.Join(req.ArtifactsDir, "stdout.txt"), 0700)
		}
		return nil
	})
	observation(t, out, "result", result)
	defer cleanup(t, c, result)
	if err != nil || result.State != "unknown" || result.Released || result.ExitCode == nil || *result.ExitCode != 0 || result.Native["status"] == nil {
		t.Fatal(result, err)
	}
	entries, _ := os.ReadDir(req.Directory)
	if len(entries) != 0 {
		t.Fatal("artifact failure published incomplete files")
	}
}

func TestRealMissingCapabilityNeverDispatchesTask(t *testing.T) {
	c, out := realClient(t)
	req := request(t, out, "userspace", "printf executed > must-not-exist")
	phases := []string{}
	result, err := c.Execute(context.Background(), req, func(p Checkpoint) error {
		phases = append(phases, p.Phase)
		if p.Phase == "created" {
			// Allocation/bootstrap can succeed even when the required tool cannot
			// run. Change only this batch's instance, before its readiness probe.
			docker(t, "exec", "sandbox-"+p.SandboxID, "sh", "-c", `chmod a-x "$(readlink -f /usr/local/bin/python)"`)
		}
		return nil
	})
	defer cleanup(t, c, result)
	observation(t, out, "result", result)
	observation(t, out, "phases", phases)
	if err != nil || result.State != "unknown" || result.Released || result.Readiness != nil || !strings.HasSuffix(result.ExecutionID, "/") || !strings.Contains(result.Error, "preflight") {
		t.Fatal("missing capability was treated as execution readiness", result, err)
	}
	if len(phases) != 3 || phases[2] != "session_created" {
		t.Fatal("task was prepared or accepted without capabilities", phases)
	}
	docker(t, "exec", "sandbox-"+result.SandboxID, "test", "!", "-e", "/workspace/task/must-not-exist")
	if _, err = os.Stat(filepath.Join(req.ArtifactsDir, "readiness.json")); err != nil {
		t.Fatal("failed readiness evidence not retained", err)
	}
}

func TestRealReadOnlyResourceMount(t *testing.T) {
	c, out := realClient(t)
	req := request(t, out, "reference", "python - <<'PY'\nimport pathlib,os\np=pathlib.Path('reference/value')\nassert p.read_text()=='fixed'\nfor change in (lambda:p.write_text('bad'),lambda:p.chmod(0o777),lambda:pathlib.Path('reference').rename('moved')):\n try:change()\n except OSError:pass\n else:raise AssertionError('read-only resource modified')\npathlib.Path('output').write_text('readonly confirmed')\nPY")
	os.Mkdir(filepath.Join(req.Directory, "reference"), 0700)
	os.WriteFile(filepath.Join(req.Directory, "reference", "value"), []byte("fixed"), 0600)
	req.ReadOnlyPaths = []string{"reference"}
	result, err := c.Execute(context.Background(), req, nil)
	defer cleanup(t, c, result)
	observation(t, out, "result", result)
	if err != nil || result.State != "completed" || result.ExitCode == nil || *result.ExitCode != 0 {
		t.Fatal(result, err)
	}
	value, err := os.ReadFile(filepath.Join(req.Directory, "reference", "value"))
	if err != nil || string(value) != "fixed" {
		t.Fatal("immutable source changed", err)
	}
	output, err := os.ReadFile(filepath.Join(req.Directory, "output"))
	if err != nil || string(output) != "readonly confirmed" {
		t.Fatal("writable target failed", err)
	}
}

func TestRealAllocationReuse(t *testing.T) {
	c, out := realClient(t)
	ctx := context.Background()
	key := operation(t)
	allocation, err := c.Acquire(ctx, key, "reused")
	if err != nil {
		t.Fatal(err)
	}
	observation(t, out, "acquired", allocation)
	released := false
	defer func() {
		if !released {
			if err := c.Release(ctx, allocation.ID); err != nil {
				t.Error(err)
			}
		}
	}()
	for i := 1; i <= 2; i++ {
		req := request(t, out, fmt.Sprintf("copy-%d", i), "printf retained > result.txt")
		req.Target = "reused"
		req.SandboxID = allocation.ID
		req.AllocationRequestID = key
		result, err := c.Execute(ctx, req, nil)
		observation(t, out, fmt.Sprintf("execution-%d", i), result)
		if err != nil || result.State != "completed" || result.SandboxID != allocation.ID || result.Released {
			t.Fatal(result, err)
		}
		raw, err := os.ReadFile(filepath.Join(req.Directory, "result.txt"))
		if err != nil || string(raw) != "retained" {
			t.Fatal(string(raw), err)
		}
	}
	if err = c.Release(ctx, allocation.ID); err != nil {
		t.Fatal(err)
	}
	released = true
	absent, err := c.InspectAllocation(ctx, key, allocation.ID)
	if err != nil || absent.State != "absent" {
		t.Fatal(absent, err)
	}
	observation(t, out, "released", absent)
}
