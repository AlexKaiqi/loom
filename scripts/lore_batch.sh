#!/bin/sh
# Run one real M01 batch or the assembly probe inside the frozen validation
# image with the manifest-required mount paths. The deps volume MUST be
# mounted at the physical path recorded in dependencies-manifest.json
# (/var/lib/docker/volumes/lore-runtime-deps/_data); arbitrary mount points
# fail startup-assets physical-identity checks. Repo root is derived from this
# script's location and mounted at the same absolute path so configs resolve.
set -e
MODE="$1"; NAME="$2"
[ -n "$MODE" ] && [ -n "$NAME" ] || { echo "usage: $0 batch|probe NAME" >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEPS=/var/lib/docker/volumes/lore-runtime-deps/_data
STATE=/var/lib/docker/volumes/lore-runtime-state/_data
docker run --rm \
  --volume /var/run/docker.sock:/var/run/docker.sock \
  --volume "$ROOT:$ROOT" \
  --volume lore-runtime-deps:"$DEPS" \
  --volume lore-runtime-state:"$STATE" \
  --volume "$HOME/.loom-credentials:/Users/kaiqidong/.loom-credentials:ro" \
  --workdir "$ROOT" --user 1000:1000 --env HOME=/tmp \
  --env LORE_RUNTIME_OUT="$STATE/m01" \
  lore-validation:2026-09-14 sh -c "
    if [ \"$MODE\" = probe ]; then
      rm -rf \"$STATE/m01/probe-$NAME\"
      research/.venvs/runtime-research/bin/python validation/runtime_assembly_probe.py --batch \"$NAME\"
    elif [ \"$MODE\" = m06 ]; then
      rm -rf \"$STATE/m06/$NAME\"
      LORE_M06_OUT=\"$STATE/m06\" research/.venvs/runtime-research/bin/python validation/m06_browser/m06_run.py --batch \"$NAME\" ${3:+--case \"$3\"} 2>&1 | tail -4
      mkdir -p \"$ROOT/validation/m06_browser/evidence\"
      tar -C \"$STATE/m06\" -cf - \"$NAME\" | tar -C \"$ROOT/validation/m06_browser/evidence\" -xf -
    elif [ \"$MODE\" = m06b ]; then
      rm -rf \"$STATE/m06/$NAME\"
      LORE_M06_OUT=\"$STATE/m06\" research/.venvs/runtime-research/bin/python validation/m06_browser/m06_run_b.py --batch \"$NAME\" ${3:+--case \"$3\"} 2>&1 | tail -4
      mkdir -p \"$ROOT/validation/m06_browser/evidence\"
      tar -C \"$STATE/m06\" -cf - \"$NAME\" | tar -C \"$ROOT/validation/m06_browser/evidence\" -xf -
    else
      rm -rf \"$STATE/m01/m01-real-$NAME\"
      research/.venvs/runtime-research/bin/python validation/system/m01_run.py \"m01-real-$NAME\" --execute-real 2>&1 | tail -2
    fi"
