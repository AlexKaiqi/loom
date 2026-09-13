"""Run the original finite S cases in captured source, retaining failures and real peers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def collect(out, target_path, selected):
    from collector import CaseDriver
    from collector_actions import perform_action
    from live_ports import load_target
    from runner import evaluate
    target = load_target(target_path)
    casefile = ROOT / 'design/g3/s/cases.json'; spec = json.loads(casefile.read_bytes())
    cases = [c for c in spec['cases'] if selected is None or c['id'] == selected]
    assert cases and (selected is not None or len(cases) == 27)
    result = dict(case_evidence={}, cases_sha256=sha(casefile), scope='TRUSTED_COLLECTOR_OUTPUT')
    (out/'cases').mkdir()
    failures = []
    for case in cases:
        driver = None
        try:
            driver = CaseDriver(case, target, out/'cases'/case['id'])
            for action in case['actions']:
                perform_action(driver, action['op'], action['args'])
            sources = set(case['evidence_required'])
            for assertion in case['assertions']:
                if 'other' in assertion:
                    sources.add(assertion['other']['source'])
            result['case_evidence'][case['id']] = driver.finish(sorted(sources))
        except Exception as exc:
            import traceback
            failures.append(dict(case_id=case['id'], error=repr(exc), traceback=traceback.format_exc()))
        finally:
            if driver is not None:
                try:
                    driver.cleanup()
                except Exception as exc:
                    failures.append(dict(case_id=case['id'], cleanup_error=repr(exc)))
            # An interrupted batch keeps each completed case and genuine failures.
            diagnostic = out/'cases/partial-index.json'
            with diagnostic.open('w') as stream:
                json.dump(dict(scope='PARTIAL_CASE_INDEX_NOT_GATE', completed=result['case_evidence'], failures=failures), stream, ensure_ascii=False, indent=2)
                stream.flush(); os.fsync(stream.fileno())
    # Oracle paths are relative to CaseDriver.root.parent, i.e. this actual cases directory.
    bundle = out/'cases/bundle.json'; bundle.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    if not failures:
        assessment = evaluate(bundle, selected)
    else:
        assessment = dict(status='FAIL', failures=failures)
    (out/'assessment.json').write_text(json.dumps(assessment, ensure_ascii=False, indent=2)+'\n')
    controllers = []
    for path in sorted((out/'cases').glob('*/peer-state/x-port/controller.json')):
        record = json.loads(path.read_bytes()); pid = record['pid']; end = time.monotonic()+2
        while Path('/proc/'+str(pid)+'/stat').exists():
            stat = Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[0]
            if stat == 'Z':
                break
            if time.monotonic() >= end:
                raise RuntimeError('original shared controller still running after explicit close')
            time.sleep(.01)
        for name, fact in record['actual_modules'].items():
            assert Path(fact['path']).is_relative_to(ROOT) and sha(fact['path']) == fact['sha256'], 'peer imported outside captured source'
        controllers.append(record)
    (out/'controller-observations.json').write_text(json.dumps(controllers, indent=2)+'\n')
    modules = {name:str(Path(module.__file__).resolve()) for name,module in sys.modules.items()
               if getattr(module, '__file__', None) and (name.startswith('lore_') or name.startswith('validation.'))}
    (out/'actual-imports.json').write_text(json.dumps(modules, indent=2)+'\n')
    print(json.dumps(dict(status=assessment['status'], failures=failures, case_count=len(cases))))
    return 0 if assessment['status'] == 'PASS' else 1


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--batch'); parser.add_argument('--case')
    parser.add_argument('--collect', type=Path); parser.add_argument('--target', type=Path)
    options = parser.parse_args()
    if options.collect:
        return collect(options.collect, options.target, options.case)
    assert options.batch and Path(options.batch).name == options.batch
    out = ROOT/'validation/components/s/evidence'/options.batch; out.mkdir(parents=True, exist_ok=False)
    workspace = out/'workspace'; sources = []
    for folder in ['lore_session', 'lore_session/node', 'harnesses/minimal', 'lore_execution', 'lore_files',
                   'validation/components/s', 'validation/components/x', 'validation/components/x_node_profile',
                   'design/g3/s', 'design/g3/x-node-profile', 'design/g3/system']:
        for original in sorted((ROOT/folder).iterdir()):
            if original.is_file():
                copy = workspace/original.relative_to(ROOT); copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, copy)
                sources.append(dict(original=str(original), copy=str(copy), sha256=sha(original)))
    original = ROOT/'research/docker-linux/seccomp.json'; copy = workspace/'research/docker-linux/seccomp.json'
    copy.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(original, copy)
    sources.append(dict(original=str(original), copy=str(copy), sha256=sha(original)))
    (out/'sources.json').write_text(json.dumps(sources, indent=2)+'\n')
    assert options.target and options.target.is_file()
    target_path = out/'target.json'; target = json.loads(options.target.read_bytes())
    for key in ('x_command', 'f_command'):
        target[key] = [part.replace(str(ROOT), str(workspace)) if isinstance(part,str) and str(ROOT) in part and 'validation/components/s/' in part else part for part in target[key]]
    target['artifact_roots'] = [str(out), *target.get('artifact_roots', [])]
    target_path.write_text(json.dumps(target, indent=2)+'\n')
    command = [sys.executable, '-B', str(workspace/'validation/components/s/run_live.py'), '--collect', str(out), '--target', str(target_path)]
    if options.case:
        command += ['--case', options.case]
    started = time.time()
    with (out/'stdout').open('wb') as stdout, (out/'stderr').open('wb') as stderr:
        process = subprocess.run(command, cwd=workspace, env={'PATH':'/usr/bin:/bin', 'LANG':'C.UTF-8', 'PYTHONDONTWRITEBYTECODE':'1'},
                                 stdout=stdout, stderr=stderr, timeout=900)
    unchanged = all(sha(row['original']) == row['sha256'] == sha(row['copy']) for row in sources)
    result = dict(status='PASS' if process.returncode == 0 and unchanged else 'FAIL', scope='S diagnostic subset' if options.case else 'Original S27 finite observations',
                  exit_code=process.returncode, source_unchanged=unchanged, source_count=len(sources), source_manifest_sha256=sha(out/'sources.json'),
                  argv=command, started=started, finished=time.time())
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result)); return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
