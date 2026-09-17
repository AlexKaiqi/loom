#!/bin/bash
# Real-model research driver: recall-driven retrieval over a small corpus, then saturation.
# Credentials come from ~/.env via the CLI; nothing secret is written here.
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=/opt/homebrew/bin/python3.12
EV=${EV_DIR:-validation/task_runtime/evidence/ark-research-001}
ROOT="$EV/root"
rm -rf "$EV"; mkdir -p "$EV"

$PY -m lore_task create --root "$ROOT" --task-id research-1 --harness lore_harness/research > "$EV/01-create.json"
C="$ROOT/research-1/surface/content"
cat > "$C/a-notes.md" <<'MD'
# Cache notes
The cache stores hot data so expensive recomputation is avoided on repeat reads.
MD
cat > "$C/b-design.md" <<'MD'
# Cache design
Eviction policy: LRU. Each entry carries a TTL of 300 seconds after which it is stale.
MD
cat > "$C/c-misc.md" <<'MD'
# Logging
Structured logs go to stderr; this file is unrelated to caching.
MD
cat > "$C/d-metrics.md" <<'MD'
# Metrics
With TTL 300s the measured p99 read latency is 12 ms and the eviction rate is about 3%.
MD

$PY -m lore_task ingest --root "$ROOT" --task-id research-1 --foreign-id q-001 --kind research.question.set \
  --payload '{"question":"What does this corpus say about cache eviction and TTL? Cite the files you used.","scope":"content corpus only"}' > "$EV/02-ingest.json"

for i in 1 2 3 4; do
  echo "=== research round $i ==="
  $PY -m lore_task run --root "$ROOT" --task-id research-1 --provider ark --max-tokens 10000 --max-steps 4 --timeout 280 > "$EV/03-run-r$i.json" || true
  cat "$EV/03-run-r$i.json"
  DONE=$($PY - "$ROOT/research-1" <<'PY'
import json,sys
done=False
for line in open(sys.argv[1]+"/surface/facts.jsonl"):
    f=json.loads(line)
    if f["kind"]=="task.completed": done=True
print("yes" if done else "no")
PY
)
  [ "$DONE" = "yes" ] && break
done

echo "=== done ==="
tail -5 "$EV/03-run-r$i.json"
