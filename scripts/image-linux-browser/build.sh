#!/bin/sh
# linux-browser-v1 build flow (A1 semantics, amendment-linux-browser-2026-09-15):
# idempotent inputs; failure leaves the registry untouched (A1-②); the resulting
# image digest is the identity (A1-④); the manifest records resolved versions.
# The seccomp smoke must pass under the candidate profile on a network=none
# container; otherwise the build fails for iteration BEFORE any registration.
set -eu
cd "$(dirname "$0")"
IMAGE=loom-linux-browser:candidate
SECCOMP_BASE=../../lore_execution/seccomp.json
SECCOMP_CANDIDATE=../../lore_execution/seccomp-browser.json

docker build -t "$IMAGE" .

IMAGE_ID=$(docker image inspect -f '{{.Id}}' "$IMAGE")
RUN_ARGS="--rm --user 1000:1000 -e HOME=/tmp --network none --security-opt seccomp=$(cd ../../lore_execution && pwd)/seccomp.json"
CHROMIUM_VERSION=$(docker run $RUN_ARGS "$IMAGE" chromium --version)
PLAYWRIGHT_VERSION=$(docker run $RUN_ARGS "$IMAGE" python -c "import importlib.metadata as m;print(m.version('playwright'))")
PYTHON_VERSION=$(docker run $RUN_ARGS "$IMAGE" python --version)

cp "$SECCOMP_BASE" "$SECCOMP_CANDIDATE"
docker run --rm --user 1000:1000 -e HOME=/tmp --network none \
  --security-opt "seccomp=$(cd ../../lore_execution && pwd)/seccomp-browser.json" \
  "$IMAGE" \
  chromium --headless --no-sandbox --disable-gpu --dump-dom about:blank >/dev/null

printf '{\n  "image_id": "%s",\n  "chromium_version": "%s",\n  "playwright_version": "%s",\n  "python_version": "%s",\n  "seccomp_candidate": "lore_execution/seccomp-browser.json",\n  "playwright_pin": "1.62.0"\n}\n' \
  "$IMAGE_ID" "$CHROMIUM_VERSION" "$PLAYWRIGHT_VERSION" "$PYTHON_VERSION"
