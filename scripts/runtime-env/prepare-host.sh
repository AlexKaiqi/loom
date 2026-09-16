#!/bin/sh
# 2026-09-14 Linux container validation environment build (host side).
# Platform revision recorded in design/g3/provider/amendment-budget-admission-2026-09-14.md
# and docs/validation-status.md: runtime validation runs in a Linux container
# (Docker Desktop arm64); the container sees the repository at its host path so
# that dependency trees materialized inside it remain host-visible to X bind mounts.
set -eu
REPO=/Users/kaiqidong/Desktop/loom
IMAGE=python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

mkdir -p "$REPO/.runtime-env"

docker run --rm -i \
  --volume /var/run/docker.sock:/var/run/docker.sock \
  --volume "$REPO:$REPO" \
  --volume /tmp/node-dl:/tmp/node-dl:ro \
  --volume /tmp/pi-upstream:/tmp/pi-upstream:ro \
  --workdir "$REPO" \
  --env REPO="$REPO" \
  "$IMAGE" \
  sh -s < "$REPO/scripts/runtime-env/build-in-container.sh"
