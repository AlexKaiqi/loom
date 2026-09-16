"""Trusted test-only actual F inputs, fixed dependency copies and immutable config."""
from pathlib import Path
import copy, hashlib, os, shutil, stat, sys, uuid
from artifacts import canonical, file_fact, save, sha_bytes
from snapshot_fixtures import original, scope
ROOT = Path(__file__).resolve().parents[3]
DESIGN = ROOT / 'design/g3/x-node-profile'

def identity(path):
    item = Path(path).stat(); return {'dev': item.st_dev, 'ino': item.st_ino}

def tree(root):
    root = Path(root); rows = {}
    for p in [root, *sorted(root.rglob('*'))]:
        st = p.lstat(); row = {'mode': stat.S_IMODE(st.st_mode), 'uid': st.st_uid, 'gid': st.st_gid, 'mtime_ns': st.st_mtime_ns}
        if stat.S_ISDIR(st.st_mode): row['kind'] = 'dir'
        elif stat.S_ISREG(st.st_mode): row.update(kind='file', byte_length=st.st_size, sha256=file_fact(p, 268435456)[0]['sha256'])
        elif stat.S_ISLNK(st.st_mode):
            target = p.resolve(strict=True)
            if not target.is_relative_to(root): raise ValueError('readonly link leaves registered root')
            row.update(kind='symlink', target=os.readlink(p), resolved_relative=target.relative_to(root).as_posix())
        else: raise ValueError('readonly tree special member')
        rows['.' if p == root else p.relative_to(root).as_posix()] = row
    return rows

def readonly_manifest(root, role, source_ref, path):
    value = {'schema': 'lore-x-readonly-tree/v1', 'role': role,
             'root': {'path': str(root), **identity(root)}, 'entries': tree(root), 'source_ref': source_ref}
    save(path, value)
    return file_fact(path, 2097152)[0]

def dependencies(out):
    import json
    manifest = json.loads((DESIGN / 'dependencies.json').read_text())
    root = Path(out) / 'dependencies'; root.mkdir(parents=True, exist_ok=False)
    for item in manifest['files']:
        source = Path(item['source']); fact, raw = file_fact(source, 268435456)
        if fact['sha256'] != item['sha256'] or fact['bytes'] != item['bytes']: raise ValueError('fixed dependency source changed')
        target = root / Path(item['target']).relative_to('/opt')
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw); target.chmod(item['mode'] & ~0o222)
    for item in manifest['links']:
        target = root / Path(item['target']).relative_to('/opt'); target.parent.mkdir(parents=True, exist_ok=True)
        if os.readlink(item['source']) != item['link']: raise ValueError('fixed dependency link changed')
        target.symlink_to(item['link'])
    config = root / 'lore/config/tsconfig.json'; config.parent.mkdir(parents=True, exist_ok=True)
    # The pinned design tsconfig replaces any copy that arrived through the tree
    # (both are equal in a correct build); unlink first because the copied file
    # is already read-only and ordinary (non-root) owners cannot overwrite it.
    config.unlink(missing_ok=True)
    config.write_bytes((DESIGN / 'tsconfig.json').read_bytes()); config.chmod(0o444)
    for p in sorted([root, *root.rglob('*')], key=lambda p: len(p.parts), reverse=True):
        if p.is_dir() and not p.is_symlink(): p.chmod(0o555)
    source_ref = {'owner': 'trusted-X-configuration', 'kind': 'profile-dependencies',
                  'upstream_manifest': file_fact(DESIGN / 'dependencies.json')[0],
                  'generated_config': {**file_fact(config)[0], 'original': file_fact(DESIGN / 'tsconfig.json')[0]}}
    manifest_ref = readonly_manifest(root, 'dependencies', source_ref, Path(out) / 'dependencies-manifest.json')
    return {'role': 'dependencies', 'source': {'path': str(root), **identity(root)}, 'target': '/opt',
            'read_only': True, 'manifest_ref': manifest_ref, 'content_ref': source_ref}

