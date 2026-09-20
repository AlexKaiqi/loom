package opensandbox

import (
	"encoding/json"
	"errors"
	"loom/runtime/contracts"
	"slices"
	"strconv"
	"strings"
)

// The fixed code profile checks the actual isolated session. In particular,
// successful allocation/bootstrap is not evidence for Bash or file permissions.
const codeProbe = `import json,os,pathlib,platform,socket,subprocess,sys
readonly=json.loads(sys.argv[1])
assert platform.system()=='Linux'
assert os.getuid()==65534 and os.getgid()==65534
status=dict(line.split(':',1) for line in pathlib.Path('/proc/self/status').read_text().splitlines() if ':' in line)
caps={k:status[k].strip() for k in ('CapEff','CapPrm','CapInh','CapBnd','CapAmb')}
assert all(int(caps[k],16)==0 for k in ('CapEff','CapPrm','CapInh','CapAmb'))
assert status['NoNewPrivs'].strip()=='1'
try:
 socket.socket()
except PermissionError:
 pass
else:
 raise RuntimeError('network syscalls must be denied')
shell=subprocess.run(['/bin/bash','--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0]
assert shell.startswith('GNU bash, version ')
assert os.getcwd()=='/workspace/task' and os.access('.',os.W_OK)
mounts={line.split()[4]:line.split()[5].split(',') for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines()}
for alias in readonly:
 assert 'ro' in mounts['/workspace/task/'+alias]
assert not pathlib.Path('/var/run/docker.sock').exists()
assert not pathlib.Path('/work/.loom').exists()
print(json.dumps(dict(platform='linux',architecture=platform.machine(),shell=shell,
 tools={'python':platform.python_version()},uid=os.getuid(),gid=os.getgid(),
 process_capabilities=caps,no_new_privileges=True,network='denied',workspace=os.getcwd(),readonly_paths=readonly)))
`

func parseReadiness(raw string, readOnly []string) (*contracts.Readiness, error) {
	var report contracts.Readiness
	if err := json.Unmarshal([]byte(raw), &report); err != nil {
		return nil, errors.New("not_ready: code profile probe returned invalid evidence")
	}
	valid := report.Platform == "linux" && report.Architecture != "" &&
		strings.HasPrefix(report.Shell, "GNU bash, version ") && report.Tools["python"] != "" &&
		report.UID == 65534 && report.GID == 65534 && report.NoNewPrivs &&
		report.Network == "denied" && report.Workspace == "/workspace/task" &&
		slices.Equal(report.ReadOnlyPaths, readOnly)
	// The bounding set is a ceiling, not a granted capability. An empty
	// permitted/inheritable/ambient set plus NoNewPrivs prevents acquiring it.
	// Retain the measured ceiling without mistaking it for effective authority.
	_, boundErr := strconv.ParseUint(report.Capabilities["CapBnd"], 16, 64)
	valid = valid && boundErr == nil
	for _, name := range []string{"CapEff", "CapPrm", "CapInh", "CapAmb"} {
		valid = valid && report.Capabilities[name] == "0000000000000000"
	}
	if !valid {
		return nil, errors.New("not_ready: code profile capabilities or permissions do not satisfy requirements")
	}
	return &report, nil
}
