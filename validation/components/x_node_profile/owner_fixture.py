"""Finite trusted owner fixture for XN09/11; no S product or Pi/Engine state machine.

expected_scope is supplied by the trusted driver from its original X registration.
original_binding names actual Pi files/address and the previously registered value.
The emitted charge is a conservative reservation, never a claim that X released.
"""
from pathlib import Path
from datetime import datetime, timezone
import copy, fcntl
from artifacts import (archive_bytes, canonical, file_fact, read_ref, require, save,
                       sha_bytes, snapshot, strict_json)
from snapshot_fixtures import original
from fixtures import register

SCOPE = ('namespace', 'surface_id', 'session_id', 'session_generation')
EXEC = ('execution_id', 'object_generation', 'request_digest', 'container_id',
        'exec_id', 'volume_id', 'freeze_generation')

def checkpoint_scope(ref, expected):
    require(isinstance(ref, dict) and ref.get('owner') == 'X', 'original X checkpoint required')
    binding = ref.get('source_binding', {})
    for key in ('namespace', 'session_id', 'session_generation'):
        require(binding.get(key) == expected[key], 'original registered Session differs: ' + key)
    execution = expected['original_execution']
    require(isinstance(execution, dict), 'original execution registration required')
    for key in EXEC:
        require(binding.get(key) == execution[key], 'original execution differs: ' + key)
    for key in ('execution_id', 'object_generation', 'freeze_generation', 'state'):
        require(ref.get(key) == execution[key], 'checkpoint tuple differs: ' + key)
    return binding

def session_original(files, descriptor, expected):
    jp, mp = descriptor['jsonl_relative_path'], descriptor['metadata_relative_path']
    require(jp in files and mp in files, 'original JSONL/metadata missing')
    raw = files[jp]
    require(raw.endswith(b'\n') and raw.strip(), 'torn original JSONL; never open Pi first')
    transactions = [strict_json(line) for line in raw.splitlines()]
    header = transactions[0]; metadata = strict_json(files[mp])
    require(isinstance(header, dict) and header.get('kind') == 'header' and header.get('v') == 4,
            'original Pi v4 header required')
    require({'id', 'cwd', 'path', 'createdAt', 'storageVersion'} <= metadata.keys(), 'complete original metadata required')
    for key in ('id', 'cwd', 'createdAt', 'storageVersion'):
        require(header.get(key) == metadata[key], 'original metadata/header differs: ' + key)
    require(metadata['id'] == expected['session_id'], 'original metadata Session differs')
    require(metadata['path'] == str(Path(metadata['cwd']) / jp), 'metadata path is not actual original member')
    namespace = descriptor.get('binding_namespace', 'lore.prep.binding')
    key = descriptor.get('binding_key', 'op-1'); found = False; binding = None
    for transaction in transactions[1:]:
        for row in transaction if isinstance(transaction, list) else [transaction]:
            require(isinstance(row, dict), 'invalid original transaction row')
            if row.get('kind') == 'value' and (row.get('namespace'), row.get('key')) == (namespace, key):
                require(row.get('op') in ('set', 'delete'), 'unknown original binding operation')
                found = row['op'] == 'set'; binding = row.get('value') if found else None
    require(found and binding == descriptor['binding'], 'actual original binding differs or missing')
    return {'jsonl': {'relative_path': jp, 'bytes': len(raw), 'sha256': sha_bytes(raw)},
            'metadata': {'relative_path': mp, 'bytes': len(files[mp]), 'sha256': sha_bytes(files[mp])},
            'binding': copy.deepcopy(binding)}

