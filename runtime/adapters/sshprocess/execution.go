package sshprocess

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"loom/runtime/adapters/internal/taskio"
	"loom/runtime/contracts"
	"loom/runtime/filesystem"
)

// Probe and gate run before any task bytes. The FIFO has no writable pathname
// in the jail. Its writer is the authenticated controller outside the view.
const probe = `import json,os,pathlib,platform,socket,subprocess,sys
ro=json.loads(sys.argv[1])
assert platform.system()=='Linux' and os.getuid()==65534 and os.getgid()==65534
s=dict(line.split(':',1) for line in pathlib.Path('/proc/self/status').read_text().splitlines() if ':' in line)
caps={k:s[k].strip() for k in ('CapEff','CapPrm','CapInh','CapBnd','CapAmb')}
assert all(int(caps[k],16)==0 for k in ('CapEff','CapPrm','CapInh','CapAmb'))
assert s['NoNewPrivs'].strip()=='1'
assert list(pathlib.Path('/sys/class/net').glob('*'))==[] if pathlib.Path('/sys/class/net').exists() else True
sock=socket.socket(); sock.settimeout(.1)
try: sock.connect(('192.0.2.1',80))
except OSError as e:
 assert e.errno==101,repr(e)
else: raise AssertionError('network reachable')
finally: sock.close()
shell=subprocess.run(['/bin/bash','--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0]
assert os.getcwd()=='/workspace/task' and os.access('.',os.W_OK)
mounts={line.split()[4]:line.split()[5].split(',') for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines()}
for alias in ro: assert 'ro' in mounts['/workspace/task/'+alias]
for p in ('/root','/home','/work','/run/systemd','/var/run/docker.sock'):
 assert not pathlib.Path(p).exists(),p
print(json.dumps(dict(platform='linux',architecture=platform.machine(),shell=shell,
 tools={'python':platform.python_version()},uid=os.getuid(),gid=os.getgid(),
 process_capabilities=caps,no_new_privileges=True,network='denied',workspace=os.getcwd(),readonly_paths=ro)),flush=True)
`

func unitName(allocation, operation string) string {
	return "loom-" + strings.TrimPrefix(allocation, "alloc-") + "-" + operation + ".service"
}

func (c *Client) startCommand(req contracts.Request, p, unit string) string {
	o := c.options
	seconds := min(int(math.Ceil(req.Timeout.Seconds()))+o.RequestTimeoutSeconds, o.LeaseSeconds)
	args := []string{"systemd-run", "--quiet", "--no-ask-password", "--unit=" + unit, "--service-type=exec",
		"--property=RemainAfterExit=yes", "--property=Restart=no", "--property=KillMode=control-group", "--property=TimeoutStopSec=2s",
		"--property=RuntimeMaxSec=" + strconv.Itoa(seconds) + "s", "--property=MemoryMax=" + strconv.FormatInt(o.MemoryBytes, 10),
		"--property=MemorySwapMax=0", "--property=TasksMax=" + strconv.Itoa(o.Processes), "--property=CPUQuota=" + strconv.Itoa(o.CPUPercent) + "%",
		"--property=StandardOutput=append:" + p + "/stdout", "--property=StandardError=append:" + p + "/stderr", "--",
		o.NsJail, "-Mo", "-q", "--user", "65534:65534:1", "--group", "65534:65534:1", "--time_limit", strconv.Itoa(seconds),
		"--rlimit_as", "max", "--rlimit_fsize", "256", "--rlimit_nofile", "256", "--rlimit_nproc", "max",
		"--cwd", "/workspace/task", "--env", "PATH=/usr/local/loom-python/bin:/usr/local/bin:/usr/bin:/bin", "--env", "HOME=/tmp", "--env", "LANG=C.UTF-8",
		"--tmpfsmount", "/tmp", "--iface_no_lo"}
	// The facility's immutable toolchain is the only shared filesystem view.
	for _, name := range []string{"/usr", "/bin", "/lib"} {
		args = append(args, "--bindmount_ro", name)
	}
	args = append(args, "--bindmount", p+"/task:/workspace/task")
	for _, name := range []string{"probe", "entry", "command", "gate"} {
		args = append(args, "--bindmount_ro", p+"/"+name+":/run/loom-"+name)
	}
	for _, alias := range req.ReadOnlyPaths {
		args = append(args, "--bindmount_ro", p+"/task/"+alias+":/workspace/task/"+alias)
	}
	args = append(args, "--", "/bin/bash", "--noprofile", "--norc", "/run/loom-entry")
	// /lib64 is absent on some Unix architectures. Add it only on the facility.
	command := argv(args...)
	index := strings.Index(command, " '--' '/bin/bash'")
	command = command[:index] + " ${LOOM_LIB64}" + command[index:]
	return "LOOM_LIB64=; if test -e /lib64; then LOOM_LIB64='--bindmount_ro /lib64'; fi\n" + command
}

