"""Small existing XN owner controls over preserved, actually generated public Pi bytes.
No Engine, provider, S implementation or new model/tool calls. Synthetic X IDs are fixtures.
"""
from pathlib import Path
import argparse, copy, json, os, shutil
from artifacts import InvalidEvidence, canonical, file_fact, save, sha_bytes, strict_json, require
from snapshot_fixtures import EMPTY, original, regular, scope
from owner_fixture import OwnerFixture, verify_receipt

ROOT = Path(__file__).resolve().parents[3]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); args = ap.parse_args()
    out = Path(args.out).resolve(); out.mkdir(parents=True, exist_ok=False)
    inputs = []
    for name in ('owner_fixture.py', 'owner_controls.py', 'artifacts.py', 'snapshot_fixtures.py', 'fixtures.py'):
        source = Path(__file__).parent / name; target = out / 'source' / name
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, target)
        inputs.append({'source': str(source), 'copy': str(target), 'sha256': sha_bytes(source.read_bytes())})
    actual_sources = [
        ROOT / 'validation/components/s/evidence/public-preparation-001/single-state/metadata.json',
        ROOT / 'design/g4/s-author-design-preparation/sb04-public-api/evidence/public-002/BA01/work/metadata.json']
    source_rows = []
    for path in actual_sources:
        fact, metadata_raw = file_fact(path); metadata = strict_json(metadata_raw)
        raw_fact, raw = file_fact(metadata['path'])
        rows = []
        for line in raw.splitlines()[1:]:
            value = strict_json(line); rows.extend(value if isinstance(value, list) else [value])
        candidates = [r for r in rows if r.get('kind') == 'value' and r.get('namespace') in ('lore.prep.binding', 'lore.s.binding') and r.get('op') == 'set']
        binding = candidates[-1]
        source_rows.append({'metadata': metadata, 'metadata_raw': metadata_raw, 'raw': raw,
                            'metadata_fact': fact, 'jsonl_fact': raw_fact, 'binding_row': binding})
    save(out / 'protocol-and-inputs.json', {'scope': 'Existing owner fixture controls only, no X/S product gate',
        'source_files': inputs, 'actual_Pi_originals': [{k: s[k] for k in ('metadata_fact', 'jsonl_fact')} for s in source_rows],
        'expected_controls': ['two_legal_same_namespace', 'exact_confirmation_retry', 'changed_same_confirmation_id',
                             'valid_successor_receipt', 'same_namespace_other_old', 'same_namespace_other_successor',
                             'hardlink_alias', 'torn_raw_before_open', 'missing_metadata', 'missing_retained', 'sealed_receipt_semantics'],
        'unchanged_on_rejection': 'Original tar/metadata/JSONL and existing charges remain; invalid fixture receipts are not authority facts',
        'no_actual_stop_claim': True})
    owner = OwnerFixture(out / 'owner', out / 'authority', 'sb04-ns')
    def make(label, which, generation=1, torn=False, missing=False):
        s = source_rows[which]; meta = s['metadata']; jp = Path(meta['path']).relative_to(meta['cwd']).as_posix()
        files = {jp: s['raw'] + (b'{"torn":' if torn else b''), 'metadata.json': s['metadata_raw']}
        if missing: del files['metadata.json']
        entries = copy.deepcopy(EMPTY)
        for name, raw in files.items():
            for parent in reversed(Path(name).parents):
                if str(parent) != '.': entries[parent.as_posix()] = copy.deepcopy(EMPTY['.'])
            entries[name] = regular(raw)
        execution = {'execution_id': 'fixture-exec-' + str(which), 'object_generation': 1,
                     'request_digest': sha_bytes(canonical({'source': which})), 'container_id': str(which + 1) * 64,
                     'exec_id': str(which + 3) * 64, 'volume_id': 'fixture-volume-' + str(which),
                     'freeze_generation': generation, 'state': 'PREPARED'}
        expected = scope(meta['id'], execution); expected['namespace'] = 'sb04-ns'
        ref = original(out / label, expected, entries, files)
        full = {'owner': 'X', 'path': ref['archive_path'], 'sha256': ref['archive_sha256'], 'size': ref['archive_bytes'],
                **{k: execution[k] for k in ('execution_id', 'object_generation', 'freeze_generation', 'state')},
                'source_binding': {**{k: v for k, v in execution.items() if k != 'state'},
                                   **{k: expected[k] for k in ('namespace', 'session_id', 'session_generation')}}}
        row = s['binding_row']; descriptor = {'binding': row['value'], 'jsonl_relative_path': jp,
            'metadata_relative_path': 'metadata.json', 'binding_namespace': row['namespace'], 'binding_key': row['key']}
        return expected, full, descriptor
    results = []
    def check(label, fn, reject=False):
        before = {str(p): file_fact(p)[0] for p in (out / 'owner').glob('confirm-*/charge.json')}
        try:
            fn(); observed = 'accepted'; error = None; passed = not reject
        except InvalidEvidence as exc:
            observed = 'rejected'; error = str(exc); passed = reject
        except Exception as exc:
            observed = 'observer_error'; error = repr(exc); passed = False
        if reject:
            after = {str(p): file_fact(p)[0] for p in (out / 'owner').glob('confirm-*/charge.json')}
            passed = passed and before == after
        results.append({'id': label, 'pass': passed, 'expected_rejection': reject, 'actual': observed, 'error': error})
        save(out / (label + '.json'), results[-1])
    a, ar, ad = make('original-a', 0); b, br, bd = make('original-b', 1)
    held = {}
    def legitimate():
        held['a'] = owner.confirm('confirm-a', a, ar, ad)
        held['b'] = owner.confirm('confirm-b', b, br, bd)
        assert a['namespace'] == b['namespace'] and a['session_id'] != b['session_id']
    check('two_legal_same_namespace', legitimate)
    check('exact_confirmation_retry', lambda: require(owner.confirm('confirm-a', a, ar, ad) == held['a'], 'retry original result differs'))
    check('changed_same_confirmation_id', lambda: owner.confirm('confirm-a', b, br, bd), True)
    a2, ar2, ad2 = make('successor-a', 0, 2); held['a2'] = owner.confirm('confirm-a2', a2, ar2, ad2)
    good = owner.receipt('receipt-a', ar, held['a'], ar2, held['a2'])
    check('valid_successor_receipt', lambda: verify_receipt(good, a, ar))
    check('same_namespace_other_old', lambda: verify_receipt(good, b, br), True)
    b2, br2, bd2 = make('successor-b', 1, 2); held['b2'] = owner.confirm('confirm-b2', b2, br2, bd2)
    bad = copy.deepcopy(good); bad['confirmed_successor_full_ref'] = br2; bad['successor_owner_record_ref'] = held['b2']['owner_record_ref']
    bad_body = {k: v for k, v in bad.items() if k != 'actual_owner_receipt_path_sha_bytes'}
    save(out / 'wrong-successor-body.json', bad_body); bad['actual_owner_receipt_path_sha_bytes'] = file_fact(out / 'wrong-successor-body.json')[0]
    check('same_namespace_other_successor', lambda: verify_receipt(bad, a, ar), True)
    retained_path = Path(held['a']['snapshot_ref']['archive_path']); kept = retained_path.with_name('preserved-original.tar')
    retained_path.rename(kept); os.link(ar['path'], retained_path)
    try: check('hardlink_alias', lambda: verify_receipt(good, a, ar), True)
    finally: retained_path.unlink(); kept.rename(retained_path)
    ts, tr, td = make('torn-copy', 0, torn=True)
    check('torn_raw_before_open', lambda: owner.confirm('torn', ts, tr, td), True)
    ms, mr, md = make('missing-metadata-copy', 0, missing=True)
    check('missing_metadata', lambda: owner.confirm('missing', ms, mr, md), True)
    retained_path.rename(kept)
    try: check('missing_retained', lambda: verify_receipt(good, a, ar), True)
    finally: kept.rename(retained_path)
    sealed = owner.receipt('sealed-a', ar, held['a'], sealed=True)
    check('sealed_receipt_semantics', lambda: verify_receipt(sealed, a, ar))
    unchanged = all(file_fact(s[k]['path'])[0] == s[k] for s in source_rows for k in ('metadata_fact', 'jsonl_fact'))
    source_unchanged = all(sha_bytes(Path(r['source']).read_bytes()) == r['sha256'] and sha_bytes(Path(r['copy']).read_bytes()) == r['sha256'] for r in inputs)
    report = {'status': 'PASS_PREPARATION_ONLY' if len(results) == 11 and all(r['pass'] for r in results) and unchanged and source_unchanged else 'FAIL',
              'checks': results, 'actual_originals_unchanged': unchanged, 'source_unchanged': source_unchanged,
              'scope': 'Owner fixture only. Actual X stop/namespace/pin/unlink/credit still required by XN09/11.'}
    save(out / 'assessment.json', report); print(json.dumps({'status': report['status'], 'checks': len(results)}))
    return 0 if report['status'] == 'PASS_PREPARATION_ONLY' else 1

if __name__ == '__main__': raise SystemExit(main())
