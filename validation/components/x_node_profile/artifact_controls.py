"""Actual finite original mutations for the external XN ordinary-file oracle."""
from pathlib import Path
import argparse, base64, copy, json, os, sys
from artifacts import InvalidEvidence, archive_bytes, save, snapshot
from snapshot_fixtures import EMPTY, original, regular, scope, tar_bytes


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--out', required=True); args = parser.parse_args()
    out = Path(args.out).resolve(); out.mkdir(parents=True, exist_ok=False)
    results = []
    def check(label, fn, rejected=False):
        try:
            value = fn(); passed = not rejected; observation = 'accepted'; error = None
        except InvalidEvidence as exc:
            passed = rejected; observation = 'rejected'; error = str(exc)
        except Exception as exc:
            passed = False; observation = 'observer_crash'; error = repr(exc)
        results.append({'id': label, 'pass': passed, 'expected_rejection': rejected,
                        'observation': observation, 'error': error})
        save(out / (label + '.json'), results[-1])
    expected = scope()
    ref = original(out / 'empty', expected)
    check('empty_actual_original', lambda: snapshot(ref, expected))
    missing = copy.deepcopy(ref); missing['archive_path'] = str(out / 'missing.tar')
    check('missing_top_original_ref', lambda: snapshot(missing, expected), True)
    other = original(out / 'other-session', scope('session-two'))
    check('real_same_namespace_other_session', lambda: snapshot(other, expected), True)
    changed = copy.deepcopy(ref); changed['session_generation'] = 0
    check('stale_original_generation', lambda: snapshot(changed, expected), True)
    data = b'{"type":"fixture-original","id":"one"}\n'
    execution = {'execution_id': 'original-exec', 'object_generation': 1, 'request_digest': 'a' * 64,
                 'container_id': 'b' * 64, 'exec_id': 'c' * 64, 'volume_id': 'fixture-volume',
                 'freeze_generation': 1, 'state': 'PREPARED'}
    checkpoint_expected = scope(execution=execution)
    entries = {**copy.deepcopy(EMPTY), 'session.jsonl': regular(data)}
    contents = {'session.jsonl': data}
    good = original(out / 'checkpoint', checkpoint_expected, entries, contents)
    check('exact_checkpoint_bytes_and_nanoseconds', lambda: snapshot(good, checkpoint_expected))
    hidden = original(out / 'hidden-empty-file', expected, entries, contents)
    check('empty_origin_cannot_hide_file', lambda: snapshot(hidden, expected), True)
    duplicate = original(out / 'duplicate', checkpoint_expected, entries, contents,
                         raw=tar_bytes(entries, contents, duplicate='session.jsonl'))
    check('duplicate_actual_member', lambda: snapshot(duplicate, checkpoint_expected), True)
    no_root_entries = {'session.jsonl': regular(data)}
    no_root = original(out / 'no-root', checkpoint_expected, no_root_entries, contents)
    check('missing_actual_root', lambda: snapshot(no_root, checkpoint_expected), True)
    corrupt = original(out / 'corrupt', checkpoint_expected, entries, contents,
                       raw=tar_bytes(entries, {'session.jsonl': b'X' + data[1:]}))
    check('same_size_changed_original_contents', lambda: snapshot(corrupt, checkpoint_expected), True)
    wrongmtime = original(out / 'wrong-ns', checkpoint_expected, entries, contents,
                          raw=tar_bytes(entries, contents, pax_extra={'session.jsonl': {'mtime': '1700000000.123456788'}}))
    check('one_nanosecond_difference', lambda: snapshot(wrongmtime, checkpoint_expected), True)
    fractional = original(out / 'fractional-ns', checkpoint_expected, entries, contents,
                           raw=tar_bytes(entries, contents, pax_extra={'session.jsonl': {'mtime': '0.0000000001'}}))
    check('sub_nanosecond_rejected', lambda: snapshot(fractional, checkpoint_expected), True)
    xattr = original(out / 'xattr', checkpoint_expected, entries, contents,
                     raw=tar_bytes(entries, contents, pax_extra={'session.jsonl': {'SCHILY.xattr.user.lore': 'lost'}}))
    check('unsupported_actual_xattr', lambda: snapshot(xattr, checkpoint_expected), True)
    special = {**copy.deepcopy(EMPTY), 'pipe': {**EMPTY['.'], 'kind': 'fifo'}}
    fifo = original(out / 'fifo', checkpoint_expected, special)
    check('actual_fifo_rejected', lambda: snapshot(fifo, checkpoint_expected), True)
    linked = {**copy.deepcopy(entries), 'alias': {k: v for k, v in entries['session.jsonl'].items() if k not in ('byte_length', 'sha256')}}
    linked['alias'].update(kind='hardlink', target='session.jsonl')
    linkref = original(out / 'actual-hardlink', checkpoint_expected, linked, contents)
    check('actual_hardlink_metadata', lambda: snapshot(linkref, checkpoint_expected))
    linked['alias']['mtime_ns'] += 1
    wronglink = original(out / 'wrong-link-metadata', checkpoint_expected, linked, contents)
    check('hardlink_metadata_disagrees', lambda: snapshot(wronglink, checkpoint_expected), True)
    ancestor = {**copy.deepcopy(EMPTY), 'link': {**EMPTY['.'], 'kind': 'symlink', 'target_base64': base64.b64encode(b'/tmp').decode()},
                'link/file': regular(data)}
    escape = original(out / 'link-ancestor', checkpoint_expected, ancestor, {'link/file': data})
    check('symlink_archive_ancestor', lambda: snapshot(escape, checkpoint_expected), True)
    wrong = copy.deepcopy(checkpoint_expected); wrong['original_execution']['exec_id'] = 'd' * 64
    check('original_exec_scope_not_from_receipt', lambda: snapshot(good, wrong), True)
    gnu_entries = {'.': copy.deepcopy(EMPTY['.']), './session.jsonl': regular(data)}
    gnu = original(out / 'gnu-prefix', checkpoint_expected, entries, contents,
                   raw=tar_bytes(gnu_entries, {'./session.jsonl': data}))
    check('actual_GNU_prefix_preserved_raw', lambda: snapshot(gnu, checkpoint_expected))
    duplicate_gnu = {**copy.deepcopy(entries), './session.jsonl': regular(data)}
    gnu_dup = original(out / 'gnu-normalized-duplicate', checkpoint_expected, entries, contents,
                       raw=tar_bytes(duplicate_gnu, {**contents, './session.jsonl': data}))
    check('GNU_prefix_normalized_duplicate', lambda: snapshot(gnu_dup, checkpoint_expected), True)
    report = {'status': 'PASS_PREPARATION_ONLY' if len(results) == 19 and all(x['pass'] for x in results) else 'FAIL',
              'checks': results, 'scope': 'External ordinary archive/ref oracle only; no X/S/Engine executed'}
    save(out / 'assessment.json', report)
    print(json.dumps({'status': report['status'], 'checks': len(results)}))
    return 0 if report['status'] == 'PASS_PREPARATION_ONLY' else 1

if __name__ == '__main__': raise SystemExit(main())
