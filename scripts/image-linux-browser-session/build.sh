#!/bin/sh
# linux-browser session image build flow (A1 semantics, amendment ④a):
# idempotent inputs; failure leaves nothing registered (A1-②); the resulting
# image digest is the identity (A1-④). Probes record resolved versions; the
# seccomp smoke must pass under the candidate seccomp on network=none.
set -eu
cd "$(dirname "$0")"
IMAGE=loom-linux-browser-session:candidate
SECCOMP_BASE=../../lore_execution/seccomp.json
SECCOMP_CANDIDATE=../../lore_execution/seccomp-browser.json

docker build -t "$IMAGE" .

# A1-④ identity: the base digest pin is checked, not assumed.
BASE_ID=$(docker image inspect -f '{{.Id}}' lore-validation:2026-09-14)
[ "$BASE_ID" = "sha256:6e58a110508338395c3c5bbbc325bb4d2492da3d63f8fe73b4839fe237ed5009" ] \
  || { echo "base digest drifted" >&2; exit 1; }

IMAGE_ID=$(docker image inspect -f '{{.Id}}' "$IMAGE")
RUN_ARGS="--rm --user 1000:1000 -e HOME=/tmp --network none"
CHROMIUM_VERSION=$(docker run $RUN_ARGS "$IMAGE" chromium --version)
PLAYWRIGHT_VERSION=$(docker run $RUN_ARGS "$IMAGE" python3 -c "import importlib.metadata as m;print(m.version('playwright'))")
PYTHON_VERSION=$(docker run $RUN_ARGS "$IMAGE" python3 --version)

cp "$SECCOMP_BASE" "$SECCOMP_CANDIDATE"
docker run --rm --user 1000:1000 -e HOME=/tmp --network none \
  --security-opt "seccomp=$(cd ../../lore_execution && pwd)/seccomp-browser.json" \
  "$IMAGE" \
  chromium --headless --no-sandbox --disable-gpu --disable-dev-shm-usage \
  --dump-dom about:blank >/dev/null

printf '{\n  "image_id": "%s",\n  "base": "sha256:6e58a110508338395c3c5bbbc325bb4d2492da3d63f8fe73b4839fe237ed5009",\n  "chromium_version": "%s",\n  "playwright_version": "%s",\n  "python_version": "%s",\n  "seccomp_candidate": "lore_execution/seccomp-browser.json",\n  "playwright_pin": "1.62.0",\n  "deps_volume_note": "node+pi closure mounts at runtime; image carries no /opt"\n}\n' \
  "$IMAGE_ID" "$CHROMIUM_VERSION" "$PLAYWRIGHT_VERSION" "$PYTHON_VERSION"
