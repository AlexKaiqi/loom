package sshprocess

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"golang.org/x/crypto/ssh"
	"loom/runtime/contracts"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func realClient(t *testing.T) (*Client, string) {
	t.Helper()
	options := os.Getenv("LOOM_SSH_OPTIONS")
	if options == "" {
		t.Skip("real prepared SSH/systemd/NsJail facility not requested")
	}
	b, e := os.ReadFile(options)
	if e != nil {
		t.Fatal(e)
	}
	key, e := os.ReadFile(os.Getenv("LOOM_SSH_KEY_FILE"))
	if e != nil {
		t.Fatal(e)
	}
	x, e := Open(contracts.Binding{Provider: Provider, ServiceID: "process-validation", Endpoint: os.Getenv("LOOM_SSH_ENDPOINT"), OptionsJSON: string(b)}, string(key))
	if e != nil {
		t.Fatal(e)
	}
	evidence := os.Getenv("LOOM_SSH_EVIDENCE")
	if evidence == "" {
		t.Fatal("new evidence directory required")
	}
	out := filepath.Join(evidence, t.Name())
	if e = os.MkdirAll(filepath.Dir(out), 0700); e != nil {
		t.Fatal(e)
	}
	if e = os.Mkdir(out, 0700); e != nil {
		t.Fatal(e)
	}
	return x.(*Client), out
}
func observe(t *testing.T, out, name string, v any) {
	t.Helper()
	b, e := json.MarshalIndent(v, "", "  ")
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(out, name+".json"), b, 0600); e != nil {
		t.Fatal(e)
	}
}
func request(t *testing.T, out, script string) contracts.Request {
	t.Helper()
	dir := filepath.Join(out, "content")
	if e := os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	return contracts.Request{OperationID: fmt.Sprintf("%s-%d", t.Name(), time.Now().UnixNano()), Target: "code", Script: script, Timeout: 10 * time.Second, Directory: dir, ArtifactsDir: filepath.Join(out, "artifacts")}
}
func observer(t *testing.T, args ...string) string {
	t.Helper()
	container := os.Getenv("LOOM_SSH_OBSERVER_CONTAINER")
	if container == "" {
		t.Fatal("direct Linux test observer required")
	}
	b, e := exec.Command("docker", append([]string{"exec", container}, args...)...).CombinedOutput()
	if e != nil {
		t.Fatalf("observer: %s %v", b, e)
	}
	return string(b)
}

func TestRealExecute(t *testing.T) {
	c, out := realClient(t)
	rq := request(t, out, `printf 'task-out\n'; printf 'task-err\n' >&2; printf changed > result; exit 7`)
	start := time.Now()
	var phases []contracts.Checkpoint
	timings := map[string]float64{}
	r, e := c.Execute(context.Background(), rq, func(cp contracts.Checkpoint) error {
		phases = append(phases, cp)
		timings[cp.Phase] = float64(time.Since(start).Microseconds()) / 1000
		return nil
	})
	observe(t, out, "result", r)
	observe(t, out, "checkpoints", phases)
	observe(t, out, "timings-ms", timings)
	if e != nil || r.State != "completed" || r.ExitCode == nil || *r.ExitCode != 7 || !r.Released {
		t.Fatalf("%+v %v", r, e)
	}
	if r.Stdout != "task-out\n" || !strings.Contains(r.Stderr, "task-err\n") {
		t.Fatal("output changed", r.Stdout, r.Stderr)
	}
	b, e := os.ReadFile(filepath.Join(rq.Directory, "result"))
	if e != nil || string(b) != "changed" {
		t.Fatal("content not delivered", e, string(b))
	}
	t.Logf("ready %.2f ms; complete %.2f ms", timings["prepared"], float64(time.Since(start).Microseconds())/1000)
}

