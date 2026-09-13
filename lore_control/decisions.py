"""Persist externally computed decisions before applying a local responsibility handoff."""
from .values import fail,encode,decode,same,identifier,fields,positive_int

class Decisions:
    def _decision_value(self,row):
        return {'id':row['id'],'parent_id':row['parent_id'],'source_ref':decode(row['source_ref_json']),'harness_ref':decode(row['harness_ref_json']),'body':decode(row['body_json']),'applied':bool(row['applied']),'wait_barriers':decode(row['wait_barriers_json'])}

    def _decision_body(self,parent,body):
        if type(body) is not dict or len(body)!=1 or not set(body)<={'successors','wait','stop_ref'}:fail('invalid','decision must contain exactly one handoff form')
        encode(body)
        if 'successors' in body:
            successors=body['successors']
            if type(successors) is not list or not successors:fail('invalid','a handoff must retain at least one successor')
            ids=[]
            for request in successors:
                self._validate_request(parent['principal'],request);ids.append(request['id'])
            if len(ids)!=len(set(ids)) or parent['id'] in ids:fail('invalid','successor identities must be distinct from parent')
        elif 'stop_ref' in body:self._reference(body['stop_ref'],'stop',{'parent_id':parent['id'],'source_ref':decode(parent['result_ref_json']),'harness_ref':decode(parent['payload_json']).get('harness_ref')})
        else:
            wait=body['wait']
            if type(wait) is not dict or not {'id','namespace','target','harness_ref','condition_ref','start_sequence','filters','refs'}<=set(wait) or set(wait)-{'id','namespace','target','harness_ref','condition_ref','start_sequence','filters','refs','release_refs'}:fail('invalid','incomplete static wait binding')
            identifier(wait['id']);positive_int(wait['start_sequence'])
            if wait['namespace']!=parent['namespace']:fail('denied','wait must retain parent namespace')
            if not same(wait['harness_ref'],decode(parent['payload_json']).get('harness_ref')):fail('conflict','wait must retain accepted harness')
            if type(wait['filters']) is not dict or type(wait['refs']) is not list or type(wait.get('release_refs',[])) is not list:fail('invalid','invalid static wait values')
            self._reference(wait['harness_ref'],'harness');self._reference(wait['condition_ref'],'condition')
            for ref in wait['refs']:self._reference(ref,'wait_ref')

    def accept_decision(self,parent_id,token,decision_id,source_ref,harness_ref,body):
        identifier(decision_id)
        with self._tx():
            parent=self._get_request(parent_id);self._token(parent,token)
            binding={'parent_id':parent_id,'source_ref':source_ref,'harness_ref':harness_ref,'body':body}
            prior=self.db.execute('SELECT * FROM decisions WHERE id=? OR parent_id=?',(decision_id,parent_id)).fetchone()
            if prior:
                previous=self._decision_value(prior)
                if prior['id']!=decision_id or not same({k:previous[k] for k in binding},binding):fail('conflict','accepted decision association cannot change')
                return previous
            if not same(source_ref,decode(parent['result_ref_json'])) or not same(harness_ref,decode(parent['payload_json']).get('harness_ref')):fail('conflict','decision must use original result and accepted harness')
            if parent['phase']!='decide':fail('stale','parent has no pending decision')
            self._reference(source_ref,'result');self._reference(harness_ref,'harness');self._decision_body(parent,body)
            barriers=self._freeze_wait_barriers(parent,body['wait']) if 'wait' in body else None
            self.db.execute('INSERT INTO decisions(id,parent_id,source_ref_json,harness_ref_json,body_json,wait_barriers_json) VALUES(?,?,?,?,?,?)',(decision_id,parent_id,encode(source_ref),encode(harness_ref),encode(body),encode(barriers) if barriers is not None else None))
            return self._decision_value(self.db.execute('SELECT * FROM decisions WHERE id=?',(decision_id,)).fetchone())

    def query_decision(self,id):
        with self._tx(False):
            row=self.db.execute('SELECT * FROM decisions WHERE id=?',(id,)).fetchone()
            if row is None:fail('not_found','decision not accepted')
            return self._decision_value(row)

    def apply_decision(self,parent_id,decision_id):
        with self._tx():
            parent=self._get_request(parent_id)
            row=self.db.execute('SELECT * FROM decisions WHERE id=?',(decision_id,)).fetchone()
            if row is None:fail('not_found','decision not accepted')
            if row['parent_id']!=parent_id:fail('conflict','decision belongs to another parent')
            if 'wait' in decode(row['body_json']):self._frozen_wait_barriers(row)
            if row['applied']:return self._decision_value(row)
            if parent['phase']!='decide':fail('stale','parent is not pending original decision')
            self._reference(decode(row['source_ref_json']),'result');self._reference(decode(row['harness_ref_json']),'harness')
            body=decode(row['body_json']);self._decision_body(parent,body)
            if 'wait' in body:self._require_wait_releases(row)
            self.checkpoint('before_handoff_commit',{'id':parent_id,'decision_id':decision_id})
            phase='settled'
            if 'successors' in body:
                for request in body['successors']:self._accept(parent['principal'],request)
            elif 'wait' in body:
                wait=body['wait']
                if self.db.execute('SELECT 1 FROM waits WHERE id=?',(wait['id'],)).fetchone():fail('conflict','wait identity already accepted')
                self.db.execute('INSERT INTO waits(id,parent_id,namespace,binding_json) VALUES(?,?,?,?)',(wait['id'],parent_id,wait['namespace'],encode(wait)))
                phase='waiting'
            self.db.execute('UPDATE decisions SET applied=1 WHERE id=?',(decision_id,))
            self.db.execute('UPDATE requests SET phase=? WHERE id=?',(phase,parent_id))
            value=self._decision_value(self.db.execute('SELECT * FROM decisions WHERE id=?',(decision_id,)).fetchone())
        self.checkpoint('after_handoff_commit_before_reply',{'id':parent_id,'decision_id':decision_id})
        return value

    def waits(self,namespace=None):
        with self._tx(False):
            rows=self.db.execute('SELECT * FROM waits WHERE matched=0'+(' AND namespace=?' if namespace is not None else ''),(namespace,) if namespace is not None else ())
            return [decode(row['binding_json'])|{'parent_id':row['parent_id']} for row in rows]

    def satisfy_wait(self,wait_id,event_ref,successor_request,expected_condition_ref):
        with self._tx():
            row=self.db.execute('SELECT * FROM waits WHERE id=?',(wait_id,)).fetchone()
            if row is None:fail('not_found','static wait not accepted')
            wait=decode(row['binding_json'])
            if not same(wait['condition_ref'],expected_condition_ref):fail('conflict','match used a different original condition')
            if row['matched']:
                if not same(decode(row['event_ref_json']),event_ref) or not same(decode(row['successor_json']),successor_request):fail('conflict','accepted matching handoff cannot change')
                return self._request_value(self._get_request(successor_request['id']))
            decision=self.db.execute('SELECT * FROM decisions WHERE parent_id=?',(row['parent_id'],)).fetchone()
            if decision is None:fail('reference_invalid','original wait decision is missing')
            self._frozen_wait_barriers(decision)
            self._reference(expected_condition_ref,'condition');self._reference(event_ref,'event',{'namespace':wait['namespace']})
            parent=self._get_request(row['parent_id'])
            if parent['phase']!='waiting':fail('busy','wait has not confirmed resource release')
            if successor_request.get('id')==parent['id']:fail('invalid','wait successor must have a new identity')
            result=self._accept(parent['principal'],successor_request)
            self.db.execute('UPDATE waits SET matched=1,event_ref_json=?,successor_json=? WHERE id=?',(encode(event_ref),encode(successor_request),wait_id))
            self.db.execute("UPDATE requests SET phase='settled' WHERE id=?",(parent['id'],))
            return result
