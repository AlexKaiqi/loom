#!/bin/bash
# v2_host_writer.sh — host-side fixed write sequence for V2 (PREREGISTERED DRAFT).
# Runs on the macOS host; writes INTO the shared mount that the VM-side probe
# watches. The probe writes <dir>/begin after its window is entered; this script
# waits for it, executes the preregistered sequence, records ops as JSONL to
# stdout, and writes <dir>/done. Ops file is a runner capture (probes/../../..):
#   ./v2_host_writer.sh <dir> > ops.jsonl 2> writer.err
# Status: DRAFT / UNVERIFIED.
set -euo pipefail

DIR="${1:?usage: v2_host_writer.sh <dir-on-shared-mount>}"
WATCH="$DIR/v2watch"

echo "waiting for begin marker at $DIR/begin" >&2
for _ in $(seq 1 300); do
  [ -f "$DIR/begin" ] && break
  sleep 0.2
done
[ -f "$DIR/begin" ] || { echo "begin marker never appeared" >&2; exit 3; }

ts() { python3 -c 'import time; print(time.time())'; }

mkdir -p "$WATCH"
printf '{"op":"create","path":"v2watch/seq-1.txt","ts":"%s"}\n' "$(ts)"
printf 'substrate-v2-seq-1\n' > "$WATCH/seq-1.txt"

printf '{"op":"write_close","path":"v2watch/seq-1.txt","ts":"%s"}\n' "$(ts)"
printf 'substrate-v2-seq-1-appended\n' >> "$WATCH/seq-1.txt"

mv "$WATCH/seq-1.txt" "$WATCH/seq-1-renamed.txt"
printf '{"op":"rename","from":"v2watch/seq-1.txt","to":"v2watch/seq-1-renamed.txt","ts":"%s"}\n' "$(ts)"

rm "$WATCH/seq-1-renamed.txt"
printf '{"op":"delete","path":"v2watch/seq-1-renamed.txt","ts":"%s"}\n' "$(ts)"

mkdir -p "$WATCH/nested"
printf '{"op":"create_dir","path":"v2watch/nested","ts":"%s"}\n' "$(ts)"
printf 'substrate-v2-nested-inner\n' > "$WATCH/nested/inner.txt"
printf '{"op":"create","path":"v2watch/nested/inner.txt","ts":"%s"}\n' "$(ts)"

printf '{"op":"done","ts":"%s"}\n' "$(ts)" > "$DIR/done"
echo "sequence complete" >&2