func TestRealIsolationAndReadOnly(t *testing.T) {
	c, out := realClient(t)
	rq := request(t, out, `python3 - <<'PY'
import os,pathlib,socket,subprocess
assert os.getuid()==65534
assert 'LOOM_SSH_KEY_FILE' not in os.environ
for p in ('/root/.ssh','/var/lib/loom-process','/work/.loom','/run/systemd','/sys/fs/cgroup'):
 assert not pathlib.Path(p).exists(),p
assert pathlib.Path('reference/data').read_text()=='fixed'
try: pathlib.Path('reference/data').write_text('tamper')
except OSError: pass
else: raise AssertionError('read resource writable')
try: pathlib.Path('/usr/bin/loom-tamper').write_text('tamper')
except OSError: pass
else: raise AssertionError('toolchain writable')
try: socket.create_connection(('192.0.2.1',80),.1)
except OSError as e: assert e.errno==101
else: raise AssertionError('network allowed')
pathlib.Path('result').write_text('isolated')
print(subprocess.check_output(['id'],text=True).strip())
PY`)
	os.Mkdir(filepath.Join(rq.Directory, "reference"), 0755)
	os.WriteFile(filepath.Join(rq.Directory, "reference/data"), []byte("fixed"), 0600)
	rq.ReadOnlyPaths = []string{"reference"}
	r, e := c.Execute(context.Background(), rq, func(cp contracts.Checkpoint) error {
		if cp.Phase == "prepared" {
			observed := observer(t, "cat", "/sys/fs/cgroup/system.slice/"+cp.ExecutionID+"/memory.max", "/sys/fs/cgroup/system.slice/"+cp.ExecutionID+"/pids.max")
			observe(t, out, "native-limits", observed)
			if observed != "536870912\n64\n" {
				return errors.New("native limits missing")
			}
		}
		return nil
	})
	observe(t, out, "result", r)
	if e != nil || r.State != "completed" || r.ExitCode == nil || *r.ExitCode != 0 {
		t.Fatalf("%+v %v", r, e)
	}
	b, e := os.ReadFile(filepath.Join(rq.Directory, "reference/data"))
	if e != nil || string(b) != "fixed" {
		t.Fatal("readonly content changed")
	}
}

func TestRealAllocationReuseAndOriginalDestination(t *testing.T) {
	c, out := realClient(t)
	ctx := context.Background()
	requestID := fmt.Sprintf("reuse-%d", time.Now().UnixNano())
	a, e := c.Acquire(ctx, requestID, "code")
	if e != nil {
		t.Fatal(e)
	}
	if _, e = c.Acquire(ctx, requestID, "code"); e == nil {
		t.Fatal("allocation replay accepted")
	}
	q, e := c.InspectAllocation(ctx, requestID, a.ID)
	if e != nil || q.State != "observed" {
		t.Fatal(q, e)
	}
	for i := 0; i < 2; i++ {
		sub := filepath.Join(out, fmt.Sprint(i))
		os.Mkdir(sub, 0700)
		rq := request(t, sub, "echo once > result")
		rq.SandboxID = a.ID
		rq.AllocationRequestID = requestID
		r, e := c.Execute(ctx, rq, nil)
		observe(t, sub, "result", r)
		if e != nil || r.State != "completed" || r.Released {
			t.Fatalf("%+v %v", r, e)
		}
		wrong := c.binding
		wrong.ServiceID = "different"
		if _, e = c.Cancel(ctx, a.ID, r.ExecutionID, wrong); e == nil {
			t.Fatal("changed destination accepted")
		}
		q, e := c.Query(ctx, a.ID, r.ExecutionID, c.binding)
		if e != nil {
			t.Fatal(e)
		}
		observe(t, sub, "query", q)
		// Reusing an operation ID cannot execute again, even in an allocation
		// that is explicitly reused for separate operations.
		rq.ArtifactsDir = filepath.Join(sub, "replay-artifacts")
		repeat, e := c.Execute(ctx, rq, nil)
		if e != nil || repeat.State != "unknown" || !strings.Contains(repeat.Error, "File exists") {
			t.Fatal("operation replay not refused", repeat, e)
		}
	}
	if e = c.Release(ctx, a.ID); e != nil {
		t.Fatal(e)
	}
	q, e = c.InspectAllocation(ctx, requestID, a.ID)
	if e != nil || q.State != "absent" {
		t.Fatal(q, e)
	}
	if _, e = c.Acquire(ctx, requestID, "code"); e == nil {
		t.Fatal("released identity recreated")
	}
}

func TestRealReadinessGateAndCancellation(t *testing.T) {
	c, out := realClient(t)
	rq := request(t, out, "echo should-not-run > forbidden")
	r, e := c.Execute(context.Background(), rq, func(cp contracts.Checkpoint) error {
		if cp.Phase == "prepared" {
			return errors.New("injected checkpoint persistence failure")
		}
		return nil
	})
	observe(t, out, "result", r)
	if e != nil || r.State != "unknown" || r.ExecutionID == "" {
		t.Fatal(r, e)
	}
	p, _ := c.allocationPath(r.SandboxID)
	p += "/" + digest(rq.OperationID)
	observer(t, "test", "!", "-e", p+"/task/forbidden")
	q, e := c.Cancel(context.Background(), r.SandboxID, r.ExecutionID, c.binding)
	if e != nil {
		t.Fatal(e)
	}
	observe(t, out, "cancel", q)
	observer(t, "test", "!", "-e", p+"/task/forbidden")
	if e = c.Release(context.Background(), r.SandboxID); e == nil {
		t.Fatal("unacknowledged content was discarded")
	}
}