def retained_original(retained, expected, old_ref):
    checkpoint_scope(old_ref, expected)
    body = strict_json(read_ref(retained['owner_record_ref'], 2097152)[1])
    require(body.get('schema') == 'lore-s-original-snapshot-owner/v1', 'owner schema')
    require(body['scope'] == {k: expected[k] for k in SCOPE}, 'owner original scope differs')
    require(body['source'] == {'kind': 'checkpoint', 'original_checkpoint_full_ref': old_ref}, 'owner original fullref differs')
    require(body['snapshot_ref'] == retained['snapshot_ref'], 'retained fullref differs')
    observed = snapshot(retained['snapshot_ref'], expected)
    fact = observed['archive_fact']
    require(body['actual_archive_object'] == fact['root'], 'retained archive inode differs')
    require(fact['sha256'] == old_ref['sha256'] and fact['bytes'] == old_ref['size'], 'retained original bytes differ')
    if Path(old_ref['path']).exists():
        old_fact = read_ref({'path': old_ref['path'], 'sha256': old_ref['sha256'], 'bytes': old_ref['size']})[0]
        require(old_fact['root'] != fact['root'], 'hardlink/alias cannot transfer ownership')
    require(body['storage_charge_ref'] == retained['storage_charge_ref'], 'original storage charge differs')
    charge = strict_json(read_ref(retained['storage_charge_ref'], 2097152)[1])
    require(charge['snapshot_ref'] == retained['snapshot_ref'] and charge['scope'] == body['scope'], 'charge scope differs')
    require(charge['archive_fact'] == fact and charge['reserved_bytes'] >= fact['bytes'], 'actual owner charge absent')
    return body

def verify_receipt(ref, expected, old_ref):
    """External fixture check; expected MUST come from original registered X tuple."""
    body = strict_json(read_ref(ref['actual_owner_receipt_path_sha_bytes'], 2097152)[1])
    require(body == {k: v for k, v in ref.items() if k != 'actual_owner_receipt_path_sha_bytes'}, 'receipt body/ref mismatch')
    require(body['owner'] == 'S' and body['old_checkpoint_full_ref'] == old_ref, 'receipt owner/old fullref differs')
    for key in ('namespace', 'session_id', 'session_generation'):
        require(body[key] == expected[key], 'receipt original registered scope differs')
    retained = {'snapshot_ref': body['retained_original_ref'], 'owner_record_ref': body['retained_owner_record_ref'],
                'storage_charge_ref': body['storage_charge_ref']}
    retained_original(retained, expected, old_ref)
    if body['handoff_kind'] == 'sealed_ownership_transfer':
        require(body['confirmed_successor_full_ref'] is None and body['successor_owner_record_ref'] is None,
                'sealed transfer has invented successor')
        # Actual stop/pins/credit are deliberately verified by X/Engine, never this fixture.
    else:
        require(body['handoff_kind'] == 'successor_retained', 'unknown handoff')
        successor = body['confirmed_successor_full_ref']
        require(successor['freeze_generation'] > old_ref['freeze_generation'], 'successor is not newer')
        successor_expected = copy.deepcopy(expected)
        successor_expected['original_execution']['freeze_generation'] = successor['freeze_generation']
        successor_expected['original_execution']['state'] = successor['state']
        owner = strict_json(read_ref(body['successor_owner_record_ref'], 2097152)[1])
        retained_original({'snapshot_ref': owner['snapshot_ref'], 'owner_record_ref': body['successor_owner_record_ref'],
                           'storage_charge_ref': owner['storage_charge_ref']}, successor_expected, successor)
    return body

