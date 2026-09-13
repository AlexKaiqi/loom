"""Trusted test-side X original receipt and real F version handoff; no expected output."""
import copy
import json
from pathlib import Path
from f_peer import canonical, digest, file_fact, identity, require, save


def complete_tool(x, plans, plan, original, peer):
    request, authority = plan['request'], plan['authority']
    eid = request['execution_id']
    accepted = x.execute(request, authority)
    exited = x.await_exit(eid, authority, timeout=20)
    require(exited['result']['output_state'] == 'COMPLETE', 'original tool output unresolved')
    checkpoint = x.checkpoint(eid, authority, 's-tool-final', 'ordinary_tool_result')
    cp = checkpoint['artifacts']['checkpoint']
    stopped = x.seal(eid, authority, cp)
    # The serialized payload is exactly the original X response, with no fixture fields added.
    receipt_path = plans.root / ('x-original-receipt-'+digest(eid.encode())+'.json')
    save(receipt_path, stopped)
    receipt = file_fact(receipt_path)
    ref = dict(owner='X', execution_id=eid, object_generation=stopped['binding']['object_generation'],
               request_digest=stopped['binding']['request_digest'], original_receipt=receipt)
    raw = x.journal.read(cp, 8388608)
    view = plan['F']
    source = Path(view['materialized']['path'])
    version = view['bundle']['version_ref']
    grant = dict(owner='trusted-S-validation', authority=peer.authority, execution_ref=ref)
    binding = dict(resource_id=version['resource_id'], domain=version['domain'], path=str(source),
                   root=identity(source), revision=1, authorization=grant)
    source_ref = dict(owner='trusted-S-original-X-transport', original_execution_ref=ref,
                      archive_ref=cp, stopped_ref=stopped['artifacts']['stopped'])
    rid = 'tool-import-'+digest(eid.encode())
    context = dict(schema='lore-f-authority-context/v1', operation='import_archive', request_id=rid,
                   binding=binding, actual_root=binding['root'], profile='host-v1', base_ref=version,
                   source_ref=source_ref, archive=dict(path=cp['path'], bytes=len(raw), sha256=digest(raw)))
    # Authorization is issued only after original X reference/bytes and physical stop are known.
    actual = x.engine.inspect(stopped['binding']['container_id'])
    require(actual is not None and actual['State']['Running'] is False, 'original tool still runs')
    peer.allow('authorization', 'import_archive', grant, context)
    peer.allow('reference', 'source', source_ref, context)
    bundle = peer.store.import_archive(rid, binding, cp['path'], source_ref, version, 'host-v1')
    parent = peer.area('tool-output'); target = parent / 'output'
    context = dict(schema='lore-f-authority-context/v1', operation='materialize', request_id='read-'+rid,
                   version_ref=bundle['version_ref'], target_path=str(target),
                   target_parent=dict(path=str(parent), root=identity(parent)), profile='host-v1')
    peer.allow('authorization', 'materialize', grant, context)
    materialized = peer.store.materialize('read-'+rid, bundle['version_ref'], str(target), grant)
    output_view = dict(bundle=bundle, materialized=materialized)
    before = json.loads(Path(view['bundle']['manifest_path']).read_bytes())['tree']['entries']
    after = json.loads(Path(bundle['manifest_path']).read_bytes())['tree']['entries']
    files = []
    for name, entry in after.items():
        if entry['kind'] == 'file' and entry.get('sha256') != before.get(name, {}).get('sha256'):
            full, fact = peer.original_file(output_view, name)
            files.append(dict(target=original['target'], full_ref=full, file_ref=fact))
    peer.index['execution_outputs'][digest(canonical(ref))] = dict(original_execution_ref=ref,
        original_receipt_file=receipt, original_receipt=stopped, files=files,
        original_F_view=output_view, original_X_accepted=accepted)
    save(peer.index_path, peer.index)
    released = x.release(eid, authority)
    save(plans.root / ('x-original-release-'+digest(eid.encode())+'.json'), released)
    return dict(result_ref=ref, stdout_ref=exited['artifacts']['stdout'])
