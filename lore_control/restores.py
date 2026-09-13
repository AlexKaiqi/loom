"""RestorePlan is an immutable list of selected domains and original installation receipts."""
from .values import fail,encode,decode,same,identifier,fields,positive_int

DOMAINS=('surface','workspace')

class Restores:
    def _validate_restore(self,principal,request):
        self._authorize(principal,request['namespace'],{'admin','runtime'})
        plan=request['payload']
        fields(plan,{'schema','domains','session','event_cursor','pending_refs','effect_refs','harness_ref','environment_ref'},'restore plan')
        if plan['schema']!='lore-restore-plan/v1':fail('invalid','unsupported restore plan schema')
        fields(plan['domains'],set(DOMAINS),'restore domains')
        resources=[];install_ids=[];executions=[];generations=[]
        for domain in DOMAINS:
            entry=plan['domains'][domain]
            fields(entry,{'action','resource_id','binding_revision','base_ref','version_ref','installation'},'restore domain')
            if entry['action'] not in ('restore','keep'):fail('invalid','unknown restore action')
            identifier(entry['resource_id']);positive_int(entry['binding_revision']);resources.append(entry['resource_id'])
            resource=self._resource(entry['resource_id']);self._resource_access(resource,principal,'write' if entry['action']=='restore' else 'read');self._current_resource(resource)
            if resource['namespace']!=request['namespace']:fail('denied','restore resources must belong to original namespace')
            if resource['kind']!=domain:fail('invalid','restore resource belongs to a different domain')
            if resource['revision']!=entry['binding_revision']:fail('stale','restore registration revision changed')
            if entry['action']=='keep':
                if entry['installation'] is not None or not same(entry['base_ref'],entry['version_ref']):fail('invalid','kept domain must retain exact original base without installation')
            else:
                install=entry['installation'];fields(install,{'request_id','execution_id','generation'},'restore installation')
                for key in install:identifier(install[key])
                install_ids.append(install['request_id']);executions.append(install['execution_id']);generations.append(install['generation'])
            for key in ('base_ref','version_ref'):self._reference(entry[key],'restore_version',{'resource_id':entry['resource_id'],'domain':domain})
        if len(set(resources))!=2 or not install_ids or any(len(v)!=len(set(v)) for v in (install_ids,executions,generations)):fail('invalid','restore domains and installation identities must be distinct')
        # Validate both domain declarations before cross-plan identity collisions.
        for install_id in install_ids:
            if self.db.execute('SELECT 1 FROM restore_installs WHERE request_id=?',(install_id,)).fetchone() or self.db.execute('SELECT 1 FROM installations WHERE request_id=?',(install_id,)).fetchone():fail('conflict','installation identity already belongs to accepted intent')
        session=plan['session'];fields(session,{'session_ref','operation_id','boundary','source_result_ref'},'session continuation')
        identifier(session['operation_id'])
        if type(session['boundary']) is not str or not session['boundary']:fail('invalid','explicit continuation boundary required')
        self._reference(session['session_ref'],'restore_session',{k:session[k] for k in ['operation_id','boundary','source_result_ref']})
        cursor=plan['event_cursor'];fields(cursor,{'namespace','start_sequence','source_ref'},'restore event cursor');positive_int(cursor['start_sequence'])
        if cursor['namespace']!=request['namespace']:fail('denied','event cursor namespace differs from plan')
        self._reference(cursor['source_ref'],'restore_events',{k:cursor[k] for k in ['namespace','start_sequence']})
        if type(plan['pending_refs']) is not list or type(plan['effect_refs']) is not list:fail('invalid','restore references must be explicit lists')
        pending=[]
        for ref in plan['pending_refs']:
            fields(ref,{'owner','id'},'pending responsibility')
            if ref['owner']!='R':fail('invalid','pending responsibility owner must be R')
            identifier(ref['id']);old=self._get_request(ref['id']);self._authorize(principal,old['namespace'])
            if old['namespace']!=request['namespace']:fail('denied','pending responsibility namespace differs')
            pending.append(ref['id'])
        if len(pending)!=len(set(pending)):fail('invalid','pending identities repeated')
        for ref in plan['effect_refs']:self._reference(ref,'restore_effect',{'namespace':request['namespace']})
        self._reference(plan['harness_ref'],'harness');self._reference(plan['environment_ref'],'environment')

    def _reserve_restore(self,request):
        for domain in DOMAINS:
            entry=request['payload']['domains'][domain]
            if entry['action']=='restore':self.db.execute('INSERT INTO restore_installs VALUES(?,?,?)',(entry['installation']['request_id'],request['id'],domain))

    def _restore_progress(self,row):
        plan=decode(row['payload_json']);value={'installations':{},'remaining_install_ids':[],'kept':{}}
        for domain in DOMAINS:
            entry=plan['domains'][domain]
            if entry['action']=='keep':value['kept'][domain]=entry['version_ref'];continue
            id=entry['installation']['request_id']
            installed=self.db.execute('SELECT installation_ref_json FROM installations WHERE request_id=? AND restore_plan_id=?',(id,row['id'])).fetchone()
            if installed and installed[0] is not None:value['installations'][domain]=decode(installed[0])
            else:value['remaining_install_ids'].append(id)
        return value

    def _restore_install_expected(self,principal,request_id,resource_id,execution_id,expected_revision,base_ref,restore_plan_id):
        reserved=self.db.execute('SELECT * FROM restore_installs WHERE request_id=?',(request_id,)).fetchone()
        if restore_plan_id is None:
            if reserved:fail('conflict','installation must retain accepted restore plan association')
            return None
        planrow=self._get_request(restore_plan_id)
        if planrow['kind']!='restore_plan':fail('invalid','request is not a restore plan')
        self._authorize(principal,planrow['namespace'],{'runtime','admin'})
        plan=decode(planrow['payload_json'])
        for domain in DOMAINS:
            entry=plan['domains'][domain]
            if entry['resource_id']!=resource_id:continue
            if entry['action']=='keep':fail('invalid','kept domain cannot be installed')
            install=entry['installation']
            if not reserved or reserved['plan_id']!=restore_plan_id or install['request_id']!=request_id or install['execution_id']!=execution_id or entry['binding_revision']!=expected_revision or not same(entry['base_ref'],base_ref):fail('conflict','installation differs from original restore entry')
            return {'restore_plan_id':restore_plan_id,'request_id':request_id,'resource_id':resource_id,'domain':domain,'execution_id':execution_id,'generation':install['generation'],'base_ref':entry['base_ref'],'version_ref':entry['version_ref']}
        fail('conflict','resource not selected in original restore plan')
