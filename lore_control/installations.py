"""Durable install intentions and F-authoritative layout confirmation; never exchange files."""
from .values import fail,encode,decode,same,identifier,positive_int

class Installations:
    def _root_reference(self,root):
        if type(root) is not dict or not {'path','dev','ino'}<=set(root):fail('reference_invalid','missing actual directory object')
        try:actual=self._directory(root['path'],'reference_invalid')
        except (TypeError,ValueError) as exc:
            if getattr(exc,'code',None):raise
            fail('reference_invalid','invalid root record')
        if not same(actual,{k:root[k] for k in actual}):fail('reference_invalid','actual directory identity differs')
        return actual

    def prepare_install(self,principal,request_id,resource_id,execution_id,expected_revision,base_ref,staged_ref,restore_plan_id=None):
        identifier(request_id);identifier(execution_id);positive_int(expected_revision)
        call=dict(principal=principal,request_id=request_id,resource_id=resource_id,execution_id=execution_id,expected_revision=expected_revision,base_ref=base_ref,staged_ref=staged_ref,restore_plan_id=restore_plan_id)
        encode(call)
        with self._tx():
            resource=self._resource(resource_id);self._authorize(principal,resource['namespace'],{'runtime','admin'});self._resource_access(resource,principal,'write')
            expected=self._restore_install_expected(principal,request_id,resource_id,execution_id,expected_revision,base_ref,restore_plan_id)
            prior=self.db.execute('SELECT * FROM installations WHERE request_id=?',(request_id,)).fetchone()
            if prior:
                old=decode(prior['binding_json'])
                if not same({k:old[k] for k in call},call):fail('conflict','installation identity has a different immutable intent')
                return old
            self._current_resource(resource)
            if resource['revision']!=expected_revision:fail('stale','installation registration revision changed')
            holder=self.db.execute('SELECT * FROM holders WHERE resource_id=?',(resource_id,)).fetchone()
            if holder is None or holder['execution_id']!=execution_id or not same(decode(holder['base_ref_json']),base_ref):fail('busy','installation must retain original holder and base')
            self._reference(staged_ref,'staged',expected if expected is not None else {'resource_id':resource_id,'execution_id':execution_id,'base_ref':base_ref})
            if type(staged_ref) is not dict:fail('reference_invalid','staged reference required')
            stage=self._root_reference(staged_ref.get('root'))
            if (stage['dev'],stage['ino'])==(resource['dev'],resource['ino']):fail('reference_invalid','staging must use a distinct actual directory')
            if expected:
                self._reference(staged_ref.get('stopped_ref'),'stopped',{k:expected[k] for k in ['resource_id','execution_id','generation','base_ref']})
            intent=call|{'old_root':{k:resource[k] for k in ['path','dev','ino']},'staged_root':stage,'expected':expected}
            self.db.execute('INSERT INTO installations(request_id,restore_plan_id,binding_json) VALUES(?,?,?)',(request_id,restore_plan_id,encode(intent)))
            return decode(encode(intent))

    def confirm_install(self,request_id,installation_ref):
        with self._tx():
            row=self.db.execute('SELECT * FROM installations WHERE request_id=?',(request_id,)).fetchone()
            if row is None:fail('not_found','installation intent not accepted')
            if row['installation_ref_json'] is not None:
                if not same(decode(row['installation_ref_json']),installation_ref):fail('conflict','confirmed installation receipt cannot change')
                return decode(row['installation_ref_json'])
            intent=decode(row['binding_json']);expected=intent['expected'] or {k:intent[k] for k in ['request_id','resource_id','execution_id','base_ref']}
            if intent['expected']:expected=expected|{'stopped_ref':intent['staged_ref']['stopped_ref']}
            else:expected=expected|{'version_ref':intent['staged_ref']}
            self._reference(installation_ref,'installation',expected)
            if installation_ref.get('status') not in ('installed_pending_confirmation','confirmed'):fail('reference_invalid','receipt does not establish actual installation')
            current=self._root_reference(installation_ref.get('current'));retired=self._root_reference(installation_ref.get('retired'))
            old=intent['old_root'];stage=intent['staged_root']
            if current['path']!=old['path'] or (current['dev'],current['ino'])!=(stage['dev'],stage['ino']) or (retired['dev'],retired['ino'])!=(old['dev'],old['ino']):fail('reference_invalid','actual current and retired layout differs from original intent')
            resource=self._resource(intent['resource_id'])
            if resource['revision']!=intent['expected_revision'] or (resource['dev'],resource['ino'])!=(old['dev'],old['ino']):fail('stale','registration changed during installation')
            self.db.execute('UPDATE resources SET dev=?,ino=?,revision=revision+1 WHERE id=?',(current['dev'],current['ino'],intent['resource_id']))
            self.db.execute('UPDATE installations SET installation_ref_json=? WHERE request_id=?',(encode(installation_ref),request_id))
            if row['restore_plan_id']:
                plan=self._get_request(row['restore_plan_id'])
                if not self._restore_progress(plan)['remaining_install_ids']:self.db.execute("UPDATE requests SET phase='confirmed' WHERE id=?",(plan['id'],))
            return decode(encode(installation_ref))
