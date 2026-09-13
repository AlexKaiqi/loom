"""Registered directory identities and explicit authorized binding changes."""
from pathlib import Path
from .values import fail,encode,decode,same,identifier,positive_int

class Registration:
    def _resource(self,resource_id):
        row=self.db.execute('SELECT * FROM resources WHERE id=? AND active=1',(resource_id,)).fetchone()
        if row is None:fail('not_found','resource not registered')
        return row

    def _resource_value(self,row):
        result={k:row[k] for k in ['id','namespace','kind','path','dev','ino','revision']}
        result.update(harness_ref=decode(row['harness_ref_json']),grants=decode(row['grants_json']))
        return result

    def _directory(self,path,code='stale'):
        if type(path) is not str or not Path(path).is_absolute():fail('invalid','absolute directory path required')
        try:
            p=Path(path).resolve(strict=True)
            if not p.is_dir():fail(code,'not a directory')
            st=p.stat()
            return {'path':str(p),'dev':st.st_dev,'ino':st.st_ino}
        except OSError:fail(code,'registered directory unavailable')

    def _resource_access(self,row,principal,access):
        self._authorize(principal,row['namespace'])
        if access not in ('read','write'):fail('invalid','unknown access')
        if access not in decode(row['grants_json']).get(principal,[]):fail('denied','resource access not granted')

    def _current_resource(self,row):
        for pending in self.db.execute('SELECT binding_json FROM installations WHERE installation_ref_json IS NULL'):
            if decode(pending[0])['resource_id']==row['id']:fail('pending_reconcile','original installation must be reconciled')
        now=self._directory(row['path'])
        if (now['path'],now['dev'],now['ino'])!=(row['path'],row['dev'],row['ino']):fail('stale','registered directory identity changed')

    def register(self,principal,request_id,resource_id,namespace,kind,path,harness_ref,grants):
        self._authorize(principal,namespace,{'admin'});identifier(resource_id);identifier(namespace)
        if kind not in ('surface','workspace','parent'):fail('invalid','unknown registration kind')
        if type(grants) is not dict or any(type(v) is not list or any(x not in ('read','write') for x in v) for v in grants.values()):fail('invalid','invalid grants')
        binding=dict(op='register',principal=principal,resource_id=resource_id,namespace=namespace,kind=kind,path=path,harness_ref=harness_ref,grants=grants)
        encode(binding)
        with self._tx():
            prior=self._operation_previous(request_id,binding)
            if prior is not None:return prior
            if self.db.execute('SELECT 1 FROM resources WHERE id=?',(resource_id,)).fetchone():fail('conflict','resource identity already used')
            root=self._directory(path,'not_found');self._reference(harness_ref,'harness')
            self.db.execute('INSERT INTO resources(id,namespace,kind,path,dev,ino,revision,harness_ref_json,grants_json) VALUES(?,?,?,?,?,?,1,?,?)',(resource_id,namespace,kind,root['path'],root['dev'],root['ino'],encode(harness_ref),encode(grants)))
            return self._operation_saved(request_id,binding,self._resource_value(self._resource(resource_id)))

    def _resolve_registered(self,principal,namespace,target,access):
        self._authorize(principal,namespace)
        if type(target) is not str:fail('invalid','target must be an ID or absolute path')
        row=self.db.execute('SELECT * FROM resources WHERE id=? AND namespace=? AND active=1',(target,namespace)).fetchone()
        if row is None:
            if not Path(target).is_absolute():fail('not_found','resource not registered')
            position=Path(target).resolve()
            matches=[]
            for item in self.db.execute('SELECT * FROM resources WHERE namespace=? AND active=1',(namespace,)):
                root=Path(item['path'])
                if position==root or root in position.parents:matches.append(item)
            if not matches:fail('not_found','no registered containing resource')
            # An explicit resource ID disambiguates; paths never choose a nearest root.
            if len(matches)>1:fail('ambiguous','overlapping registered roots')
            row=matches[0]
        self._resource_access(row,principal,access);self._current_resource(row)
        return row

    def resolve(self,principal,namespace,target,access):
        with self._tx(False):
            return self._resource_value(self._resolve_registered(principal,namespace,target,access))

    def _change_registration(self,op,principal,request_id,resource_id,expected_revision,**change):
        identifier(request_id);positive_int(expected_revision)
        binding=dict(op=op,principal=principal,resource_id=resource_id,expected_revision=expected_revision,**change)
        with self._tx():
            row=self.db.execute('SELECT * FROM resources WHERE id=?',(resource_id,)).fetchone()
            if row is None:fail('not_found','resource was never registered')
            self._authorize(principal,row['namespace'],{'admin'})
            prior=self._operation_previous(request_id,binding)
            if prior is not None:return prior
            if not row['active']:fail('not_found','resource is no longer registered')
            if row['revision']!=expected_revision:fail('stale','registration revision changed')
            if op=='relocate':
                now=self._directory(change['new_path'])
                if (now['dev'],now['ino'])!=(row['dev'],row['ino']):fail('stale','relocation must retain original object')
                self.db.execute('UPDATE resources SET path=?,revision=revision+1 WHERE id=?',(now['path'],resource_id))
            else:
                self._current_resource(row)
                if op=='rebind':
                    self._reference(change['harness_ref'],'harness')
                    self.db.execute('UPDATE resources SET harness_ref_json=?,revision=revision+1 WHERE id=?',(encode(change['harness_ref']),resource_id))
                else:self.db.execute('UPDATE resources SET active=0,revision=revision+1 WHERE id=?',(resource_id,))
            updated=self.db.execute('SELECT * FROM resources WHERE id=?',(resource_id,)).fetchone()
            return self._operation_saved(request_id,binding,self._resource_value(updated))

    def rebind(self,principal,request_id,resource_id,expected_revision,harness_ref):
        return self._change_registration('rebind',principal,request_id,resource_id,expected_revision,harness_ref=harness_ref)

    def relocate(self,principal,request_id,resource_id,new_path,expected_revision):
        return self._change_registration('relocate',principal,request_id,resource_id,expected_revision,new_path=new_path)

    def unregister(self,principal,request_id,resource_id,expected_revision):
        return self._change_registration('unregister',principal,request_id,resource_id,expected_revision)
