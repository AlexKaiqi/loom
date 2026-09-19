#!/usr/bin/env python3.12
"""Offline cases for runtime invariants found by independent acceptance A.

Covers:
  I1 layout_version > runtime is refused loudly (landing §10)
  I2 a declared harness role digest must match the real bytes (landing §4.5 R2)
  I3 copying a work directory does NOT inherit cross-work authorization (§9-3 / I8)
No network, no credentials.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lore_work import layout, manifest as manifest_mod, provider
from lore_work import round as round_mod


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="lore-invariants-"))
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    # I1: unknown higher layout_version is refused
    kernel = ROOT / "lore_harness"
    relation = ROOT / "validation" / "work_runtime" / "fixture_relation"
    a = layout.create_work(root, "v-99", kernel)
    round_mod.admit(a, "o1", "work.objective.set", {"objective": "x"})
    work = layout.read_json(a / "work.json")
    work["layout_version"] = 99
    layout.write_json(a / "work.json", work)
    try:
        round_mod.run_round(a, provider.FauxProvider([]), max_steps=1)
        check("layout_version_refused", False, "run_round accepted layout_version=99")
    except ValueError as exc:
        check("layout_version_refused", "unsupported work layout_version 99" in str(exc), str(exc))
    try:
        round_mod.admit(a, "o2", "work.objective.set", {"objective": "y"})
        check("layout_version_refused_on_ingest", False, "ingest accepted layout_version=99")
    except ValueError as exc:
        check("layout_version_refused_on_ingest", "unsupported" in str(exc), str(exc))

    # I2: a declared but wrong role digest is refused
    b = layout.create_work(root, "bad-digest", kernel)
    mpath = b / "harness" / "manifest.json"
    data = json.loads(mpath.read_text())
    data["roles"]["logic"][0]["digest"] = "sha256:" + "0" * 64
    mpath.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    try:
        manifest_mod.load(b)
        check("declared_digest_mismatch_refused", False, "manifest.load accepted a wrong digest")
    except manifest_mod.ManifestError as exc:
        check("declared_digest_mismatch_refused", "digest mismatch" in str(exc), str(exc))

    # I3: a copied work directory carries no authority
    sender = layout.create_work(root, "snd", relation)
    receiver = layout.create_work(root, "rcv", relation)
    round_mod.relate(receiver, want=("snd", ["work.delegated"]))
    round_mod.relate(sender, grant=("rcv", ["work.delegated"]))
    payload = {"child": "rcv", "scope": "x", "input_refs": []}
    ok_here = round_mod.relay(sender, receiver, "d-orig", "work.delegated", payload)
    check("registered_pair_delivers", ok_here.get("delivered") is True, json.dumps(ok_here))

    copy_root = Path(tempfile.mkdtemp(prefix="lore-copy-"))
    shutil.copytree(sender, copy_root / "snd")
    shutil.copytree(receiver, copy_root / "rcv")
    copied = round_mod.relay(copy_root / "snd", copy_root / "rcv", "d-copy", "work.delegated", payload)
    check("copy_has_no_authority", copied.get("delivered") is False and "not registered" in copied.get("reason", ""),
          json.dumps(copied))
    rejected = [json.loads(l) for l in (copy_root / "rcv" / "ledger" / "admission.jsonl").read_text().split("\n") if l.strip()]
    check("copy_refusal_recorded", any(r.get("decision") == "rejected" for r in rejected), json.dumps(rejected))

    # A-N5: a relation-required kind cannot be admitted directly (admission != authorization)
    child = layout.create_work(root, "child-rel", relation)
    try:
        round_mod.admit(child, "direct-1", "work.delegated", {"child": "child-rel", "scope": "x"})
        check("relation_required_kind_refuses_direct_ingest", False, "direct ingest accepted work.delegated")
    except ValueError as exc:
        # Criterion unchanged (refusal of relation-required kinds on direct
        # admission); only the verb in the refusal message was renamed
        # deliver -> relay per glossary v3.2 (tombstone: delivery).
        check("relation_required_kind_refuses_direct_ingest", "requires relation-mediated relay" in str(exc), str(exc))

    # A-N6: an imported work can be adopted explicitly by the new host, then it may deliver
    layout.register_authority(copy_root, "snd", copy_root / "snd")
    layout.register_authority(copy_root, "rcv", copy_root / "rcv")
    adopted = round_mod.relay(copy_root / "snd", copy_root / "rcv", "d-adopted", "work.delegated", payload)
    check("explicit_adoption_restores_authority", adopted.get("delivered") is True, json.dumps(adopted))

    # R8-adjacent: a corrupt LEDGER row must error loudly (same rule as facts)
    from lore_work import ledger as ledger_mod
    bad = layout.create_work(root, "bad-ledger", kernel)
    (bad / "ledger" / "admission.jsonl").write_text('{"foreign_id": "x", broken\n')
    try:
        ledger_mod.read_jsonl(bad / "ledger" / "admission.jsonl")
        check("corrupt_ledger_row_errors", False, "read_jsonl silently truncated the ledger")
    except ValueError as exc:
        check("corrupt_ledger_row_errors", "corrupt ledger row 1" in str(exc), str(exc))
    # and a U+2028 payload inside a ledger row round-trips (same reader rule)
    (bad / "ledger" / "admission.jsonl").write_text(json.dumps({"foreign_id": "a\u2028b"}) + "\n")
    rows = ledger_mod.read_jsonl(bad / "ledger" / "admission.jsonl")
    check("ledger_unicode_row_roundtrip", len(rows) == 1 and rows[0]["foreign_id"] == "a\u2028b", json.dumps(rows))

    ok = all(item[1] for item in checks)
    for name, passed, detail in checks:
        print(("PASS " if passed else "FAIL ") + name + ("" if passed else "  :: " + detail))
    print(json.dumps({"work_root": str(root)}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
