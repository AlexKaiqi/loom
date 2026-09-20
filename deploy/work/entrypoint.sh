#!/bin/bash
set -euo pipefail
: "${LOOM_FACILITY_ID:?installation identity required}"
case "$LOOM_FACILITY_ID" in *[!a-z0-9-]*|'') exit 2;; esac
mount -o remount,rw /sys/fs/cgroup
for controller in cpu memory pids; do
  printf '+%s\n' "$controller" > /sys/fs/cgroup/cgroup.subtree_control
done
mkdir -p "/sys/fs/cgroup/$LOOM_FACILITY_ID" /var/lib/loom-execution
for controller in cpu memory pids; do
  printf '+%s\n' "$controller" > "/sys/fs/cgroup/$LOOM_FACILITY_ID/cgroup.subtree_control"
done
python3 - <<'PY'
import hashlib, json, os
from pathlib import Path
cfg = Path(os.environ['LOOM_EXECUTION_CONFIG'])
cfg.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
launcher = Path('/usr/local/bin/nsjail')
settings = dict(launcher=str(launcher), launcher_sha256=hashlib.sha256(launcher.read_bytes()).hexdigest(),
    state_directory='/var/lib/loom-execution', cgroup_root='/sys/fs/cgroup/' + os.environ['LOOM_FACILITY_ID'],
    uid_base=100000, uid_count=1000000, memory_bytes=536870912, processes=64, cpu_milliseconds=1000)
raw = ''.join(k + ' = ' + json.dumps(v) + '\n' for k,v in settings.items())
# A deployment's launcher may change only with a new installation image. This
# host-only file is copied into setup; existing configurations remain explicit.
cfg.write_text(raw)
cfg.chmod(0o600)
PY
exec sleep infinity