class OwnerFixture:
    def __init__(self, root, authority_root, namespace, global_budget=20 * 1024**3):
        self.root = Path(root).resolve(); self.root.mkdir(parents=True, exist_ok=True)
        self.authority_root = Path(authority_root).resolve(); self.namespace = namespace
        self.global_budget = global_budget

    def confirm(self, request_id, expected_scope, checkpoint_full_ref, original_binding):
        require(expected_scope['namespace'] == self.namespace, 'owner namespace mismatch')
        checkpoint_scope(checkpoint_full_ref, expected_scope)
        request = {'request_id': request_id, 'expected_scope': expected_scope, 'checkpoint_full_ref': checkpoint_full_ref,
                   'original_binding': original_binding}
        root = self.root / ('confirm-' + sha_bytes(canonical(request_id)))
        with (self.root / '.lock').open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if (root / 'result.json').exists():
                require(strict_json((root / 'request.json').read_bytes()) == request, 'confirmation ID conflict')
                result = strict_json((root / 'result.json').read_bytes())
                retained_original(result, expected_scope, checkpoint_full_ref)
                return result
            fact, raw = read_ref({'path': checkpoint_full_ref['path'], 'sha256': checkpoint_full_ref['sha256'],
                                  'bytes': checkpoint_full_ref['size']})
            entries, files, _ = archive_bytes(raw)
            session = session_original(files, original_binding, expected_scope)
            reserved = len(raw) + 2097152  # bounded owner records/manifests, conservatively charged
            charges = [strict_json(p.read_bytes()) for p in self.root.glob('confirm-*/charge.json')]
            physical = sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
            require(max(sum(c['reserved_bytes'] for c in charges), physical) + reserved <= self.global_budget,
                    'global owner storage reservation exhausted')
            root.mkdir(exist_ok=False); save(root / 'request.json', request)
            ref = original(root / 'snapshot', expected_scope, entries, files, raw, 'checkpoint')
            observed = snapshot(ref, expected_scope)
            require(observed['archive_fact']['root'] != fact['root'], 'copy did not establish independent inode')
            scope = {k: expected_scope[k] for k in SCOPE}
            charge = {'schema': 'lore-s-owner-fixture-charge/v1', 'scope': scope, 'snapshot_ref': ref,
                      'archive_fact': observed['archive_fact'], 'reserved_bytes': reserved,
                      'global_budget_bytes': self.global_budget, 'reserved_inodes': 16}
            save(root / 'charge.json', charge); charge_ref = file_fact(root / 'charge.json')[0]
            body = {'schema': 'lore-s-original-snapshot-owner/v1', 'id': root.name, 'confirmation_request_id': request_id,
                    'scope': scope, 'source': {'kind': 'checkpoint', 'original_checkpoint_full_ref': checkpoint_full_ref},
                    'snapshot_ref': ref, 'actual_archive_object': observed['archive_fact']['root'],
                    'original_session': session, 'storage_charge_ref': charge_ref, 'source_owner_record_ref': None,
                    'confirmed_at': datetime.now(timezone.utc).isoformat()}
            save(root / 'owner.json', body); owner_ref = file_fact(root / 'owner.json')[0]
            result = {'snapshot_ref': ref, 'owner_record_ref': owner_ref, 'storage_charge_ref': charge_ref}
            retained_original(result, expected_scope, checkpoint_full_ref)
            register(self.authority_root, 'snapshot', ref, expected_scope)
            register(self.authority_root, 'storage-charge', charge_ref, expected_scope)
            save(root / 'result.json', result)
            return result

    def receipt(self, receipt_id, old_fullref, retained, successor_fullref=None, successor_owner=None, sealed=False):
        owner = strict_json(read_ref(retained['owner_record_ref'], 2097152)[1])
        expected = {**owner['scope'], 'original_execution':
                    {**{k: old_fullref['source_binding'][k] for k in EXEC}, 'state': old_fullref['state']}}
        # Creation is trusted fixture work; external verification supplies original X expected independently.
        successor_owner_ref = successor_owner['owner_record_ref'] if successor_owner is not None and 'owner_record_ref' in successor_owner else successor_owner
        body = {'owner': 'S', 'receipt_id': receipt_id,
                **{k: expected[k] for k in ('namespace', 'session_id', 'session_generation')},
                'old_checkpoint_full_ref': old_fullref, 'retained_original_ref': retained['snapshot_ref'],
                'confirmed_successor_full_ref': successor_fullref, 'successor_owner_record_ref': successor_owner_ref,
                'handoff_kind': 'sealed_ownership_transfer' if sealed else 'successor_retained',
                'retained_owner_record_ref': retained['owner_record_ref'], 'storage_charge_ref': retained['storage_charge_ref']}
        path = self.root / ('receipt-' + sha_bytes(canonical(receipt_id)) + '.json')
        if path.exists(): require(strict_json(path.read_bytes()) == body, 'receipt ID conflict')
        else: save(path, body)
        ref = {**body, 'actual_owner_receipt_path_sha_bytes': file_fact(path)[0]}
        verify_receipt(ref, expected, old_fullref)
        register(self.authority_root, 'owner-receipt', ref, expected)
        return ref
