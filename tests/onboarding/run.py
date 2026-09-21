"""Independent installed-user acceptance, with real Pi and real OpenSandbox.

Run only against an operator-provided service. Outputs never include credentials,
private host TOML or authority databases; those remain under --private-dir.
"""
import argparse
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
import hashlib
import json
import os
import pty
import select
import time
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/go_acceptance"))
from support import Handler, ProviderFixture, query, assert_no_secrets
from remote import APIObserver, serving

ARCHIVE_CANARY = "OLD_ARCHIVE_BODY_MUST_NOT_BE_PROJECTED_34c270f"
PLAN_CANARY = "CURRENT_PLAN_VISIBLE_69b1b07"
MODEL_KEY = "onboarding-model-secret-361562b94"
TASK = "读取 default Target 中 app/numbers.txt，保存总和；在 Work 中维护计划和报告，通过主模板选择事实。"


class UserProvider(Handler):
    def openai(self, mode, number):
        effects = query(self.server.work, "SELECT * FROM effects ORDER BY rowid")
        active = [e for e in effects if e["kind"] == "model" and e["status"] == "intent"]
        if len(active) != 1:
            self.server.errors.append("provider request without exactly one saved model intent")
        else:
            ref = json.loads(active[0]["request"])["request"]
            raw = (self.server.work / ref["path"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
                self.server.errors.append("provider request artifact digest differs")
        if self.server.mode == "truncated":
            self.chunk({"role": "assistant", "content": "unconfirmed"})
            return
        self.chunk({"role": "assistant"})
        calls = []
        if self.server.mode == "tools" and number <= 4:
            self.chunk({"content": "NATIVE_ORIGINAL_TURN_" + str(number) + "_" + "e" * 12000})
        if self.server.mode == "tools" and number == 1:
            calls = [
                ("onboarding_task", {"environment":"sandbox", "target":"default", "script":
                    "python - <<'SCRIPT'\nimport os,pathlib\nassert os.getuid()==65534\n"
                    "assert 'LOOM_TEST_MODEL_KEY' not in os.environ\n"
                    "assert 'LOOM_TEST_SANDBOX_KEY' not in os.environ\n"
                    "assert not pathlib.Path('/var/run/docker.sock').exists()\n"
                    "assert not pathlib.Path('/work/surface').exists()\n"
                    "values=[int(v) for v in pathlib.Path('app/numbers.txt').read_text().split()]\n"
                    "assert values==[17,23]\npathlib.Path('app/sum.txt').write_text(str(sum(values))+'\\n')\nprint(sum(values))\nSCRIPT"}),
                ("onboarding_work", {"environment":"work", "script":
                    "python3 - <<'SCRIPT'\nimport os,pathlib\nassert os.getuid()>=100000\n"
                    "assert not pathlib.Path('/var/run/docker.sock').exists()\n"
                    "assert not pathlib.Path('/work/.loom').exists()\n"
                    "assert pathlib.Path('/harness/worker.py').exists()\n"
                    "assert pathlib.Path('/work/work.toml').is_file()\n"
                    "pathlib.Path('surface/report.md').write_text('# Result\\n17 + 23 = 40\\n')\n"
                    "pathlib.Path('surface/plan.md').write_text('# Plan\\n- [x] Compute 17 + 23\\n')\n"
                    "print('maintained Surface updated')\nSCRIPT"})]
        elif self.server.mode == "tools" and number == 2:
            calls = [("onboarding_evidence", {"environment":"work", "script":"printf 'retained tool evidence\\n'"})]
        elif self.server.mode == "tools" and number in (3,4):
            selected = 'onboarding_task' if number == 3 else 'onboarding_work'
            key = 'body_refs' if number == 3 else 'after'
            script = ("python3 - <<'SCRIPT'\nimport json,os,pathlib,sqlite3\n"
                "db=sqlite3.connect('file:'+os.environ['FACTS_DB']+'?mode=ro',uri=True)\n"
                "ids=[]\nfor fid,path in db.execute(\"SELECT fact_id,record_path FROM facts WHERE kind='tool.result' ORDER BY ordinal\"):\n"
                " value=json.loads(pathlib.Path(path).read_text())\n"
                f" if value['message']['toolCallId']=={selected!r}: ids.append(fid)\n"
                "assert len(ids)==1\npath=pathlib.Path('surface/main.md')\ntext=path.read_text()\n"
                + ("value=json.dumps(ids)\n" if number == 3 else "value=json.dumps(ids[0])\n")
                + f"text=text.replace('```facts\\n','```facts\\n{key}='+value+'\\n')\n"
                "path.write_text(text)\nprint('explicit template choice',ids[0])\nSCRIPT")
            calls = [("onboarding_select_"+str(number), {"environment":"work","script":script})]
        if calls:
            for index,(identity,args) in enumerate(calls):
                self.chunk({"tool_calls":[{"index":index,"id":identity,"type":"function",
                    "function":{"name":"bash","arguments":json.dumps({**args,"timeout":30})}}]})
            self.chunk(finish="tool_calls",usage={"prompt_tokens":20,"completion_tokens":10,"total_tokens":30})
        else:
            self.chunk({"content":"已完成：17 + 23 = 40。Surface 与事实选择已保存。"})
            self.chunk(finish="stop",usage={"prompt_tokens":20,"completion_tokens":10,"total_tokens":30})
        self.event("[DONE]")


def peer_server(upstream, work):
    provider=ProviderFixture("tools");provider.RequestHandlerClass=UserProvider
    provider.work,provider.errors=Path(work),[]
    api=ThreadingHTTPServer(("127.0.0.1",0),APIObserver)
    api.upstream,api.work,api.errors,api.creates,api.requests=upstream.rstrip('/'),Path(work),[],0,[]
    with serving(provider),serving(api):
        print(json.dumps({'model':provider.base_url,'sandbox_port':api.server_port}),flush=True)
        for line in sys.stdin:
            request=json.loads(line)
            if request.get('stop'):break
            if 'mode' in request:provider.mode=request['mode']
            if 'work' in request:provider.work=api.work=Path(request['work'])
            print(json.dumps({'provider_calls':provider.calls,'provider_errors':provider.errors,
                'api_requests':api.requests,'api_errors':api.errors,'sandbox_creates':api.creates}),flush=True)


class FacilityPeers:
    def __init__(self,user):
        from urllib.parse import urlsplit,urlunsplit
        copied=user.private/'fixture-source'
        for component in ('tests/model','tests/go_acceptance','tests/onboarding'):
            shutil.copytree(ROOT/component,copied/component,ignore=shutil.ignore_patterns('__pycache__'))
        endpoint=urlsplit(user.args.sandbox_endpoint)
        if endpoint.hostname in ('127.0.0.1','localhost'):
            endpoint=endpoint._replace(netloc='host.docker.internal'+(':'+str(endpoint.port) if endpoint.port else ''))
        info=json.loads((user.prefix/'current/installation.json').read_text())
        self.process=subprocess.Popen([shutil.which('docker'),'exec','-i',info['container'],'python3',
            str(copied/'tests/onboarding/run.py'),'--peer-server',urlunsplit(endpoint),str(user.work)],
            env=user.env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        first=self.process.stdout.readline()
        if not first:raise RuntimeError('facility peers did not start')
        endpoints=json.loads(first);self.base_url=endpoints['model'];self.server_port=endpoints['sandbox_port']
        self.saved={};self.refresh()
    def refresh(self,**change):
        self.process.stdin.write(json.dumps(change)+'\n');self.process.stdin.flush()
        self.saved=json.loads(self.process.stdout.readline());return self.saved
    def close(self):
        self.refresh();self.process.stdin.write('{"stop":true}\n');self.process.stdin.flush()
        try:self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
        for pipe in (self.process.stdin,self.process.stdout,self.process.stderr):pipe.close()



class InstalledUser:
    def __init__(self, args):
        self.output = Path(args.output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.private = Path(args.private_dir).resolve()
        self.private.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.home = self.private / "home"
        self.home.mkdir()
        self.prefix = self.private / "installed prefix"
        self.cwd = self.private / "unrelated cwd"
        self.cwd.mkdir()
        self.binary = self.prefix / "bin/loom"
        self.commands = []
        self.checks = []
        self.env = dict(os.environ)
        self.env.setdefault("DOCKER_CONFIG", str(Path.home() / ".docker"))
        self.env["HOME"] = str(self.home)
        self.env["PATH"] = os.pathsep.join(p for p in self.env["PATH"].split(os.pathsep) if str(ROOT) not in p and "loom-onboarding-private" not in p)
        self.env.pop("PYTHONPATH", None)
        self.env.pop("LOOM_INSTALL_ROOT", None)
        self.env["LOOM_TEST_MODEL_KEY"] = MODEL_KEY
        self.env["LOOM_TEST_SANDBOX_KEY"] = Path(args.sandbox_key_file).read_text().strip()
        self.config = self.prefix / "host-state/.config/loom/config.toml"
        self.authority = self.prefix / "host-state/.local/state/loom/authority.sqlite"
        self.work = self.output / "work"
        self.userspace = self.private / "task files"
        self.userspace.mkdir()
        (self.userspace / "numbers.txt").write_text("17\n23\n")
        self.args = args

    def command(self, *args, ok=True, env=None, cwd=None, timeout=180):
        cmd = [str(self.binary), *map(str, args)]
        result = subprocess.run(cmd, cwd=cwd or self.cwd, env=env or self.env, text=True, capture_output=True, timeout=timeout)
        self.commands.append({"argv": cmd, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        (self.output / "commands.json").write_text(json.dumps(self.commands, ensure_ascii=False, indent=2))
        assert (result.returncode == 0) == ok, result.stderr + result.stdout
        return result

    def install(self):
        before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for base in ("runtime", "services/model", "harnesses", "deploy", "scripts", "tests/onboarding", "tests/model", "tests/go_acceptance", "tests/harness", "tests/install", "templates")
                  for p in (ROOT / base).rglob("*") if p.is_file() and not any(part in {"node_modules", "bin", "__pycache__"} for part in p.parts)}
        for name in ("docs/loom-design-book.html", "AGENTS.md", "install.sh"):
            before[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        (self.output / "source-hashes.json").write_text(json.dumps(before, sort_keys=True, indent=2))
        result = subprocess.run([str(ROOT / "install.sh"), "--deployment", "docker", "--prefix", str(self.prefix), "--workspace-root", str(self.private), "--workspace-root", str(self.output)], cwd=self.cwd, env=self.env, capture_output=True, text=True, timeout=1800)
        (self.output / "install.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stderr
        self.command("--help")
        self.checks.append("fresh installation in prefix with spaces from unrelated cwd; no manual Python env or worker path")

    def setup(self, provider, api, *, ok=True):
        return self.command("setup", "--sandbox-provider", "opensandbox/v1", "--provider", "groq", "--model", "llama-3.1-8b-instant",
                            "--model-endpoint", provider.base_url, "--sandbox-endpoint", f"http://127.0.0.1:{api.server_port}",
                            "--model-key-env", "LOOM_TEST_MODEL_KEY", "--sandbox-key-env", "LOOM_TEST_SANDBOX_KEY", ok=ok)

    def interactive_setup(self, provider, api):
        target = self.private / "interactive/config.toml"
        master, slave = pty.openpty()
        process = subprocess.Popen([str(self.binary), "--config", str(target), "setup", "--model-endpoint", provider.base_url],
                                   stdin=slave, stdout=slave, stderr=slave, cwd=self.cwd, env=self.env, close_fds=True)
        os.close(slave)
        transcript = bytearray()
        def until(marker):
            deadline = time.monotonic() + 30
            while marker not in transcript:
                assert time.monotonic() < deadline, "interactive setup prompt timeout"
                ready, _, _ = select.select([master], [], [], 0.2)
                if ready:
                    try:
                        raw = os.read(master, 65536)
                    except OSError:
                        raw = b""
                    assert raw, "interactive setup exited before prompt"
                    transcript.extend(raw)
        try:
            for prompt, answer in (
                (b"Provider (--provider): ", "groq"),
                (b"Model (--model): ", "llama-3.1-8b-instant"),
                (b"Sandbox provider (--sandbox-provider): ", "opensandbox/v1"),
                (b"Sandbox endpoint (--sandbox-endpoint): ", f"http://127.0.0.1:{api.server_port}"),
                (b"model API key (hidden): ", MODEL_KEY),
                (b"sandbox API key (hidden): ", self.env["LOOM_TEST_SANDBOX_KEY"]),
            ):
                until(prompt)
                time.sleep(0.05)
                os.write(master, answer.encode() + b"\n")
            while process.poll() is None:
                ready, _, _ = select.select([master], [], [], 0.2)
                if ready:
                    try:
                        transcript.extend(os.read(master, 65536))
                    except OSError:
                        break
            assert process.wait(timeout=30) == 0
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            assert MODEL_KEY.encode() not in transcript and self.env["LOOM_TEST_SANDBOX_KEY"].encode() not in transcript
            (self.output / "interactive-setup.txt").write_bytes(transcript)
        config = tomllib.loads(target.read_text())
        for name, key in (("model", MODEL_KEY), ("sandbox", self.env["LOOM_TEST_SANDBOX_KEY"])):
            secret = target.parent / "secrets" / (name + ".key")
            assert secret.read_text() == key and secret.stat().st_mode & 0o777 == 0o600
        assert "api_key_file" in config["models"]["primary"]
        self.checks.append("real terminal setup offers Pi catalog, hides key input and persists only private 0600 credential files")

    def run(self):
        self.install()
        peers=FacilityPeers(self)
        try:
            self.interactive_setup(peers,peers)
            self.setup(peers,peers)
            config_before=self.config.read_bytes()
            config=tomllib.loads(config_before.decode())
            assert config['models']['primary']['worker']==['loom-model']
            assert not any(key in config_before for key in (MODEL_KEY.encode(),self.env['LOOM_TEST_SANDBOX_KEY'].encode()))
            self.setup(peers,peers,ok=False)
            assert self.config.read_bytes()==config_before
            self.checks.append('setup and interactive secrets stay private; existing configuration is preserved')
            self.command('new',self.work,'--userspace',self.userspace)
            assert (self.work/'surface/main.md').is_file()
            assert not (self.work/'surface/plan.md').exists()
            (self.work/'surface/plan.md').write_text('# Plan\n'+PLAN_CANARY+'\n')
            (self.work/'surface/report.md').write_text('# Result pending\n')
            (self.work/'surface/reference.md').write_text(ARCHIVE_CANARY+'\n')
            main=self.work/'surface/main.md'
            main.write_text('# Maintained understanding\n```include\npath="surface/plan.md"\n```\n'
                '```include\npath="surface/report.md"\n```\n```facts\n```\n')
            self.command('status',cwd=self.work)
            denied=dict(self.env);denied.pop('LOOM_TEST_MODEL_KEY')
            self.command('ask',self.work,TASK,'--request-id','natural-1',ok=False,env=denied)
            assert len(query(self.work,'SELECT * FROM pending'))==1
            assert not query(self.work,'SELECT * FROM effects')
            observed=peers.refresh();assert not observed['provider_calls'] and not observed['api_requests']
            self.checks.append('missing credential preserves the admitted input with zero dispatch')
            queued=self.command('ask',self.work,TASK,'--request-id','natural-1')
            assert 'recover' in queued.stdout.lower()
            assert peers.refresh()==observed, 'retrying admission bypassed recovery or dispatched a duplicate request'
            recovered=json.loads(self.command('recover',self.work).stdout)
            assert query(self.work,'SELECT state FROM rounds')==[{'state':'ready'}]
            resumed=json.loads(self.command('resume',self.work).stdout)
            assert resumed['state']=='handed_off'
            assert len(query(self.work,"SELECT * FROM events WHERE kind='work.message'"))==1
            self.checks.append('pre-dispatch credential failure resumes the saved projection after explicit recovery, without duplicate input')
            observed=peers.refresh();calls=observed['provider_calls']
            assert len(calls)==5 and observed['sandbox_creates']==1
            assert not observed['provider_errors'] and not observed['api_errors'],observed
            assert calls[0]['body']['max_completion_tokens']==4096
            first=json.dumps(calls[0]['body']['messages'],ensure_ascii=False)
            assert PLAN_CANARY in first and ARCHIVE_CANARY not in first
            assert 'Original tool body:' in json.dumps(calls[3]['body']['messages'])
            assert 'NATIVE_ORIGINAL_TURN_1_' not in json.dumps(calls[4]['body']['messages'])
            assert not (self.userspace/'sum.txt').exists()
            restored=self.output/'saved-task-result'
            self.command('restore-resource',self.work,'app',restored,'--target','default')
            assert (restored/'sum.txt').read_text()=='40\n'
            assert (self.work/'surface/report.md').read_text()=='# Result\n17 + 23 = 40\n'
            assert (self.work/'surface/reference.md').read_text()==ARCHIVE_CANARY+'\n'
            assert not (self.work/'surface/archive').exists()
            native=query(self.work,"SELECT * FROM events WHERE source='model-adapter' AND kind='model.message'")
            original=[row for row in native if 'NATIVE_ORIGINAL_TURN_1_' in row['payload']]
            assert len(original)==1
            full=json.loads(original[0]['payload'])
            assert 'e'*12000 in json.dumps(full)
            effects=query(self.work,'SELECT * FROM effects ORDER BY rowid')
            assert sum(e['kind']=='model' for e in effects)==5
            assert sum(e['kind']=='tool.exec' for e in effects)==5
            assert all(e['status']=='completed' for e in effects)
            for effect in effects:
                if effect['kind']=='tool.exec' and json.loads(effect['request'])['environment']=='sandbox':
                    receipt=json.loads(effect['result'])['receipt']
                    assert receipt['exit_code']==0 and receipt['released']
                    assert not subprocess.check_output(['docker','ps','-aq','--filter','label=loom.operation='+effect['id']],text=True,env=self.env).strip()
            assert not query(self.work,'SELECT * FROM pending')
            self.checks.append('real Work Bash plus remote Sandbox; independent resource result=40; shared source unchanged; native results and release verified')
            self.checks.append('model tool calls explicitly fold and archive through main.md; complete native facts survive without a Surface history copy')
            before=query(self.work,'SELECT * FROM events')
            self.command('ask',self.work,TASK,'--request-id','natural-1')
            self.command('ask',self.work,'conflicting text','--request-id','natural-1',ok=False)
            assert query(self.work,'SELECT * FROM events')==before
            assert len(peers.refresh()['provider_calls'])==5
            self.checks.append('same identity is idempotent; changed text conflicts without additional model requests')
            peers.refresh(mode='text')
            self.command('ask','检查保存的计划','--request-id','natural-2',cwd=self.work)
            latest=json.dumps(peers.refresh()['provider_calls'][-1]['body']['messages'],ensure_ascii=False)
            assert 'Compute 17 + 23' in latest and 'NATIVE_ORIGINAL_TURN_1_' not in latest
            assert ARCHIVE_CANARY not in latest
            # A declared small model window exercises pre-dispatch refusal. The
            # admission itself remains the same natural-language CLI path.
            limited=self.private/'limited-work.toml'
            defaults=self.config.parent/'work-default.toml'
            import re
            text=defaults.read_text()
            text=re.sub(r'contextWindow = \d+', 'contextWindow = 4096',text)
            text=re.sub(r'maxTokens = \d+', 'maxTokens = 128',text)
            limited.write_text(text)
            local_work=self.output/'local-rejection-work';local_tasks=self.private/'local-tasks';local_tasks.mkdir()
            self.command('new',local_work,'--userspace',local_tasks,'--definition',limited)
            before_http=peers.refresh()
            rejected=self.command('ask',local_work,'Required input '+('z'*50000),'--request-id','local-1',ok=False)
            assert 'context capacity' in rejected.stderr
            assert not query(local_work,'SELECT * FROM effects')
            assert query(local_work,'SELECT state FROM rounds')==[{'state':'blocked'}]
            assert len(query(local_work,'SELECT * FROM pending'))==1
            assert peers.refresh()==before_http
            self.checks.append('oversized required input blocks before dispatch, without hidden truncation or dropping responsibility')
            unknown_work=self.output/'unknown-work';unknown_tasks=self.private/'unknown-tasks';unknown_tasks.mkdir()
            self.command('new',unknown_work,'--userspace',unknown_tasks)
            peers.refresh(work=str(unknown_work),mode='truncated')
            self.command('ask',unknown_work,'retain interrupted input','--request-id','unknown-1',ok=False)
            count=len(peers.refresh()['provider_calls'])
            saved=query(unknown_work,'SELECT * FROM effects');assert len(saved)==1
            round=query(unknown_work,'SELECT * FROM rounds')[0];assert round['state']=='blocked'
            cp=json.loads(round['checkpoint']);assert cp['phase']=='model_ready' and 'native_turn' not in cp
            native_error=json.loads(saved[0]['result']);assert native_error['stopReason']=='error'
            raw=(unknown_work/native_error['artifact']['path']).read_bytes()
            assert hashlib.sha256(raw).hexdigest()==native_error['artifact']['sha256']
            assert json.loads(raw)['message']['stopReason']=='error'
            queued=self.command('ask',unknown_work,'retain interrupted input','--request-id','unknown-1')
            assert 'queued' in queued.stdout.lower()
            self.command('run',unknown_work,ok=False);self.command('resume',unknown_work,ok=False)
            assert len(peers.refresh()['provider_calls'])==count and query(unknown_work,'SELECT * FROM pending')
            self.checks.append('truncated native response is retained; no confirmed continuation or automatic replay is invented')
            captured=subprocess.check_output(['git','--git-dir',str(self.work/'.loom/versions.git'),'show','HEAD:surface/report.md'])
            assert captured==(self.work/'surface/report.md').read_bytes()
            self.command('export',self.work,self.output/'work.tar.gz')
            copied=self.output/'copied-work';shutil.copytree(self.work,copied)
            self.command('status',copied,ok=False)
            self.checks.append('versioned Surface matches actual bytes; copied Work inherits no physical authority')
        finally:
            observations={**peers.refresh(),'checks':self.checks,
                'rounds':query(self.work,'SELECT * FROM rounds') if self.work.exists() else [],
                'effects':query(self.work,'SELECT * FROM effects ORDER BY rowid') if self.work.exists() else []}
            peers.close()
            (self.output/'observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2))
            scanned=assert_no_secrets(self.output,[MODEL_KEY.encode(),self.env['LOOM_TEST_SANDBOX_KEY'].encode()])
            (self.output/'secret-scan.json').write_text(json.dumps({'objects':scanned,'matches':0}))
        frozen=json.loads((self.output/'source-hashes.json').read_text())
        changed=[name for name,digest in frozen.items() if not (ROOT/name).is_file() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
        (self.output/'source-closure.json').write_text(json.dumps({'files':len(frozen),'changed_during_run':changed}))
        assert not changed,changed
        (self.output/'PASS').write_text('\n'.join(self.checks)+'\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--private-dir", required=True)
    parser.add_argument("--sandbox-endpoint", required=True)
    parser.add_argument("--sandbox-key-file", required=True)
    args = parser.parse_args()
    InstalledUser(args).run()


if __name__ == "__main__":
    if len(sys.argv)>1 and sys.argv[1]=="--peer-server": peer_server(sys.argv[2],sys.argv[3])
    else: main()
