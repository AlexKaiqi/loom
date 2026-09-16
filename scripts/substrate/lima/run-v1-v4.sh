#!/bin/bash
# run-v1-v4.sh — substrate 批次 V1–V4 编排（PREREGISTERED DRAFT，从未执行）。
# 判据与停止条件：validation/substrate/protocol-substrate-001.json（生效判据）
#                 design/g2/substrate-verification-protocol-2026-09-15.md（叙述）
# 状态：DRAFT / UNVERIFIED。执行前必须：套件冻结 → 模板/探针 sha256 回填预登记 JSON
#       （template_sha256 字段）→ 独立审查通过。S0 身份门禁不过，本脚本不会启动 VM。
#
# 用法：LORE_ROOT=/abs/path/to/loom ./run-v1-v4.sh virtiofs|9p
set -euo pipefail

KIND="${1:?usage: run-v1-v4.sh virtiofs|9p}"
LORE_ROOT="${LORE_ROOT:?set LORE_ROOT to the absolute repo path}"
LIMA_PINNED="2.2.0"
INSTANCE="lore-substrate-${KIND}"
HERE="$(cd "$(dirname "$0")" && pwd)"
PROBES="$HERE/probes"
TMP="$LORE_ROOT/.substrate-tmp"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID="$LORE_ROOT/validation/substrate/evidence/${INSTANCE}-${STAMP}"
mkdir -p "$EVID" "$TMP"

abort() { echo "STOP: $*" | tee -a "$EVID/stops.log"; exit 2; }
blocked() { echo "BLOCKED: $*" | tee -a "$EVID/stops.log"; exit 3; }
run_vm() { limactl shell "$INSTANCE" -- bash -c "PYTHONPATH=$LORE_ROOT $*"; }

# ---- S0 身份门禁 -------------------------------------------------------------
command -v limactl >/dev/null || blocked "limactl not found"
limactl --version | tee "$EVID/limactl-version.txt"
limactl --version | grep -F "version ${LIMA_PINNED}" || abort "limactl is not the pinned ${LIMA_PINNED} (S0)"

{
  echo "# template/probe identity, $(date -u)"
  sha256sum "$HERE/lore-substrate-${KIND}.yaml" "$PROBES"/v*.py "$PROBES"/v2_host_writer.sh
} > "$EVID/identity.txt"
cat "$EVID/identity.txt"
echo "NOTE: template_sha256 must equal the preregistered value once the suite is frozen" \
  | tee -a "$EVID/identity.txt"

# ---- 实例生成与启动（生成命令逐条留证）--------------------------------------
if ! limactl list | awk '{print $1}' | grep -Fxq "$INSTANCE"; then
  INST_YAML="$EVID/instance-${INSTANCE}.yaml"
  # 决定性生成：模板内 {{.Param.LORE_ROOT}} 占位符替换为绝对路径；两份 sha256 均已留证。
  sed "s|{{.Param.LORE_ROOT}}|${LORE_ROOT}|g" "$HERE/lore-substrate-${KIND}.yaml" > "$INST_YAML"
  sha256sum "$INST_YAML" >> "$EVID/identity.txt"
  limactl start --name "$INSTANCE" "$INST_YAML" 2>&1 | tee "$EVID/limactl-start.log"
fi
limactl list | tee -a "$EVID/identity.txt"

run_vm "uname -a && python3 --version && docker version --format '{{json .Server}}'" \
  > "$EVID/guest-facts.txt" 2>&1 || blocked "guest facts unavailable; see guest-facts.txt"

# ---- V1：RENAME_EXCHANGE（×3 + 负对照）--------------------------------------
for i in 1 2 3; do
  run_vm "python3 $PROBES/v1_rename_exchange.py --mode exchange --parent '$TMP/v1-$i'" \
    > "$EVID/v1-exchange-$i.json" 2>&1 \
    || abort "V1 sample $i violated (exit $?); evidence preserved, no rerun (S1/S3)"
done
run_vm "python3 $PROBES/v1_rename_exchange.py --mode exdev --parent '$TMP/v1-neg'" \
  > "$EVID/v1-neg-exdev.json" 2>&1 || abort "V1 exdev negative control violated"
run_vm "python3 $PROBES/v1_rename_exchange.py --mode corrupt --parent '$TMP/v1-neg'" \
  > "$EVID/v1-neg-corrupt.json" 2>&1 || abort "V1 corrupt negative control violated"

