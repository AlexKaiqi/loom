#!/bin/bash
# Real-model delegation driver: parent delegates, child works, report returns.
# Credentials come from ~/.env via the CLI; nothing secret is written here.
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=/opt/homebrew/bin/python3.12
EV=${EV_DIR:-validation/work_runtime/evidence/ark-delegation-001}
ROOT="$EV/root"

rm -rf "$EV"; mkdir -p "$EV"

$PY -m lore_work create --root "$ROOT" --work-id parent-1 --harness lore_harness/delegation_parent > "$EV/01-create-parent.json"
$PY -m lore_work create --root "$ROOT" --work-id child-1  --harness lore_harness/delegation_child  > "$EV/02-create-child.json"

# consumer declares wants; sender declares grants (both directions)
$PY -m lore_work relate --root "$ROOT" --work-id child-1  --want parent-1:work.delegated --grant parent-1:work.reported > "$EV/03-relate-child.json"
$PY -m lore_work relate --root "$ROOT" --work-id parent-1 --want child-1:work.reported   --grant child-1:work.delegated > "$EV/04-relate-parent.json"

$PY -m lore_work admit --root "$ROOT" --work-id parent-1 --foreign-id obj-001 --kind work.objective.set \
  --payload '{"objective":"Have the child produce the deliverable, then acknowledge its report.","child":"child-1","scope":"Write report.md in your own content area whose exact content is sum=10."}' > "$EV/05-admit-objective.json"

echo "=== parent round 1 (delegate) ==="
$PY -m lore_work run --root "$ROOT" --work-id parent-1 --provider ark --max-tokens 6000 --max-steps 4 --timeout 280 > "$EV/06-parent-r1.json"

DELEGATED=$($PY - "$ROOT/parent-1" <<'PY'
import json,sys
for line in open(sys.argv[1]+"/surface/facts.jsonl"):
    f=json.loads(line)
    if f["kind"]=="work.delegated":
        print(json.dumps(f["payload"])); break
PY
)
echo "delegated payload: $DELEGATED"

$PY -m lore_work relay --from-root "$ROOT" --from-work parent-1 --to-root "$ROOT" --to-work child-1 \
  --foreign-id d-001 --kind work.delegated --payload "$DELEGATED" > "$EV/07-relay-delegation.json"

echo "=== child round 1 (work + report) ==="
$PY -m lore_work run --root "$ROOT" --work-id child-1 --provider ark --max-tokens 6000 --max-steps 6 --timeout 280 > "$EV/08-child-r1.json"

REPORTED=$($PY - "$ROOT/child-1" <<'PY'
import json,sys
for line in open(sys.argv[1]+"/surface/facts.jsonl"):
    f=json.loads(line)
    if f["kind"]=="work.reported":
        print(json.dumps(f["payload"])); break
PY
)
echo "reported payload: $REPORTED"

$PY -m lore_work relay --from-root "$ROOT" --from-work child-1 --to-root "$ROOT" --to-work parent-1 \
  --foreign-id d-002 --kind work.reported --payload "$REPORTED" > "$EV/09-relay-report.json"

echo "=== parent round 2 (acknowledge) ==="
$PY -m lore_work run --root "$ROOT" --work-id parent-1 --provider ark --max-tokens 6000 --max-steps 4 --timeout 280 > "$EV/10-parent-r2.json"

echo "=== done ==="
cat "$EV/06-parent-r1.json" "$EV/08-child-r1.json" "$EV/10-parent-r2.json"