func (c *Client) Execute(ctx context.Context, req contracts.Request, checkpoint func(contracts.Checkpoint) error) (r contracts.Result, err error) {
	r = contracts.Result{Binding: c.binding, OperationID: req.OperationID, Target: req.Target, State: "unknown", OutputStream: "separate", Artifacts: []contracts.Artifact{}, Native: map[string]any{}}
	if req.OperationID == "" || !namePattern.MatchString(req.Target) || req.Timeout <= 0 || req.Timeout >= time.Duration(c.options.LeaseSeconds)*time.Second {
		return r, errors.New("operation, logical target and timeout within lease required")
	}
	seen := map[string]bool{}
	for _, alias := range req.ReadOnlyPaths {
		if !namePattern.MatchString(alias) || alias == "." || alias == ".." || seen[alias] {
			return r, errors.New("invalid readonly alias")
		}
		seen[alias] = true
	}
	dir, e := filepath.Abs(req.Directory)
	if e != nil {
		return r, e
	}
	identity, e := os.Lstat(dir)
	if e != nil {
		return r, e
	}
	if !identity.IsDir() {
		return r, errors.New("task root must be a real directory")
	}
	artifacts, e := filepath.Abs(req.ArtifactsDir)
	if e != nil {
		return r, e
	}
	if filesystem.Inside(dir, artifacts) {
		return r, errors.New("artifacts must be outside task content")
	}
	if e = os.MkdirAll(artifacts, 0700); e != nil {
		return r, e
	}
	canonicalDir, e := filepath.EvalSymlinks(dir)
	if e != nil {
		return r, e
	}
	canonicalArtifacts, e := filepath.EvalSymlinks(artifacts)
	if e != nil {
		return r, e
	}
	if filesystem.Inside(canonicalDir, canonicalArtifacts) {
		return r, errors.New("artifact alias inside task content")
	}
	for p := canonicalArtifacts; ; p = filepath.Dir(p) {
		if e = filesystem.SyncDir(p); e != nil {
			return r, e
		}
		if filepath.Dir(p) == p {
			break
		}
	}
	temp, e := os.CreateTemp("", "loom-input-")
	if e != nil {
		return r, e
	}
	defer os.Remove(temp.Name())
	defer temp.Close()
	if e = filesystem.Archive(dir, temp); e != nil {
		return r, e
	}
	if _, e = temp.Seek(0, io.SeekStart); e != nil {
		return r, e
	}
	input, e := taskio.Save(filepath.Join(artifacts, "input.tar"), temp)
	if e != nil {
		return r, e
	}
	input.MIMEType = "application/x-tar"
	r.Artifacts = append(r.Artifacts, input)
	if e = filesystem.Unchanged(dir, identity, input.SHA256); e != nil {
		return r, e
	}
	record := func(phase string) error {
		if checkpoint == nil {
			return nil
		}
		var native map[string]any
		if phase == "native_result" {
			native = map[string]any{"exit_code": r.ExitCode, "native": r.Native, "output_stream": "separate"}
		}
		return checkpoint(contracts.Checkpoint{Phase: phase, Binding: r.Binding, SandboxID: r.SandboxID, ExecutionID: r.ExecutionID, Artifacts: r.Artifacts, Readiness: r.Readiness, NativeResult: native})
	}
	if e = record("planned"); e != nil {
		return r, e
	}
	// No retries after this boundary. Loss of transport retains the original
	// identity and native deadline, rather than launching the command again.
	ctx, cancel := context.WithTimeout(ctx, req.Timeout+2*time.Duration(c.options.RequestTimeoutSeconds)*time.Second)
	defer cancel()
	e = c.execute(ctx, req, dir, artifacts, identity, input, &r, record)
	if e != nil {
		r.Error = e.Error()
	}
	return r, nil
}

