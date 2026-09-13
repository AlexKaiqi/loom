"""Trusted Runtime file access from original R registration and F Git provenance."""
import copy
import json
from pathlib import Path, PurePosixPath
from lore_control.values import decode
from lore_files.errors import require
from lore_files.util import canonical, digest, identity, ordinary_path
from lore_files.metadata import walk


class HostFiles:
    def __init__(self, control, host):
        self.control, self.host = control, copy.deepcopy(host)
        self.files = self.session_resolver = None
        for key in ('artifact_root', 'plan_root'):
            path = Path(host[key])
            require(path.is_absolute() and path.resolve() == path, 'UNAUTHORIZED', 'unaliased host root required')

    def _file_reference(self, ref):
        require(type(ref) is dict and ref.get('owner') == 'F' and ref.get('kind') == 'file',
                'REFERENCE_TYPE', 'file reference must name its actual F owner and kind')

    def _private(self, path):
        path = ordinary_path(path)
        return any(path.is_relative_to(Path(self.host[k])) for k in ('artifact_root', 'plan_root'))

    def _resource(self, id, operation):
        c = self.control
        with c._lock:
            row = c.db.execute('SELECT * FROM resources WHERE id=?', (id,)).fetchone()
            if row is None: return None
            require(row['active'] == 1, 'UNAUTHORIZED', 'original resource is no longer active')
            c._authorize(self.host['principal'], row['namespace'])
            c._resource_access(row, self.host['principal'], operation)
            require(row['namespace'] == self.host['namespace'], 'UNAUTHORIZED', 'original resource namespace differs')
            return c._resource_value(row)

    def _version(self, version):
        self.files.versions.load(version)
        resource = self._resource(version['resource_id'], 'read')
        if resource is not None:
            return resource['kind'] == version['domain']
        if any(s['resource_id'] == version['resource_id'] and s['domain'] == version['domain'] for s in self.host['initial_sources']):
            return True
        provenance = json.loads(self.files.versions.git('cat-file', 'blob', version['git_ref']+':provenance.json'))
        binding = provenance['binding']
        return (provenance['operation'] == 'capture' and binding['resource_id'] == version['resource_id'] and
                binding['domain'] == version['domain'] and self._private(binding['path']))

    def _binding(self, binding):
        require(binding['authorization'] == self.host['authorization'], 'UNAUTHORIZED', 'fixed host authorization differs')
        path = ordinary_path(binding['path'])
        require(identity(path) == binding['root'], 'STALE_BINDING', 'original source root changed')
        resource = self._resource(binding['resource_id'], 'write')
        if resource is not None:
            return (resource['kind'] == binding['domain'] and resource['path'] == str(path) and
                    resource['revision'] == binding['revision'] and
                    binding['root'] == {k:resource[k] for k in ('dev', 'ino')})
        source = {k:binding[k] for k in ('resource_id', 'domain', 'path', 'root', 'revision')}
        return source in self.host['initial_sources'] or self._private(path)

    def authorization(self, ref, purpose, context):
        try:
            if ref != self.host['authorization']: return False
            if purpose == 'capture': return self._binding(context['binding'])
            if purpose == 'read_reference':
                self._file_reference(context['reference'])
                return self._version(context['reference']['version_ref'])
            if purpose == 'materialize':
                return self._private(context['target_path']) and self._version(context['version_ref'])
            return False
        except Exception:
            return False

    def reference(self, ref, purpose, context):
        try:
            if purpose != 'coordination' or context['operation'] != 'capture': return False
            binding = context['binding']
            if not self._binding(binding): return False
            if ref == dict(owner='trusted-runtime-initial', binding=binding):
                return ({k:binding[k] for k in ('resource_id', 'domain', 'path', 'root', 'revision')} in
                        self.host['initial_sources'] or self._private(binding['path']))
            if ref.get('owner') == 'trusted-session-plans':
                with self.control._lock:
                    row = self.control._get_request(ref['invocation_id'])
                    return row['kind'] == 'invocation' and row['namespace'] == self.host['namespace'] and self._private(binding['path'])
            return False
        except Exception:
            return False

    def _bundle(self, version):
        require(self._version(version), 'UNAUTHORIZED', 'original version outside permitted resources')
        root = self.files.versions.artifacts/digest(canonical(version))
        bundle = dict(version_ref=version, archive_path=str(root/'archive.tar'), manifest_path=str(root/'manifest.json'))
        self.files.versions.validate_bundle(bundle)
        return bundle

    def _harness(self, ref):
        self._file_reference(ref)
        value = json.loads(self.files.read_reference(ref, self.host['authorization']))
        require(type(value) is dict and {'code', 'entry', 'harness_entry'} <= value.keys(), 'REFERENCE_TYPE', 'not an original Harness descriptor')
        view = value['code']; self.files.versions.validate_bundle(view['bundle'])
        require(self._version(view['bundle']['version_ref']), 'UNAUTHORIZED', 'Harness code outside permitted sources')
        material = view['materialized']; root = ordinary_path(material['path'])
        _, tree, _ = self.files.versions.load(view['bundle']['version_ref'])
        require(material['version_ref'] == view['bundle']['version_ref'] and identity(root) == material['root'] and
                walk(root, self.files.limits)[0] == tree, 'STALE_BINDING', 'original Harness materialization changed')
        for key in ('entry', 'harness_entry'):
            name = PurePosixPath(value[key])
            require(not name.is_absolute() and '..' not in name.parts and
                    tree['entries'].get(str(name), {}).get('kind') == 'file', 'REFERENCE_TYPE', 'Harness entry is not retained code')
        return value

    def control_reference(self, ref, purpose, expected=None):
        try:
            if purpose != 'harness': return False
            self._harness(ref); return True
        except Exception:
            return False

    def resolve(self, ref, purpose, expected):
        if purpose == 'F-view':
            resource = expected['registration']
            require(self._resource(resource['id'], 'read') == resource and
                    ref['resource_id'] == resource['id'] and ref['domain'] == resource['kind'],
                    'UNAUTHORIZED', 'original R/F resource association differs')
            bundle = self._bundle(ref)
            return dict(bundle=bundle, materialized=dict(path=resource['path'],
                root={k:resource[k] for k in ('dev', 'ino')}, version_ref=ref))
        if purpose in ('harness', 'capability', 'original-file'):
            self._file_reference(ref)
            if purpose == 'harness': self._harness(ref)
            if purpose in ('harness', 'capability'):
                require(ref == expected['invocation']['payload'][purpose+'_ref'], 'UNAUTHORIZED', 'original accepted descriptor differs')
            return self.files.read_reference(ref, self.host['authorization'])
        require(callable(self.session_resolver), 'REFERENCE_TYPE', 'trusted original Session resolver is missing')
        return self.session_resolver(ref, purpose, expected)
