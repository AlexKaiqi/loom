"""Curate .runtime-env/opt down to the runtime-needed dependency set.

The readonly tree manifest must stay under the product's 2MB bounded-file cap,
so the tree keeps only what the Node/Pi/tsx execution actually loads:
- /opt/node/bin/node (the single pinned interpreter binary used by argv_prefix)
- the Pi worktree sources without node_modules (tsconfig/TSX handle TS sources)
- tsx + esbuild + @esbuild/linux-arm64 plus their runtime deps in Pi's
  node_modules (installed at pinned versions)
Everything else (npm, headers, dev toolchains, native test deps) is removed.
The actual import closure is verified by a smoke test afterwards.
"""
import os
import shutil
import sys
from pathlib import Path

REPO = Path(os.environ["REPO"])
OPT = REPO / ".runtime-env/opt"
NODE = OPT / "node"
PI = OPT / "lore/research/repos/pi"

KEEP_NODE_MODULES = {
    "tsx", "esbuild", "@esbuild", "get-tsconfig", "resolve-pkg-maps",
    "typebox", "@earendil-works", "diff", "ignore", "yaml",
    "@anthropic-ai", "@aws-sdk", "@smithy", "@google", "openai",
    "partial-json", "http-proxy-agent", "https-proxy-agent", "agent-base",
    "debug", "ms", "json-bigint", "proxy-agent-negotiate", "p-retry",
}

# Provider SDKs that packages/ai loads lazily per provider; the product bridges
# its own HTTP provider, so the lazily loaded SDK packages are not needed.
DROP_LAZY_SDKS = {
    "@anthropic-ai", "@aws-sdk", "@smithy", "@google", "openai",
    "http-proxy-agent", "https-proxy-agent", "agent-base", "proxy-agent-negotiate",
    "debug", "ms", "json-bigint", "p-retry", "grok-mermaid", "protobufjs",
}


def main():
    removed = 0
    for child in sorted(NODE.iterdir()):
        if child.name != "bin":
            shutil.rmtree(child) if child.is_dir() else child.unlink()
            removed += 1
    for child in sorted((NODE / "bin").iterdir()):
        if child.name != "node":
            if child.is_symlink():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
            removed += 1
    modules = PI / "node_modules"
    for child in sorted(modules.iterdir()):
        if child.name in DROP_LAZY_SDKS:
            (shutil.rmtree(child) if child.is_dir() and not child.is_symlink()
             else child.unlink())
            removed += 1
            continue
    for child in sorted(modules.iterdir()):
        keep = child.name in KEEP_NODE_MODULES
        if not keep and child.name.startswith("@"):
            keep = any(
                (child / scope).name in KEEP_NODE_MODULES for scope in
                [p.name for p in child.iterdir() if p.is_dir()])
        if not keep:
            if child.is_symlink():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
            removed += 1
    files = sum(len([1 for _ in paths]) for _, dirs, paths in os.walk(OPT))
    links = 0
    for root, dirs, names in os.walk(OPT):
        for name in names:
            if os.path.islink(Path(root) / name):
                links += 1
    print("removed entries:", removed)
    print("remaining files:", files, "links:", links)


if __name__ == "__main__":
    main()