class FInputs:
    def __init__(self, root):
        sys.path.insert(0, str(ROOT / 'validation/components/x'))
        from source_closure import verify_f
        from lore_files import FileStore
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=False)
        self.equivalence = verify_f(ROOT); self.allowed = {}; self.calls = []
        self.store = FileStore(self.root / 'control', self.auth, self.ref,
                               limits={'max_entries': 1024, 'max_logical_bytes': 2097152, 'max_archive_bytes': 4194304,
                                       'window_seconds': 10})
    def check(self, kind, value, operation, context):
        good = (value, context) == self.allowed.get((kind, operation))
        self.calls.append({'kind': kind, 'value': copy.deepcopy(value), 'operation': operation,
                           'context': copy.deepcopy(context), 'accepted': good})
        (self.root / 'authority-calls.json').write_bytes(canonical(self.calls) + b'\n')
        return good
    def auth(self, value, operation, context): return self.check('authorization', value, operation, context)
    def ref(self, value, operation, context): return self.check('reference', value, operation, context)
    def view(self, role, source):
        resource = 'xn-' + role + '-' + uuid.uuid4().hex
        grant = {'owner': 'controlled-R-fixture', 'id': resource}
        binding = {'resource_id': resource, 'domain': 'workspace' if role == 'workspace' else 'surface',
                   'path': str(source), 'root': identity(source), 'revision': 1, 'authorization': grant}
        coordination = {'owner': 'controlled-R-fixture', 'id': 'capture-' + resource, 'binding': binding}
        rid = 'capture-' + role
        context = {'schema': 'lore-f-authority-context/v1', 'operation': 'capture', 'request_id': rid,
                   'binding': binding, 'actual_root': binding['root'], 'profile': 'host-v1',
                   'base_ref': None, 'coordination': coordination}
        self.allowed['authorization', 'capture'] = (copy.deepcopy(grant), copy.deepcopy(context))
        self.allowed['reference', 'coordination'] = (copy.deepcopy(coordination), copy.deepcopy(context))
        bundle = self.store.capture(rid, binding, coordination)
        target = self.root / ('materialized-' + role)
        context = {'schema': 'lore-f-authority-context/v1', 'operation': 'materialize', 'request_id': 'read-' + role,
                   'version_ref': bundle['version_ref'], 'target_path': str(target),
                   'target_parent': {'path': str(target.parent), 'root': identity(target.parent)}, 'profile': 'host-v1'}
        self.allowed['authorization', 'materialize'] = (copy.deepcopy(grant), copy.deepcopy(context))
        materialized = self.store.materialize('read-' + role, bundle['version_ref'], str(target), grant)
        if tree(source) != tree(target): raise ValueError('actual F materialization differs')
        save(self.root / (role + '-F-actual.json'), {'bundle': bundle, 'materialized': materialized})
        content_ref = {'owner': 'F', 'version_ref': bundle['version_ref'], 'original_manifest': file_fact(Path(bundle['manifest_path']))[0],
                       'materialized_root': {'path': str(target), **identity(target)}}
        manifest_ref = readonly_manifest(target, role, content_ref, self.root / (role + '-readonly-manifest.json'))
        return {'role': role, 'source': {'path': str(target), **identity(target)}, 'target': '/' + role,
                'read_only': True, 'manifest_ref': manifest_ref, 'content_ref': content_ref}


def register(authority_root, kind, ref, registered_scope):
    """Trusted driver-only append, not a candidate or peer method."""
    root = Path(authority_root); root.mkdir(parents=True, exist_ok=True)
    registration = {'kind': kind, 'ref': copy.deepcopy(ref), 'registered_scope': copy.deepcopy(registered_scope)}
    raw = canonical(registration) + b'\n'
    key = sha_bytes(canonical({'kind': kind, 'ref': ref}))
    path = root / (key + '.json')
    if path.exists():
        if path.read_bytes() != raw: raise ValueError('trusted registration cannot rebind')
    else: save(path, registration)
    return file_fact(path)[0]