# ---- V2：inotify 送达（×3，双层观测 + 负对照）--------------------------------
for i in 1 2 3; do
  D="$TMP/v2-$i"; mkdir -p "$D"
  # Ops JSONL goes ON the shared mount (unwatched path) so the VM-side probe can read it.
  bash "$PROBES/v2_host_writer.sh" "$D" > "$D/ops.jsonl" 2> "$EVID/v2-writer-$i.err" &
  WRITER=$!
  run_vm "python3 $PROBES/v2_inotify.py --mode observe --root '$D' --writer-events '$D/ops.jsonl' --timeout 60" \
    > "$EVID/v2-observe-$i.json" 2>&1 || { kill "$WRITER" 2>/dev/null || true; abort "V2 sample $i violated"; }
  cp "$D/ops.jsonl" "$EVID/v2-writer-ops-$i.jsonl"
  wait "$WRITER" || abort "V2 host writer failed for sample $i"
done
run_vm "python3 $PROBES/v2_inotify.py --mode silent --root '$TMP/v2-silent'" \
  > "$EVID/v2-neg-silent.json" 2>&1 || abort "V2 silent negative control violated"
# shadow 对照需要 writer 先跑完：先写序列，再开 post-hoc 观察者。
D="$TMP/v2-shadow"; mkdir -p "$D"
bash "$PROBES/v2_host_writer.sh" "$D" > "$D/ops.jsonl" 2> "$EVID/v2-writer-shadow.err"
cp "$D/ops.jsonl" "$EVID/v2-writer-ops-shadow.jsonl"
run_vm "python3 $PROBES/v2_inotify.py --mode shadow --root '$D' --writer-events '$D/ops.jsonl'" \
  > "$EVID/v2-neg-shadow.json" 2>&1 || abort "V2 shadow negative control violated"

# ---- V4（样本 1）：Engine/digest/seccomp/volume 钉定 -------------------------
run_vm "python3 $PROBES/v4_engine_pin.py" > "$EVID/v4-sample-1.json" 2>&1 \
  || abort "V4 sample 1 violated"
run_vm "python3 $PROBES/v4_engine_pin.py --expect-reject-engine 28.0.1" \
  > "$EVID/v4-neg-reject.json" 2>&1 || abort "V4 negative control violated"

# ---- V3：dev/ino 跨 VM 生命周期（重启 ×2 判据 + 重建 1 次观测）----------------
run_vm "python3 $PROBES/v3_identity_stability.py --mode record --root '$TMP/v3-shared' --manifest '$EVID/v3-shared-m0.json' --seed" \
  > "$EVID/v3-record-shared.json" 2>&1 || abort "V3 record failed"
run_vm "python3 $PROBES/v3_identity_stability.py --mode record --root /var/tmp/v3-local --manifest '$EVID/v3-local-m0.json' --seed" \
  > "$EVID/v3-record-local.json" 2>&1 || abort "V3 record (local control) failed"
for r in 1 2; do
  limactl stop "$INSTANCE" >> "$EVID/limactl-v3.log" 2>&1
  limactl start "$INSTANCE" >> "$EVID/limactl-v3.log" 2>&1
  run_vm "python3 $PROBES/v3_identity_stability.py --mode compare --root '$TMP/v3-shared' --manifest '$EVID/v3-shared-m0.json'" \
    > "$EVID/v3-restart-$r.json" 2>&1 || abort "V3 restart $r drifted (criterion FAIL)"
  run_vm "python3 $PROBES/v3_identity_stability.py --mode compare --root /var/tmp/v3-local --manifest '$EVID/v3-local-m0.json'" \
    > "$EVID/v3-restart-$r-local.json" 2>&1 || abort "V3 restart $r local control drifted"
done
# 重建观测（观测项，不参与判据；其 outcome 只决定 manifest 再生成策略）。
limactl delete -f "$INSTANCE" >> "$EVID/limactl-v3.log" 2>&1
if ! limactl list | awk '{print $1}' | grep -Fxq "$INSTANCE"; then
  INST_YAML="$(ls "$LORE_ROOT"/validation/substrate/evidence/${INSTANCE}-*/instance-${INSTANCE}.yaml 2>/dev/null | head -1)"
  [ -n "$INST_YAML" ] || abort "instance yaml for recreate not found"
  limactl start --name "$INSTANCE" "$INST_YAML" >> "$EVID/limactl-v3.log" 2>&1
fi
run_vm "python3 $PROBES/v3_identity_stability.py --mode compare --root '$TMP/v3-shared' --manifest '$EVID/v3-shared-m0.json'" \
  > "$EVID/v3-recreate-OBSERVATION.json" 2>&1 \
  || echo "V3 recreate observation: drift/absence recorded (observation only, not a criterion)" \
      | tee -a "$EVID/stops.log"

# ---- V4（样本 2）：独立全新实例 ----------------------------------------------
run_vm "python3 $PROBES/v4_engine_pin.py" > "$EVID/v4-sample-2.json" 2>&1 \
  || abort "V4 sample 2 violated"

echo "ALL BATCHES COMPLETED — evidence in $EVID" | tee -a "$EVID/stops.log"
echo "Batch verdicts remain UNVERIFIED until an independent accepter re-runs or re-inspects the raw evidence."