func TestRealBackgroundWriterFenced(t *testing.T) {
	c, out := realClient(t)
	rq := request(t, out, `(while true; do echo child >> changing; sleep .01; done) &
echo parent; sleep .05`)
	r, e := c.Execute(context.Background(), rq, nil)
	observe(t, out, "result", r)
	if e != nil || r.State != "completed" || r.ExitCode == nil || *r.ExitCode != 0 {
		t.Fatal(r, e)
	}
	first, e := os.ReadFile(filepath.Join(rq.Directory, "changing"))
	if e != nil {
		t.Fatal(e)
	}
	time.Sleep(100 * time.Millisecond)
	second, e := os.ReadFile(filepath.Join(rq.Directory, "changing"))
	if e != nil || string(first) != string(second) {
		t.Fatal("background writer survived")
	}
	observer(t, "test", "!", "-d", "/sys/fs/cgroup/system.slice/"+r.ExecutionID)
}

func TestRealContentConflictRetainsRemoteResult(t *testing.T) {
	c, out := realClient(t)
	rq := request(t, out, "echo task > result")
	r, e := c.Execute(context.Background(), rq, func(cp contracts.Checkpoint) error {
		if cp.Phase == "prepared" {
			return os.WriteFile(filepath.Join(rq.Directory, "human"), []byte("new"), 0600)
		}
		return nil
	})
	observe(t, out, "result", r)
	if e != nil || r.State != "unknown" || r.ExitCode == nil || r.Released {
		t.Fatal(r, e)
	}
	if _, e = os.Stat(filepath.Join(rq.Directory, "result")); !os.IsNotExist(e) {
		t.Fatal("conflicting result published")
	}
	p, _ := c.allocationPath(r.SandboxID)
	raw := observer(t, "cat", p+"/"+digest(rq.OperationID)+"/task/result")
	if raw != "task\n" {
		t.Fatal("remote outcome lost")
	}
	if e = c.Release(context.Background(), r.SandboxID); e == nil {
		t.Fatal("pending content released")
	}
}

func TestRealPinnedHostKeyRejectsBeforeEffects(t *testing.T) {
	c, out := realClient(t)
	before := observer(t, "ls", "-A", c.options.StateDirectory)
	public, _, e := ed25519.GenerateKey(rand.Reader)
	if e != nil {
		t.Fatal(e)
	}
	key, e := ssh.NewPublicKey(public)
	if e != nil {
		t.Fatal(e)
	}
	c.hostKey = key
	r, e := c.Execute(context.Background(), request(t, out, "touch forbidden"), nil)
	observe(t, out, "result", r)
	if e != nil || r.State != "unknown" || r.SandboxID != "" || !strings.Contains(r.Error, "host key mismatch") {
		t.Fatal(r, e)
	}
	if after := observer(t, "ls", "-A", c.options.StateDirectory); after != before {
		t.Fatal("untrusted host received effects")
	}
}

func TestRealDisconnectHasNativeDeadline(t *testing.T) {
	c, out := realClient(t)
	c.options.RequestTimeoutSeconds = 1
	rq := request(t, out, "echo partial > result; sleep 30")
	rq.Timeout = 2 * time.Second
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	r, e := c.Execute(ctx, rq, func(cp contracts.Checkpoint) error {
		if cp.Phase == "accepted" {
			cancel()
		}
		return nil
	})
	observe(t, out, "result", r)
	if e != nil || r.State != "unknown" || r.Released {
		t.Fatal(r, e)
	}
	time.Sleep(3500 * time.Millisecond)
	q, e := c.Query(context.Background(), r.SandboxID, r.ExecutionID, c.binding)
	if e != nil {
		t.Fatal(e)
	}
	observe(t, out, "after-deadline", q)
	s := q["status"].(map[string]string)
	if s["Result"] != "timeout" && s["Result"] != "exit-code" {
		t.Fatal("native timeout absent", s)
	}
	observer(t, "test", "!", "-d", "/sys/fs/cgroup/system.slice/"+r.ExecutionID)
	if e = c.Release(context.Background(), r.SandboxID); e == nil {
		t.Fatal("unknown outcome discarded")
	}
}