class Fixture:
    def __init__(self, root, deps, mode='channel', large=False, namespace=None, session_id='prep-session'):
        import json
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=False)
        self.state = self.root / 'state'; self.state.mkdir()
        self.authority_root = self.root / 'trusted-authority'; self.authority_root.mkdir()
        self.namespace = namespace or ('xn-' + uuid.uuid4().hex)
        self.session_id = session_id; self.surface_id = 'surface-one'
        self.execution_id = 'exec-' + uuid.uuid4().hex
        self.execution_ids = {self.execution_id}
        self.expected_scope = {'namespace': self.namespace, 'surface_id': self.surface_id,
                               'session_id': self.session_id, 'session_generation': 1, 'original_execution': None}
        self.snapshot_ref = original(self.root / 'initial-original', self.expected_scope)
        self.f = FInputs(self.root / 'F')
        sources = self.root / 'sources'; sources.mkdir()
        for role in ('harness', 'input', 'workspace'): (sources / role).mkdir()
        harness = sources / 'harness'
        (harness / 'entry.mts').write_bytes((ROOT / 'validation/components/x_node_profile/entry.mts').read_bytes())
        pi = (ROOT / 'validation/components/s/probe-public.mts').read_text()
        pi = pi.replace('../../../research/repos/pi', '/opt/lore/research/repos/pi')
        # Test-only wrapper around the unchanged actual public API, not a Pi source patch.
        pi = pi.replace("fresh=['single','multi','pending','control']", "fresh=['accept','single','multi','pending','control']")
        pi = pi.replace("if(mode!=='query')out.driven=", "if(mode!=='query'&&mode!=='accept')out.driven=")
        pi = pi.replace('process.exit(0);', 'export {session,lane,context,value};').replace("id:'prep-session'", 'id:'+json.dumps(self.session_id))
        (harness / 'pi-probe.mts').write_text(pi)
        (sources / 'input/original.txt').write_bytes(b'INPUT_ORIGINAL\n')
        workspace = sources / 'workspace'
        if large:
            for i in range(64): (workspace / f'd{i:02d}').mkdir()
            for i in range(512):
                raw = (f'original-file-{i:04d}|'.encode() + b'a' * 128)[:128]
                (workspace / f'd{i % 48:02d}' / f'f{i:04d}.txt').write_bytes(raw)
            (workspace / 'workspace.diff').write_bytes(''.join(('+' if i % 2 else '-') + f'line {i:04d} stable original source payload\n' for i in range(4096)).encode())
        else: (workspace / 'workspace.diff').write_bytes(b'-old\n+new\n')
        self.mounts = [copy.deepcopy(deps)] + [self.f.view(role, sources / role) for role in ('harness', 'input', 'workspace')]
        self.request = json.loads((DESIGN / 'request-template.json').read_text())
        self.request.update(execution_id=self.execution_id, invocation_id='invocation-one', step_id='step-one',
                            source_result='saved-original-one', harness_version=self.mounts[1]['content_ref']['version_ref'],
                            session_binding={k: self.expected_scope[k] for k in ('namespace', 'surface_id', 'session_id', 'session_generation')},
                            base_version=sha_bytes(canonical(self.snapshot_ref)), snapshot_ref=self.snapshot_ref, readonly_mounts=self.mounts)
        self.request['command_argv'][4] = mode
        profile = json.loads((DESIGN / 'profile.json').read_text())
        self.slot_ref = {'owner': 'trusted-X-configuration', 'slot_id': 'slot-one', 'revision': 1,
                         'plan_sha256': sha_bytes(canonical(profile['slot_reservation'])), 'role': 'session'}
        self.grant_ref = self.grant(self.request)
        self.authority = {'grant_ref': self.grant_ref, 'slot_ref': self.slot_ref}
        self.slot = {'slot_id': 'slot-one', 'revision': 1, 'namespace': self.namespace,
                     'plan_sha256': self.slot_ref['plan_sha256'], 'plan': profile['slot_reservation'],
                     'allowed_principals': ['trusted-S', 'trusted-tool'], 'state_root': str(self.state)}
        register(self.authority_root, 'snapshot', self.snapshot_ref, self.expected_scope)
        for mount in self.mounts: register(self.authority_root, 'readonly-view', mount, {'namespace': self.namespace, 'role': mount['role']})
        self.config = {'schema': 'lore-x-trusted-node-test-config/v1', 'transport_principal': 'trusted-S', 'state_root': str(self.state),
                       'profiles': [{'id': profile['id'], 'path': str(DESIGN / 'profile.json'), 'sha256': file_fact(DESIGN / 'profile.json')[0]['sha256']}],
                       'slots': [self.slot], 'grants': [self.grant_ref], 'references': {'snapshots': [{'ref': self.snapshot_ref, 'registered_scope': self.expected_scope}], 'F_views': [m['content_ref'] for m in self.mounts[1:]], 'owner_receipts': []},
                       'read_only_roots': self.mounts, 'allowed_harness_entries': [{'path': '/harness/entry.mts', 'sha256': file_fact(harness / 'entry.mts')[0]['sha256'], 'argv_modes': ['channel', 'pi-accept', 'pi-single', 'pi-query', 'read-files', 'isolation', 'quota-bytes', 'quota-unlinked', 'quota-inodes', 'output-flood']}],
                       'dynamic_reference_authorities': [{'root': str(self.authority_root), 'identity': 'controlled-S-F-owner-fixture',
                           'namespace': self.namespace, 'allowed_kinds': ['snapshot', 'readonly-view', 'owner-receipt', 'grant', 'storage-charge'],
                           'rule': 'immutable-full-ref-registration/v1'}]}
        self.config_path = self.root / 'trusted-config.json'; save(self.config_path, self.config)
        save(self.root / 'request.json', self.request); save(self.root / 'authority.json', self.authority)
        self.values = {}; self.params = {}; self.canary = ('owned-fixture-canary-' + uuid.uuid4().hex).encode()
        (self.root / 'control').mkdir(); (self.root / 'control/control-canary').write_bytes(self.canary)
        self.state.mkdir(exist_ok=True); self.cache = self.root / 'cache'; self.cache.mkdir()
    def grant(self, request):
        from artifacts import strict_json
        record = {'principal': 'trusted-S', 'operations': ['execute', 'query', 'checkpoint', 'stop'],
                  'original_request': copy.deepcopy(request), 'request_digest': sha_bytes(canonical(request)),
                  'scope': copy.deepcopy(request['session_binding']), 'slot_ref': self.slot_ref, 'role': 'session'}
        key = record['request_digest']; path = self.authority_root / ('grant-' + key + '.json')
        if not path.exists(): save(path, record)
        elif strict_json(path.read_bytes()) != record: raise ValueError('original grant rebind')
        ref = {'owner': 'trusted-X-configuration', 'id': key, 'record_path': str(path), 'sha256': file_fact(path)[0]['sha256']}
        register(self.authority_root, 'grant', ref, record['scope'])
        return ref
    def mapping(self):
        return {'root': self.root, 'state': self.state, 'cache': self.cache, 'request': self.request,
                'authority': self.authority, 'execution_ids': self.execution_ids, 'params': self.params,
                'values': self.values, 'canary': self.canary}
