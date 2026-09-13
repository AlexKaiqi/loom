"""S ownership of immutable ordinary snapshots; no Engine, Pi drive or scheduler.

register(kind, full_ref, registered_scope) is an injected trusted, monotonic
registry callback. expected_scope comes from the accepted original X/Session
registration, never from an owner receipt supplied by an untrusted peer.
"""
from pathlib import Path
from datetime import datetime, timezone
from functools import wraps
import copy
import fcntl
import os
import stat

from .snapshot_files import (SnapshotError, require, canonical, decode, sha, file_fact,
                             read_ref, save, sync_dir, archive, empty_archive,
                             session_original, EMPTY, SCOPE, EXEC, RAW_LIMIT, CONTROL_LIMIT)


def checked(method):
    @wraps(method)
    def call(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except SnapshotError:
            raise
        except (OSError, KeyError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
            raise SnapshotError('invalid_snapshot', 'invalid or unavailable original snapshot: '+str(exc)) from exc
    return call


def checkpoint_scope(fullref, expected):
    require(type(fullref) is dict and fullref.get('owner') == 'X', 'original X checkpoint required')
    original = expected['original_execution']; binding = fullref['source_binding']
    require(type(original) is dict and all(binding.get(k) == original[k] for k in EXEC), 'original execution association differs')
    require(all(binding.get(k) == expected[k] for k in ('namespace', 'session_id', 'session_generation')),
            'original Session association differs')
    require('surface_id' not in binding or binding['surface_id'] == expected['surface_id'], 'original Surface differs')
    require(all(fullref.get(k) == original[k] for k in ('execution_id', 'object_generation', 'freeze_generation', 'state')),
            'original checkpoint tuple differs')


class SnapshotStore:
    def __init__(self, root, namespace, register, *, global_budget_bytes=20*1024**3):
        root = Path(root)
        require(root.is_absolute() and root.resolve() == root, 'trusted owner root must be an unaliased absolute path')
        require(type(namespace) is str and namespace and callable(register), 'trusted namespace and registry callback required')
        require(type(global_budget_bytes) is int and CONTROL_LIMIT <= global_budget_bytes <= 20*1024**3,
                'owner storage budget exceeds admitted limit')
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root = root; self.namespace = namespace; self.register = register
        self.global_budget = global_budget_bytes
        # Sixteen actual host objects per minimum two-MiB control reservation.
        self.inode_limit = 2+(global_budget_bytes//CONTROL_LIMIT)*16
        self.root_identity = (root.stat().st_dev, root.stat().st_ino)

    def _root(self):
        st = self.root.lstat()
        require(stat.S_ISDIR(st.st_mode) and (st.st_dev, st.st_ino) == self.root_identity,
                'trusted owner root changed')

    def _id(self, value):
        require(type(value) is str and 0 < len(value.encode('utf8')) <= 256, 'bounded stable identity required')
        return sha(canonical(value))

    def _scope(self, scope):
        require(type(scope) is dict and set(scope) == set(SCOPE)|{'original_execution'}, 'complete registered Session scope required')
        require(scope['namespace'] == self.namespace and all(type(scope[k]) is str and scope[k] for k in SCOPE[:-1]) and
                type(scope['session_generation']) is int and scope['session_generation'] > 0, 'original owner scope differs')
        canonical(scope)

    def _budget(self, extra_bytes=0, extra_inodes=0):
        requests = list(self.root.glob('confirm-*/request.json'))
        reserved = sum(decode(file_fact(path, CONTROL_LIMIT)[1])['reserved_bytes'] for path in requests)
        groups = {path.parent for path in requests}
        inside = outside = count = 0; seen = set()
        for path in [self.root, *self.root.rglob('*')]:
            st = path.lstat(); require(not stat.S_ISLNK(st.st_mode), 'owner store contains an unexpected alias')
            identity = (st.st_dev, st.st_ino)
            if identity not in seen:
                if any(path == group or group in path.parents for group in groups):
                    inside += st.st_blocks*512
                else:
                    outside += st.st_blocks*512
                count += 1; seen.add(identity)
        require(max(reserved, inside)+outside+extra_bytes <= self.global_budget and count+extra_inodes <= self.inode_limit,
                'original owner storage reservation exhausted', 'storage_limit')

    def _save_json(self, path, body):
        raw = canonical(body)+b'\n'; require(len(raw) <= CONTROL_LIMIT, 'owner control document exceeds limit')
        group = next((q for q in path.parents if q.parent == self.root and q.name.startswith('confirm-')), None)
        if group is not None and not path.exists():
            members = [group, *group.rglob('*')]
            control = sum(q.lstat().st_blocks*512 for q in members if q.name != 'original.tar')
            require(control+((len(raw)+4095)//4096)*4096 <= CONTROL_LIMIT and len(members)+1 <= 16,
                    'confirmation control reservation exhausted', 'storage_limit')
        return save(path, raw)

    def _request(self, request_id):
        return self.root/('confirm-'+self._id(request_id))

    def _snapshot(self, directory, expected, raw, entries, logical, origin):
        directory.mkdir(mode=0o700, exist_ok=True); sync_dir(directory.parent)
        archive_ref = save(directory/'original.tar', raw)
        manifest = dict(schema='lore-x-session-ordinary-manifest/v1',
                        **{k:expected[k] for k in ('namespace', 'session_id', 'session_generation')},
                        metadata_profile='linux-posix-session-no-xattr-acl-v1', entries=entries,
                        logical_bytes=logical, archive_sha256=archive_ref['sha256'], archive_bytes=len(raw))
        manifest_ref = self._save_json(directory/'manifest.json', manifest)
        record = dict(schema='lore-x-session-ordinary-snapshot/v1', origin=origin, **copy.deepcopy(expected),
                      archive=archive_ref, manifest=manifest_ref)
        record_ref = self._save_json(directory/'record.json', record)
        ref = dict(owner='S', id=directory.parent.name,
                   **{k:expected[k] for k in ('namespace', 'session_id', 'session_generation')},
                   record_path=record_ref['path'], record_sha256=record_ref['sha256'])
        for prefix, item in [('archive', archive_ref), ('manifest', manifest_ref)]:
            for key in ('path', 'sha256', 'bytes'):
                ref[prefix+'_'+key] = item[key]
        self._save_json(directory/'reference.json', ref)
        return ref, archive_ref

    def _verify(self, result, request):
        expected, fullref = request['expected_scope'], request['checkpoint_full_ref']
        self._scope(expected)
        quarantined = request.get('retention_only', False)
        key = 'quarantine_ref' if quarantined else 'snapshot_ref'
        require(set(result) == {key, 'owner_record_ref', 'storage_charge_ref'}, 'retention result kind differs')
        owner = decode(read_ref(result['owner_record_ref'], CONTROL_LIMIT)[1])
        require(owner['schema'] == 'lore-s-original-snapshot-owner/v1' and
                owner['confirmation_request_id'] == request['request_id'] and owner['scope'] == {k:expected[k] for k in SCOPE} and
                owner['source'] == {'kind': request['origin'], 'original_checkpoint_full_ref': fullref} and
                owner['snapshot_ref'] == result[key] and owner['storage_charge_ref'] == result['storage_charge_ref'],
                'original owner record association differs')
        if quarantined:
            reason = request['quarantine_reason']
            self._reason(reason)
            require(fullref is not None and request['origin'] == 'checkpoint' and
                    owner.get('retention_only') is True and owner.get('session_admission') == 'NOT_ADMITTED' and
                    owner.get('quarantine_reason') == reason, 'quarantine admission or reason differs')
        else:
            require(not owner.get('retention_only', False), 'quarantine is not a healthy Session')
        ref = result[key]
        require(ref['owner'] == 'S' and all(ref[k] == expected[k] for k in ('namespace', 'session_id', 'session_generation')), 'snapshot reference scope differs')
        record_raw = file_fact(ref['record_path'], CONTROL_LIMIT)[1]
        require(sha(record_raw) == ref['record_sha256'], 'original snapshot record hash differs')
        record = decode(record_raw)
        require(set(record) == {'schema', 'origin', *SCOPE, 'original_execution', 'archive', 'manifest'} and
                record['schema'] == 'lore-x-session-ordinary-snapshot/v1' and record['origin'] == request['origin'] and
                all(record[k] == expected[k] for k in expected), 'original snapshot record scope differs')
        fact, raw = read_ref(record['archive']); mf, mr = read_ref(record['manifest'], CONTROL_LIMIT)
        for prefix, original in [('archive', fact), ('manifest', mf)]:
            require(all(ref[prefix+'_'+k] == original[k] for k in ('path', 'sha256', 'bytes')), 'snapshot reference/file differs')
        entries, files, logical = archive(raw); manifest = decode(mr)
        require(manifest == dict(schema='lore-x-session-ordinary-manifest/v1',
                                **{k:expected[k] for k in ('namespace', 'session_id', 'session_generation')},
                                metadata_profile='linux-posix-session-no-xattr-acl-v1', entries=entries,
                                logical_bytes=logical, archive_sha256=fact['sha256'], archive_bytes=fact['bytes']),
                'actual complete archive/manifest differs')
        if fullref is None:
            require(expected['original_execution'] is None and entries == EMPTY, 'empty snapshot conceals original work')
            session = dict(jsonl=None, metadata=None, binding=None)
        else:
            checkpoint_scope(fullref, expected)
            require(fact['sha256'] == fullref['sha256'] and fact['bytes'] == fullref['size'], 'retained original bytes differ')
            if Path(fullref['path']).exists():
                original = read_ref(dict(path=fullref['path'], sha256=fullref['sha256'], bytes=fullref['size']))[0]
                require(original['root'] != fact['root'], 'hardlink or same inode is not ownership transfer')
            session = None if quarantined else session_original(files, request['original_binding'], expected)
        require(owner['actual_archive_object'] == fact['root'] and owner['original_session'] == session, 'owner original inode/Session bytes differ')
        charge = decode(read_ref(result['storage_charge_ref'], CONTROL_LIMIT)[1])
        require(charge['scope'] == owner['scope'] and charge['snapshot_ref'] == ref and charge['archive_fact'] == fact and
                charge['reserved_bytes'] == request['reserved_bytes'] and charge['reserved_inodes'] == 16 and
                charge['global_budget_bytes'] == self.global_budget, 'original owner storage charge differs')
        return owner

    def _publish(self, result, expected):
        self.register('snapshot', copy.deepcopy(result['quarantine_ref'] if 'quarantine_ref' in result else result['snapshot_ref']), copy.deepcopy(expected))
        self.register('storage-charge', copy.deepcopy(result['storage_charge_ref']), copy.deepcopy(expected))

    @checked
    def empty(self, request_id, scope):
        scope = copy.deepcopy(scope)
        if 'original_execution' not in scope:
            scope['original_execution'] = None
        require(scope['original_execution'] is None, 'empty source cannot carry an old execution')
        return self.confirm(request_id, scope, None, None)

    @staticmethod
    def _reason(reason):
        require(type(reason) is str and 0 < len(reason.encode('utf8')) <= 1024,
                'bounded nonempty quarantine reason required')

    @checked
    def quarantine(self, request_id, expected_scope, checkpoint_full_ref, reason):
        """Retain exact ordinary bytes without admitting a healthy Pi Session."""
        self._reason(reason)
        require(checkpoint_full_ref is not None, 'quarantine requires an original checkpoint')
        return self._confirmation(request_id, expected_scope, checkpoint_full_ref, None, reason)

    @checked
    def confirm(self, request_id, expected_scope, checkpoint_full_ref, original_binding):
        return self._confirmation(request_id, expected_scope, checkpoint_full_ref, original_binding)

    def _confirmation(self, request_id, expected_scope, checkpoint_full_ref, original_binding, quarantine_reason=None):
        self._root(); self._scope(expected_scope)
        quarantined = quarantine_reason is not None
        expected_scope, checkpoint_full_ref, original_binding = copy.deepcopy((expected_scope, checkpoint_full_ref, original_binding))
        fullref = checkpoint_full_ref; origin = 'empty-initial' if fullref is None else 'checkpoint'
        if fullref is None:
            require(expected_scope['original_execution'] is None and original_binding is None, 'empty origin has prior state')
            source_size = len(empty_archive())
        else:
            checkpoint_scope(fullref, expected_scope)
            require(type(fullref['size']) is int and 0 <= fullref['size'] <= RAW_LIMIT, 'bounded original archive required')
            source_size = fullref['size']
        request = dict(request_id=request_id, expected_scope=expected_scope, checkpoint_full_ref=fullref,
                       original_binding=original_binding, origin=origin, reserved_bytes=((source_size+4095)//4096)*4096+CONTROL_LIMIT, reserved_inodes=16)
        if quarantined:
            request.update(retention_only=True, quarantine_reason=quarantine_reason)
        directory = self._request(request_id)
        with (self.root/'.lock').open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if (directory/'request.json').exists():
                require(decode(file_fact(directory/'request.json', CONTROL_LIMIT)[1]) == request, 'confirmation identity has different complete content', 'conflict')
                if (directory/'result.json').exists():
                    result = decode(file_fact(directory/'result.json', CONTROL_LIMIT)[1]); self._verify(result, request)
                    self._publish(result, expected_scope)
                    return result
            if fullref is None:
                raw = empty_archive(); source_fact = None
            else:
                source_fact, raw = read_ref(dict(path=fullref['path'], sha256=fullref['sha256'], bytes=fullref['size']))
            entries, files, logical = archive(raw)
            session = (None if quarantined else dict(jsonl=None, metadata=None, binding=None) if fullref is None else
                       session_original(files, original_binding, expected_scope))
            if not (directory/'request.json').exists():
                self._budget(request['reserved_bytes'], 16)
                directory.mkdir(mode=0o700, exist_ok=False); sync_dir(self.root)
                self._save_json(directory/'request.json', request)
            ref, fact = self._snapshot(directory/'snapshot', expected_scope, raw, entries, logical, origin)
            require(source_fact is None or fact['root'] != source_fact['root'], 'copy did not create independent inode')
            charge = dict(schema='lore-s-storage-charge/v1', scope={k:expected_scope[k] for k in SCOPE}, snapshot_ref=ref,
                          archive_fact=fact, reserved_bytes=request['reserved_bytes'], global_budget_bytes=self.global_budget, reserved_inodes=16)
            charge_ref = self._save_json(directory/'charge.json', charge)
            if (directory/'owner.json').exists():
                owner_ref = file_fact(directory/'owner.json', CONTROL_LIMIT)[0]
            else:
                body = dict(schema='lore-s-original-snapshot-owner/v1', id=directory.name, confirmation_request_id=request_id,
                            scope=charge['scope'], source=dict(kind=origin, original_checkpoint_full_ref=fullref), snapshot_ref=ref,
                            actual_archive_object=fact['root'], original_session=session, storage_charge_ref=charge_ref,
                            source_owner_record_ref=None, confirmed_at=datetime.now(timezone.utc).isoformat())
                if quarantined:
                    body.update(retention_only=True, session_admission='NOT_ADMITTED', quarantine_reason=quarantine_reason)
                owner_ref = self._save_json(directory/'owner.json', body)
            result = {'quarantine_ref' if quarantined else 'snapshot_ref': ref,
                      'owner_record_ref': owner_ref, 'storage_charge_ref': charge_ref}
            self._verify(result, request); self._budget()
            self._publish(result, expected_scope)
            self._save_json(directory/'result.json', result)
            return result

    @checked
    def query(self, request_id):
        return self._query(request_id, False)

    @checked
    def query_quarantine(self, request_id):
        """Read only: no registry publication, repair, lock write or new charge."""
        return self._query(request_id, True)

    def _query(self, request_id, quarantined):
        self._root(); directory = self._request(request_id)
        request = decode(file_fact(directory/'request.json', CONTROL_LIMIT)[1])
        require(request.get('retention_only', False) is quarantined, 'snapshot query kind differs')
        result = decode(file_fact(directory/'result.json', CONTROL_LIMIT)[1])
        self._verify(result, request)
        return result

    @checked
    def receipt(self, receipt_id, old_fullref, retained, successor_fullref=None, successor_owner=None, sealed=False):
        self._root(); self._id(receipt_id)
        owner = decode(read_ref(retained['owner_record_ref'], CONTROL_LIMIT)[1])
        quarantined = owner.get('retention_only', False)
        require(not quarantined or sealed is True, 'quarantine requires a sealed ownership transfer')
        original = self._query(owner['confirmation_request_id'], quarantined)
        require(original == retained, 'retained owner is not the original confirmed result')
        request = decode(file_fact(self._request(owner['confirmation_request_id'])/'request.json', CONTROL_LIMIT)[1])
        expected = request['expected_scope']
        require(request['checkpoint_full_ref'] == old_fullref and old_fullref is not None, 'receipt selects another original checkpoint')
        successor_ref = successor_owner.get('owner_record_ref') if type(successor_owner) is dict and 'owner_record_ref' in successor_owner else successor_owner
        if sealed:
            require(successor_fullref is None and successor_ref is None, 'sealed transfer cannot invent a successor')
        else:
            newer = copy.deepcopy(expected)
            require(type(successor_fullref) is dict and successor_fullref['freeze_generation'] > old_fullref['freeze_generation'], 'successor is not newer')
            newer['original_execution'].update(freeze_generation=successor_fullref['freeze_generation'], state=successor_fullref['state'])
            checkpoint_scope(successor_fullref, newer)
            following = decode(read_ref(successor_ref, CONTROL_LIMIT)[1])
            result = self.query(following['confirmation_request_id'])
            require(result['owner_record_ref'] == successor_ref and following['source'] == {'kind':'checkpoint', 'original_checkpoint_full_ref':successor_fullref}, 'successor ownership differs')
        body = dict(owner='S', receipt_id=receipt_id, **{k:expected[k] for k in ('namespace', 'session_id', 'session_generation')},
                    old_checkpoint_full_ref=old_fullref, retained_original_ref=retained['quarantine_ref' if quarantined else 'snapshot_ref'],
                    confirmed_successor_full_ref=successor_fullref, successor_owner_record_ref=successor_ref,
                    handoff_kind='sealed_ownership_transfer' if sealed else 'successor_retained',
                    retained_owner_record_ref=retained['owner_record_ref'], storage_charge_ref=retained['storage_charge_ref'])
        path = self.root/('receipt-'+self._id(receipt_id)+'.json')
        with (self.root/'.lock').open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not path.exists():
                self._budget(len(canonical(body))+4096, 1)
            receipt_file = self._save_json(path, body)
            ref = {**body, 'actual_owner_receipt_path_sha_bytes':receipt_file}
            self.register('owner-receipt', copy.deepcopy(ref), copy.deepcopy(expected))
            return ref