func (c *Client) execute(ctx context.Context, req contracts.Request, dir, artifacts string, identity os.FileInfo, input contracts.Artifact, r *contracts.Result, record func(string) error) error {
	x, e := c.connect(ctx)
	if e != nil {
		return e
	}
	defer x.close()
	var a contracts.AllocationResult
	if req.SandboxID == "" {
		r.SandboxID = allocationID(req.OperationID)
		a, e = c.acquire(x, req.OperationID, req.Target)
	} else {
		r.SandboxID = req.SandboxID
		a, e = c.inspect(x, req.AllocationRequestID, req.SandboxID)
	}
	if e != nil {
		return e
	}
	if a.ID != r.SandboxID || a.State != "observed" || a.Native["target"] != req.Target {
		return errors.New("original allocation missing or target changed")
	}
	if e = record("created"); e != nil {
		return e
	}
	root, _ := c.allocationPath(r.SandboxID)
	op := digest(req.OperationID)
	p := root + "/" + op
	unit := unitName(r.SandboxID, op)
	r.ExecutionID = unit
	if e = record("session_created"); e != nil {
		return e
	}
	// Persist a unique operation directory before start; never remove this
	// tombstone, even when the transient unit has been garbage collected.
	if _, e = x.run("mkdir -m 711 -- " + quote(p) + " && mkdir -m 755 -- " + quote(p+"/task")); e != nil {
		return e
	}
	readOnly, _ := json.Marshal(append([]string{}, req.ReadOnlyPaths...))
	entry := "set -eu\npython -I /run/loom-probe " + quote(string(readOnly)) + "\nIFS= read -r gate < /run/loom-gate\n[ \"$gate\" = go ]\nexec /bin/bash --noprofile --norc /run/loom-command\n"
	for _, f := range []struct{ name, data string }{{"probe", probe}, {"entry", entry}, {"command", req.Script}} {
		if e = x.put(p+"/"+f.name, strings.NewReader(f.data), 0444); e != nil {
			return e
		}
	}
	f, e := os.Open(input.Path)
	if e != nil {
		return e
	}
	e = errors.Join(x.put(p+"/input.tar", f, 0600), f.Close())
	if e != nil {
		return e
	}
	prepare := "test \"$(sha256sum " + quote(c.options.NsJail) + " | cut -d' ' -f1)\" = " + quote(c.options.NsJailSHA256) + "\n" +
		"test -f /sys/fs/cgroup/cgroup.controllers\n" +
		"tar --no-same-owner -xf " + quote(p+"/input.tar") + " -C " + quote(p+"/task") + "\nchown -R -h 65534:65534 -- " + quote(p+"/task") + "\nchmod u+rwx " + quote(p+"/task") + "\n" +
		"mkfifo -m 400 " + quote(p+"/gate") + "\nchown 65534:65534 " + quote(p+"/gate") + "\nsync -f " + quote(p) + "\n"
	for _, alias := range req.ReadOnlyPaths {
		prepare += "test -d " + quote(p+"/task/"+alias) + " && test ! -L " + quote(p+"/task/"+alias) + "\n"
	}
	if _, e = x.run(prepare + c.startCommand(req, p, unit)); e != nil {
		return e
	}
	deadline := time.Now().Add(time.Duration(c.options.RequestTimeoutSeconds) * time.Second)
	var raw []byte
	lastStatus := time.Now()
	for {
		raw, e = x.read(p+"/stdout", 65536)
		if e == nil && strings.Contains(string(raw), "\n") {
			break
		}
		if e != nil && !os.IsNotExist(e) {
			return e
		}
		if time.Since(lastStatus) > 50*time.Millisecond {
			s, err := nativeStatus(x, unit)
			if err != nil {
				return err
			}
			lastStatus = time.Now()
			if s["ExecMainCode"] != "0" {
				details, _ := x.read(p+"/stderr", 65536)
				return fmt.Errorf("isolated process failed readiness: %s", details)
			}
		}
		if time.Now().After(deadline) {
			return errors.New("isolated process did not become ready; inspect original unit")
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(5 * time.Millisecond):
		}
	}
	line, _, _ := strings.Cut(string(raw), "\n")
	if r.Readiness, e = taskio.ParseReadiness(line, req.ReadOnlyPaths); e != nil {
		return e
	}
	ready, e := taskio.Save(filepath.Join(artifacts, "readiness.json"), strings.NewReader(line))
	if e != nil {
		return e
	}
	ready.MIMEType = "application/json"
	r.Artifacts = append(r.Artifacts, ready)
	status, e := nativeStatus(x, unit)
	if e != nil {
		return e
	}
	r.Native["ready_unit"] = status
	if status["ActiveState"] != "active" || status["InvocationID"] == "" {
		return errors.New("ready unit identity missing")
	}
	invocation := status["InvocationID"]
	limits, e := c.checkLimits(x, unit, status)
	if e != nil {
		return e
	}
	r.Native["cgroup_limits"] = limits
	if e = record("prepared"); e != nil {
		return e
	}
	if _, e = x.run("printf 'go\\n' > " + quote(p+"/gate")); e != nil {
		return e
	}
	if e = record("accepted"); e != nil {
		return e
	}
	deadline = time.Now().Add(req.Timeout)
	for {
		status, e = nativeStatus(x, unit)
		if e != nil {
			return e
		}
		r.Native["status"] = status
		if status["InvocationID"] != invocation {
			return errors.New("original systemd invocation changed")
		}
		if status["ExecMainCode"] != "0" {
			break
		}
		if time.Now().After(deadline) {
			_, stopErr := x.run("systemctl stop " + quote(unit))
			return errors.Join(errors.New("execution deadline exceeded; business result unknown"), stopErr)
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(10 * time.Millisecond):
		}
	}
	if status["ExecMainCode"] != "1" || (status["Result"] != "success" && status["Result"] != "exit-code") {
		return errors.New("native execution did not confirm a normal exit")
	}
	code, e := strconv.Atoi(status["ExecMainStatus"])
	if e != nil {
		return e
	}
	r.ExitCode = &code
	// Before copying output or files, prove that the actual cgroup has no live
	// descendants. Namespace exit alone or a successful shell is insufficient.
	if e = fence(x, unit, status); e != nil {
		return e
	}
	stdout, e := x.read(p+"/stdout", 256<<20)
	if e != nil {
		return e
	}
	stderr, e := x.read(p+"/stderr", 256<<20)
	if e != nil {
		return e
	}
	if !strings.HasPrefix(string(stdout), line+"\n") {
		return errors.New("original readiness/output prefix changed")
	}
	r.Stdout = strings.TrimPrefix(string(stdout), line+"\n")
	r.Stderr = string(stderr)
	native, _ := json.Marshal(r.Native)
	for _, f := range []struct{ name, data, mime string }{{"stdout.txt", r.Stdout, "text/plain"}, {"stderr.txt", r.Stderr, "text/plain"}, {"execution.json", string(native), "application/json"}} {
		a, e := taskio.Save(filepath.Join(artifacts, f.name), strings.NewReader(f.data))
		if e != nil {
			return e
		}
		a.MIMEType = f.mime
		r.Artifacts = append(r.Artifacts, a)
	}
	if e = record("native_result"); e != nil {
		return e
	}
	if e = record("execution_fenced"); e != nil {
		return e
	}
	if _, e = x.run("tar -cf " + quote(p+"/workspace.tar") + " -C " + quote(p+"/task") + " ."); e != nil {
		return e
	}
	output, e := x.files.Open(p + "/workspace.tar")
	if e != nil {
		return e
	}
	saved, e := taskio.Save(filepath.Join(artifacts, "workspace.tar"), output)
	e = errors.Join(e, output.Close())
	if e != nil {
		return e
	}
	saved.MIMEType = "application/x-tar"
	r.Artifacts = append(r.Artifacts, saved)
	snapshot, e := os.Open(saved.Path)
	if e != nil {
		return e
	}
	e = errors.Join(filesystem.Restore(snapshot, dir, identity, input.SHA256), snapshot.Close())
	if e != nil {
		return e
	}
	if e = x.put(p+"/delivered", strings.NewReader(saved.SHA256+"\n"), 0600); e != nil {
		return e
	}
	r.State = "completed"
	if req.SandboxID == "" {
		if e = c.release(x, r.SandboxID); e != nil {
			r.Error = e.Error()
		} else {
			r.Released = true
		}
	}
	return nil
}