func TestRealLatency(t *testing.T) {
	c, out := realClient(t)
	ctx := context.Background()
	var samples []map[string]any
	allocationRequest := fmt.Sprintf("latency-reuse-%d", time.Now().UnixNano())
	a, e := c.Acquire(ctx, allocationRequest, "code")
	if e != nil {
		t.Fatal(e)
	}
	for _, reuse := range []bool{false, true} {
		for i := 0; i < 5; i++ {
			name := fmt.Sprintf("reuse-%t-%d", reuse, i)
			sub := filepath.Join(out, name)
			os.Mkdir(sub, 0700)
			rq := request(t, sub, "printf ready; printf done > result")
			os.WriteFile(filepath.Join(rq.Directory, "input"), []byte("tiny"), 0600)
			if reuse {
				rq.SandboxID = a.ID
				rq.AllocationRequestID = allocationRequest
			}
			start := time.Now()
			sample := map[string]any{"reuse": reuse, "sample": i, "input_bytes": 4}
			r, e := c.Execute(ctx, rq, func(cp contracts.Checkpoint) error {
				sample[cp.Phase+"_ms"] = float64(time.Since(start).Microseconds()) / 1000
				return nil
			})
			sample["complete_ms"] = float64(time.Since(start).Microseconds()) / 1000
			samples = append(samples, sample)
			observe(t, sub, "result", r)
			if e != nil || r.State != "completed" || r.ExitCode == nil || *r.ExitCode != 0 {
				t.Fatal(r, e)
			}
		}
	}
	if e = c.Release(ctx, a.ID); e != nil {
		t.Fatal(e)
	}
	observe(t, out, "samples", samples)
}

func TestRealConcurrentViews(t *testing.T) {
	c, out := realClient(t)
	ctx := context.Background()
	type outcome struct {
		result contracts.Result
		err    error
	}
	done := make(chan outcome, 2)
	for i := 0; i < 2; i++ {
		sub := filepath.Join(out, fmt.Sprint(i))
		os.Mkdir(sub, 0700)
		rq := request(t, sub, fmt.Sprintf("test ! -e ../other && sleep .2 && test \"$(cat input)\" = %d && printf %d > result", i, i))
		os.WriteFile(filepath.Join(rq.Directory, "input"), []byte(fmt.Sprint(i)), 0600)
		go func() { r, e := c.Execute(ctx, rq, nil); done <- outcome{r, e} }()
	}
	var results []contracts.Result
	for i := 0; i < 2; i++ {
		got := <-done
		results = append(results, got.result)
		if got.err != nil || got.result.State != "completed" || got.result.ExitCode == nil || *got.result.ExitCode != 0 {
			t.Error(got.result, got.err)
		}
	}
	observe(t, out, "results", results)
	if results[0].SandboxID == results[1].SandboxID {
		t.Fatal("concurrent allocations share identity")
	}
	for i := 0; i < 2; i++ {
		b, e := os.ReadFile(filepath.Join(out, fmt.Sprint(i), "content/result"))
		if e != nil || string(b) != fmt.Sprint(i) {
			t.Fatal("cross-task content", e, string(b))
		}
	}
}

func TestRealFaultCheckpointsKeepOriginalResponsibility(t *testing.T) {
	for _, phase := range []string{"created", "session_created", "accepted", "native_result"} {
		t.Run(phase, func(t *testing.T) {
			c, out := realClient(t)
			rq := request(t, out, "echo once >> executions")
			r, e := c.Execute(context.Background(), rq, func(cp contracts.Checkpoint) error {
				if cp.Phase == phase {
					return errors.New("injected custody failure at " + phase)
				}
				return nil
			})
			observe(t, out, "result", r)
			if e != nil || r.State != "unknown" || r.Released {
				t.Fatal(r, e)
			}
			a, e := c.InspectAllocation(context.Background(), rq.OperationID, r.SandboxID)
			if e != nil || a.ID != r.SandboxID || a.State != "observed" {
				t.Fatal(a, e)
			}
			observe(t, out, "original-allocation", a)
			if _, e = os.Stat(filepath.Join(rq.Directory, "executions")); !os.IsNotExist(e) {
				t.Fatal("unconfirmed content published")
			}
			p, _ := c.allocationPath(r.SandboxID)
			p += "/" + digest(rq.OperationID) + "/task/executions"
			if phase == "accepted" || phase == "native_result" {
				time.Sleep(150 * time.Millisecond)
				if observer(t, "cat", p) != "once\n" {
					t.Fatal("original command lost or repeated")
				}
				if e = c.Release(context.Background(), r.SandboxID); e == nil {
					t.Fatal("pending content deleted")
				}
			} else {
				observer(t, "test", "!", "-e", p)
			}
			rq.ArtifactsDir = filepath.Join(out, "repeat-artifacts")
			again, e := c.Execute(context.Background(), rq, nil)
			if e != nil || again.State != "unknown" || !strings.Contains(again.Error, "File exists") {
				t.Fatal("replay not rejected", again, e)
			}
		})
	}
}
