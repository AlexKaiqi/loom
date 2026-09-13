"""Accepted responsibility, fair leases and saved results; no strategy evaluation."""
import math,uuid
from .values import ControlError,fail,encode,decode,same,identifier,fields

DELIVERY_KINDS={'event':'E','execution':'X','provider_transport':'provider'}

class Responsibilities:
    def _request_binding(self,row):
        return {k:row[k] for k in ['principal','id','namespace','kind']}|{'payload':decode(row['payload_json'])}

    def _validate_request(self,principal,request):
        fields(request,{'id','namespace','kind','payload'},'request')
        self._authorize(principal,request['namespace'],{'submit','admin','runtime'})
        identifier(request['id']);identifier(request['namespace']);identifier(request['kind'])
        if type(request['payload']) is not dict:fail('invalid','request payload must be an object')
        binding={'principal':principal,**request};raw=encode(binding)
        if len(raw.encode('utf-8'))>self.request_limit_bytes:fail('invalid','request byte budget exceeded')
        if set(request['payload'])&{'principal','user','origin'}:fail('denied','payload cannot supply trusted origin')
        return raw

    def _accept(self,principal,request):
        raw=self._validate_request(principal,request)
        row=self.db.execute('SELECT * FROM requests WHERE id=?',(request['id'],)).fetchone()
        if row:
            if raw!=encode(self._request_binding(row)):fail('conflict','accepted identity has a different complete binding')
            return self._request_value(row)
        payload=request['payload'];kind=request['kind'];ns=request['namespace']
        if kind=='restore_plan':self._validate_restore(principal,request)
        else:
            if payload.get('harness_ref') is not None:self._reference(payload['harness_ref'],'harness')
            if kind=='invocation' and 'resource_id' in payload:
                resource=self._resource(payload['resource_id']);self._resource_access(resource,principal,'write');self._current_resource(resource)
                if resource['namespace']!=ns:fail('denied','invocation resource belongs to another namespace')
                if payload.get('resource_revision')!=resource['revision'] or not same(payload.get('harness_ref'),decode(resource['harness_ref_json'])):fail('stale','invocation must bind current registration and harness')
            if kind=='invocation' and 'input_binding' in payload:self._validate_selector(principal,ns,payload['input_binding'])
            if 'retry_of' in payload:self._validate_retry(principal,request)
        phase='accepted_delivery' if kind in DELIVERY_KINDS else 'accepted'
        self.db.execute('INSERT INTO requests(id,principal,namespace,kind,payload_json,phase) VALUES(?,?,?,?,?,?)',(request['id'],principal,ns,kind,encode(payload),phase))
        self.db.execute('INSERT OR IGNORE INTO namespace_turns VALUES(?,0)',(ns,))
        if kind=='restore_plan':self._reserve_restore(request)
        return self._request_value(self._get_request(request['id']))

    def accept(self,principal,request):
        with self._tx():value=self._accept(principal,request)
        self.checkpoint('after_commit_before_reply',value)
        return value

    def query(self,principal,id):
        identifier(id)
        with self._tx(False):
            row=self._get_request(id);self._authorize(principal,row['namespace'])
            return self._request_value(row)

    def pending(self):
        with self._tx(False):return [self._request_value(r) for r in self.db.execute("SELECT * FROM requests WHERE phase NOT IN ('settled','confirmed') ORDER BY seq")]

    def _token(self,row,token):
        if type(token) is not str or not token or row['token']!=token:fail('stale','claim token no longer owns responsibility')

    def claim(self,worker_id,now):
        identifier(worker_id)
        if type(now) not in (int,float) or not math.isfinite(now):fail('invalid','finite claim time required')
        with self._tx():
            rows=self.db.execute("SELECT r.* FROM requests r JOIN namespace_turns n ON n.namespace=r.namespace WHERE r.phase IN ('accepted','issued','decide') AND (r.token IS NULL OR r.lease_until<=?) ORDER BY n.turn,r.seq",(now,)).fetchall()
            for row in rows:
                if row['kind'] in DELIVERY_KINDS or row['kind']=='restore_plan':continue
                if not self._input_ready(row):continue
                mode='execute' if row['phase']=='accepted' else ('decide' if row['phase']=='decide' else 'reconcile')
                phase='issued' if row['phase']=='accepted' else row['phase'];token=uuid.uuid4().hex
                self.db.execute('UPDATE requests SET phase=?,token=?,worker=?,lease_until=? WHERE id=?',(phase,token,worker_id,now+self.lease_seconds,row['id']))
                self.db.execute("UPDATE meta SET value=value+1 WHERE key='claim_clock'")
                self.db.execute("UPDATE namespace_turns SET turn=(SELECT value FROM meta WHERE key='claim_clock') WHERE namespace=?",(row['namespace'],))
                return self._request_value(self._get_request(row['id']))|{'token':token,'mode':mode}
        return None

    def renew(self,id,token,now):
        if type(now) not in (int,float) or not math.isfinite(now):fail('invalid','finite renewal time required')
        with self._tx():
            row=self._get_request(id);self._token(row,token)
            if row['phase'] not in ('issued','decide'):fail('stale','responsibility no longer leased')
            self.db.execute('UPDATE requests SET lease_until=? WHERE id=?',(now+self.lease_seconds,id))
            return {'id':id,'token':token,'lease_until':now+self.lease_seconds}

    def save_result(self,id,token,result_ref):
        with self._tx():
            row=self._get_request(id);self._token(row,token);self._reference(result_ref,'result')
            if row['kind'] in DELIVERY_KINDS or row['kind']=='restore_plan':fail('invalid','not an ordinary strategy responsibility')
            if row['result_ref_json'] is not None:
                if not same(decode(row['result_ref_json']),result_ref):fail('conflict','saved original result cannot change')
                return self._request_value(row)
            if row['phase']!='issued':fail('stale','responsibility cannot accept a new result')
            self.db.execute("UPDATE requests SET result_ref_json=?,phase='decide' WHERE id=?",(encode(result_ref),id))
            return self._request_value(self._get_request(id))

    def pause(self,id,token,reason,query_ref):
        if type(reason) is not str or not reason:fail('invalid','pause reason required')
        encode(query_ref)
        with self._tx():
            row=self._get_request(id);self._token(row,token)
            if row['phase'] not in ('issued','decide','paused'):fail('stale','responsibility no longer active')
            if row['phase']=='paused' and (row['reason']!=reason or not same(decode(row['query_ref_json']),query_ref)):fail('conflict','original unresolved query cannot change')
            self.db.execute("UPDATE requests SET phase='paused',reason=?,query_ref_json=? WHERE id=?",(reason,encode(query_ref),id))
            return self._request_value(self._get_request(id))
