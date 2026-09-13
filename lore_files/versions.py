"""Immutable ordinary archives in an isolated, explicitly rooted bare Git store."""
import json
import os
import subprocess
from pathlib import Path
from .archive import unpack
from .errors import FileError, require
from .util import atomic_write, canonical, digest, sync_dir


class Versions:
    def __init__(self, control, limits):
        self.control, self.limits = Path(control), limits
        self.repo = self.control / "versions.git"
        self.artifacts = self.control / "artifacts"
        self.artifacts.mkdir(mode=0o700, exist_ok=True)
        self.pins = self.control / "pins"
        self.pins.mkdir(mode=0o700, exist_ok=True)
        self.released_pins=self.control / "released-pins"
        self.released_pins.mkdir(mode=0o700,exist_ok=True)
        if not self.repo.exists():
            self.git("init", "--bare", str(self.repo), bare=False)
            sync_dir(self.control)

    def git(self, *args, data=None, bare=True, code="PERSISTENCE_FAILED"):
        argv = ["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "gc.auto=0",
                "-c", "core.fsync=all", "-c", "core.fsyncObjectFiles=true"]
        if bare:
            argv.append("--git-dir=" + str(self.repo))
        env = dict(PATH="/usr/bin:/bin", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null",
                   GIT_AUTHOR_NAME="Lore file retention", GIT_AUTHOR_EMAIL="files@localhost",
                   GIT_COMMITTER_NAME="Lore file retention", GIT_COMMITTER_EMAIL="files@localhost")
        try:
            result = subprocess.run(argv + list(args), input=data, capture_output=True, env=env, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise FileError(code, "Git invocation unavailable") from exc
        require(result.returncode == 0, code, "Git: " + result.stderr.decode(errors="replace")[:500])
        return result.stdout

    def seal(self, raw, tree, binding, profile, provenance):
        manifest = dict(schema="lore-f-manifest/v1", resource_id=binding["resource_id"],
                        domain=binding["domain"], profile=profile, tree=tree)
        encoded = canonical(manifest)
        blobs = {}
        for name, data in (("archive.tar", raw), ("manifest.json", encoded), ("provenance.json", canonical(provenance))):
            blobs[name] = self.git("hash-object", "-w", "--stdin", data=data).strip().decode()
        listing = "".join(f"100644 blob {oid}\t{name}\n" for name, oid in sorted(blobs.items())).encode()
        tree_id = self.git("mktree", data=listing).strip().decode()
        commit = self.git("commit-tree", tree_id, data=b"Retain complete ordinary-file version\n").strip().decode()
        git_ref = "refs/lore/versions/" + digest(canonical(dict(blobs=blobs, binding=binding, provenance=provenance)))
        self.git("update-ref", git_ref, commit)
        ref = dict(resource_id=binding["resource_id"], domain=binding["domain"], git_ref=git_ref,
                   archive_sha256=digest(raw), manifest_sha256=digest(encoded), profile=profile)
        directory = self.artifacts / digest(canonical(ref))
        directory.mkdir(mode=0o700, exist_ok=True)
        atomic_write(directory / "archive.tar", raw)
        atomic_write(directory / "manifest.json", encoded)
        sync_dir(directory.parent)
        return dict(version_ref=ref, archive_path=str(directory / "archive.tar"),
                    manifest_path=str(directory / "manifest.json"))

    def load(self, ref):
        require(isinstance(ref, dict) and ref.get("profile") == "host-v1", "VERSION_CORRUPT", "invalid version profile")
        name = ref.get("git_ref", "")
        require(isinstance(name, str) and name.startswith("refs/lore/versions/") and
                all(c.isalnum() or c in "/-_" for c in name), "VERSION_MISSING", "invalid rooted version name")
        self.git("rev-parse", "--verify", name + "^{commit}", code="VERSION_MISSING")
        raw = self.git("cat-file", "blob", name + ":archive.tar", code="VERSION_CORRUPT")
        encoded = self.git("cat-file", "blob", name + ":manifest.json", code="VERSION_CORRUPT")
        require(digest(raw) == ref.get("archive_sha256") and digest(encoded) == ref.get("manifest_sha256"),
                "VERSION_CORRUPT", "actual rooted blob digest mismatch")
        try:
            manifest = json.loads(encoded)
            tree, contents = unpack(raw, self.limits)
            expected = dict(schema="lore-f-manifest/v1", resource_id=ref["resource_id"],
                            domain=ref["domain"], profile=ref["profile"], tree=tree)
            require(canonical(manifest) == canonical(expected), "VERSION_CORRUPT", "manifest and archive scope/content differ")
        except (ValueError, KeyError, FileError) as exc:
            raise FileError("VERSION_CORRUPT", "invalid rooted version: " + str(exc)) from exc
        return raw, tree, contents

    def validate_bundle(self, result):
        raw, _, _ = self.load(result["version_ref"])
        for field, expected in (("archive_path", raw), ("manifest_path", None)):
            path = Path(result[field])
            require(not path.is_symlink() and path.resolve().is_relative_to(self.control),
                    "VERSION_CORRUPT", "artifact path outside control")
            try:
                actual = path.read_bytes()
            except OSError as exc:
                raise FileError("VERSION_CORRUPT", "returned artifact is unavailable") from exc
            if expected is not None:
                require(actual == expected, "VERSION_CORRUPT", "returned archive differs from rooted blob")
            else:
                require(digest(actual) == result["version_ref"]["manifest_sha256"], "VERSION_CORRUPT", "returned manifest differs")

    def retain(self, pin_id, ref):
        self.load(ref)
        path = self.pins / (digest(pin_id.encode()) + ".json")
        old=self.pin_reference(pin_id,missing=True)
        if old is not None:
            require(canonical(old)==canonical(ref),"CONFLICT","pin already binds another original version")
        commit = self.git("rev-parse", ref["git_ref"] + "^{commit}").strip().decode()
        self.git("update-ref", "refs/lore/pins/" + digest(pin_id.encode()), commit)
        atomic_write(path, canonical(ref))

    def pin_reference(self,pin_id,missing=False):
        require(isinstance(pin_id,str) and pin_id,"REFERENCE_INVALID","empty pin identity")
        name=digest(pin_id.encode())+".json"
        for directory in (self.pins,self.released_pins):
            path=directory/name
            if path.exists():
                require(not path.is_symlink(),"REFERENCE_INVALID","pin record alias")
                ref=json.loads(path.read_bytes());self.load(ref);return ref
        require(missing,"REFERENCE_INVALID","original pin association missing")
        return None

    def release(self, pin_id):
        path = self.pins / (digest(pin_id.encode()) + ".json")
        original=self.pin_reference(pin_id)
        atomic_write(self.released_pins/path.name,canonical(original))
        self.git("update-ref", "-d", "refs/lore/pins/" + digest(pin_id.encode()))
        if path.exists():
            path.unlink()
            sync_dir(path.parent)

    def gc(self):
        # Published version roots are conservative retention until R authorizes retirement.
        # Releasing a pin alone never authorizes deleting the underlying version.
        for path in self.pins.glob("*.json"):
            self.load(json.loads(path.read_bytes()))
        self.git("gc", "--prune=now")