func (c *Client) checkLimits(x *connection, unit string, status map[string]string) (map[string]string, error) {
	group := "/system.slice/" + unit
	if status["ControlGroup"] != group {
		return nil, errors.New("unexpected systemd cgroup")
	}
	values := map[string]string{}
	for _, name := range []string{"memory.max", "memory.swap.max", "pids.max", "cpu.max"} {
		b, e := x.read("/sys/fs/cgroup"+group+"/"+name, 4096)
		if e != nil {
			return nil, e
		}
		values[name] = strings.TrimSpace(string(b))
	}
	if values["memory.max"] != strconv.FormatInt(c.options.MemoryBytes, 10) || values["memory.swap.max"] != "0" || values["pids.max"] != strconv.Itoa(c.options.Processes) {
		return nil, errors.New("cgroup resource limits were not applied")
	}
	var quota, period int64
	if _, e := fmt.Sscan(values["cpu.max"], &quota, &period); e != nil || quota <= 0 || period <= 0 || quota*100 > period*int64(c.options.CPUPercent) {
		return nil, errors.New("cgroup CPU limit was not applied")
	}
	return values, nil
}

func nativeStatus(x *connection, unit string) (map[string]string, error) {
	raw, e := x.run("systemctl show " + quote(unit) + " --property=LoadState,ActiveState,SubState,InvocationID,ControlGroup,ExecMainCode,ExecMainStatus,Result,MemoryMax,TasksMax,CPUQuotaPerSecUSec,RuntimeMaxUSec")
	if e != nil {
		return nil, e
	}
	status := map[string]string{}
	for _, line := range strings.Split(raw, "\n") {
		k, v, ok := strings.Cut(line, "=")
		if ok {
			status[k] = v
		}
	}
	if status["LoadState"] == "not-found" {
		return nil, errors.New("original unit no longer observable; result unknown")
	}
	return status, nil
}
func fence(x *connection, unit string, status map[string]string) error {
	cgroup := "/system.slice/" + unit
	if status["ControlGroup"] != "" && status["ControlGroup"] != cgroup {
		return errors.New("native cgroup identity missing")
	}
	events := "/sys/fs/cgroup" + cgroup + "/cgroup.events"
	b, e := x.read(events, 4096)
	if os.IsNotExist(e) && status["ExecMainCode"] != "0" && status["SubState"] != "running" {
		return nil
	}
	if e == nil && strings.Contains(string(b), "populated 0\n") {
		return nil
	}
	if _, e = x.run("systemctl kill --kill-who=all --signal=KILL " + quote(unit)); e != nil {
		return e
	}
	for i := 0; i < 100; i++ {
		b, e = x.read(events, 4096)
		if e == nil && strings.Contains(string(b), "populated 0\n") {
			return nil
		}
		if os.IsNotExist(e) {
			s, err := nativeStatus(x, unit)
			if err == nil && s["ExecMainCode"] != "0" && s["SubState"] != "running" {
				return nil
			}
		}
		time.Sleep(10 * time.Millisecond)
	}
	return fmt.Errorf("cannot confirm execution cgroup is empty: %s", unit)
}
