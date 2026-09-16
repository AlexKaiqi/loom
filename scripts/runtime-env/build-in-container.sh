#!/bin/sh
# 2026-09-14 in-container dependency build for the Linux runtime validation
# environment. Builds: system tools, pinned Node 24.21.0 (linux/arm64), Pi
# worktree at pinned commit, tsx/esbuild in Pi node_modules, tsconfig, the
# support venv, and the markdown-001 parser snapshot. Every pinned input is
# digest-verified before use; all outputs land under the repository mount so
# the host Docker daemon can bind-mount them into X containers.
set -eu
REPO="${REPO:?REPO env var required}"
NODE_TARBALL=/tmp/node-dl/node-v24.21.0-linux-arm64.tar.xz
NODE_SHA256=6ad1325edbdb5649c379b75a237147a666c95d4f9ae8d340fef2d1575d289ad2
PI_COMMIT=71dca871bc80b6bc97be37f0ca3189399d651fff
OPT="$REPO/.runtime-env/opt"
PI="$OPT/lore/research/repos/pi"
export PATH="$OPT/node/bin:$PATH"

echo "== container identity"
python3 --version
uname -m
docker --version 2>/dev/null || echo "docker CLI MISSING"

echo "== system tools"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git xz-utils docker.io >/dev/null
git --version
docker --version

echo "== pinned node tarball"
echo "$NODE_SHA256  $NODE_TARBALL" | sha256sum -c -
mkdir -p "$OPT"
if [ ! -x "$OPT/node/bin/node" ]; then
  tmp=$(mktemp -d)
  tar -xJf "$NODE_TARBALL" -C "$tmp"
  mv "$tmp/node-v24.21.0-linux-arm64" "$OPT/node"
  rm -rf "$tmp"
fi
"$OPT/node/bin/node" --version

echo "== pi worktree at pinned commit"
if [ ! -d "$PI" ]; then
  mkdir -p "$(dirname "$PI")"
  cp -a /tmp/pi-upstream "$PI"
  rm -rf "$PI/.git"
fi
"$OPT/node/bin/node" -e 'console.log("pi files:", require("fs").readdirSync(process.argv[1]).length)' "$PI"

echo "== recorded single-line derived patch (chord context import)"
if ! grep -q "chord/src/context/index.ts" "$PI/packages/agent/src/harness/context.ts"; then
  sed -i "s|} from \"@earendil-works/chord/context\";|} from \"../../../chord/src/context/index.ts\";|" \
    "$PI/packages/agent/src/harness/context.ts"
fi

echo "== tsx/esbuild into pi node_modules (linux/arm64 binaries)"
if [ ! -e "$PI/node_modules/tsx/dist/loader.mjs" ]; then
  "$OPT/node/bin/npm" install --prefix "$PI" --no-audit --no-fund tsx@4.22.1 esbuild@0.28.2
fi
"$OPT/node/bin/node" -e 'console.log("tsx", require(process.argv[1] + "/node_modules/tsx/package.json").version, "esbuild", require(process.argv[1] + "/node_modules/esbuild/package.json").version)' "$PI"
"$PI/node_modules/esbuild/bin/esbuild" --version

echo "== tsconfig"
mkdir -p "$OPT/lore/config"
cp "$REPO/design/g3/x-node-profile/tsconfig.json" "$OPT/lore/config/tsconfig.json"

echo "== support venv (nats-py pinned)"
if [ ! -x "$REPO/research/.venvs/runtime-research/bin/python" ]; then
  python3 -m venv "$REPO/research/.venvs/runtime-research"
  "$REPO/research/.venvs/runtime-research/bin/pip" install --quiet nats-py==2.15.0
fi
"$REPO/research/.venvs/runtime-research/bin/python" -c 'import nats; print("nats-py", nats.__version__ if hasattr(nats,"__version__") else "installed")'

echo "== markdown-001 parser snapshot"
python3 -m venv "$REPO/.runtime-env/markdown-venv"
"$REPO/.runtime-env/markdown-venv/bin/pip" install --quiet markdown-it-py==4.2.0 mdurl==0.1.2
python3 "$REPO/scripts/runtime-env/build-markdown-snapshot.py" \
  --site "$REPO/.runtime-env/markdown-venv/lib/python3.12/site-packages" \
  --out "$REPO/validation/system/dependencies/markdown-001"

echo "== dependency selection manifest + original-host manifests"
python3 "$REPO/scripts/runtime-env/build-dependencies-manifest.py"

echo "== done"
