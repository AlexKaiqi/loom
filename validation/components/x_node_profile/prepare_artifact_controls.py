"""Capture all local verifier sources before importing/executing finite controls."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, sys, time
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'validation/components/x'))
from source_closure import AUDIT

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--batch', required=True); args = parser.parse_args()
    if not args.batch.replace('-', '').isalnum(): parser.error('fresh batch required')
    out = ROOT / 'validation/components/x_node_profile/evidence' / args.batch
    out.mkdir(parents=True, exist_ok=False); ws = out / 'workspace'; rows = []
    names = ['artifacts.py', 'snapshot_fixtures.py', 'artifact_controls.py', 'prepare_artifact_controls.py']
    paths = [ROOT / 'validation/components/x_node_profile' / n for n in names]
    paths += [ROOT / 'validation/components/x/source_closure.py']
    paths += [ROOT / 'design/g3/x-node-profile' / n for n in ['snapshot-manifest-contract.json', 'driver-preparation-protocol.json', 'interface.json', 'cases-inputs.json']]
    for original in paths:
        dest = ws / original.relative_to(ROOT); dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(original.read_bytes()); rows.append({'original': str(original), 'copy': str(dest), 'sha256': sha(original)})
    (ws / 'sitecustomize.py').write_text(AUDIT)
    known = {x['copy']: x['sha256'] for x in rows}
    known[str(ws / 'sitecustomize.py')] = sha(ws / 'sitecustomize.py')
    argv = [sys.executable, '-B', str(ws / 'validation/components/x_node_profile/artifact_controls.py'), '--out', str(out / 'actual')]
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONPATH': str(ws), 'PYTHONDONTWRITEBYTECODE': '1'}
    started = time.time()
    with (out / 'stdout').open('wb') as stdout, (out / 'stderr').open('wb') as stderr:
        process = subprocess.run(argv, cwd=ws, env=env, stdout=stdout, stderr=stderr, timeout=30)
    events = [json.loads(line) for p in (out / 'imports').glob('*.jsonl') for line in p.read_text().splitlines()]
    executed = [x for x in events if x['kind'] == 'exec']
    source_bound = bool(executed) and all(known.get(x['filename']) == x['sha256'] for x in executed)
    unchanged = all(sha(Path(x[k])) == x['sha256'] for x in rows for k in ('original', 'copy'))
    assessment = json.loads((out / 'actual/assessment.json').read_text())
    result = {'status': 'PASS_PREPARATION_ONLY' if process.returncode == 0 and assessment['status'] == 'PASS_PREPARATION_ONLY' and source_bound and unchanged else 'FAIL',
              'scope': 'Ordinary snapshot oracle preparation only; no X/S product or Docker', 'started': started, 'finished': time.time(),
              'argv': argv, 'environment': env, 'exit_code': process.returncode, 'inputs': rows, 'actual_source_events': events,
              'actual_copy_execution_bound': source_bound, 'source_unchanged': unchanged,
              'assessment': {'path': str(out / 'actual/assessment.json'), 'sha256': sha(out / 'actual/assessment.json')}}
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'exit_code': process.returncode}))
    return 0 if result['status'] == 'PASS_PREPARATION_ONLY' else 1
if __name__ == '__main__': raise SystemExit(main())
