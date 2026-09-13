"""Original authorized wait dependencies, separate from the external policy body."""
from .values import ControlError,fail,encode,decode,same

class WaitBarriers:
    def _wait_resource_ids(self,parent,wait):
        payload=decode(parent['payload_json']);targets=[wait['target']]
        if 'resource_id' in payload:targets.append(payload['resource_id'])
        if 'input_binding' in payload:
            selector=payload['input_binding']
            if type(selector) is not dict or type(selector.get('execution_targets')) is not list:fail('invalid','invalid original execution targets')
            for target in selector['execution_targets']:
                if type(target) is not dict or type(target.get('resource_id')) is not str:fail('invalid','execution target needs registered resource_id')
                targets.append(target['resource_id'])
        # Reuse the actual namespace/grant/path-alias resolver inside this transaction.
        return sorted({self._resolve_registered(parent['principal'],parent['namespace'],target,'write')['id'] for target in targets})

    def _holder_tuple(self,row):
        return {'resource_id':row['resource_id'],'execution_id':row['execution_id'],'base_ref':decode(row['base_ref_json'])}

    def _release_tuple(self,row):
        if row['holder_json'] is None:return None
        value=decode(row['holder_json'])
        if type(value) is not dict or set(value)!={'resource_id','execution_id','base_ref'} or value['resource_id']!=row['resource_id'] or value['execution_id']!=row['execution_id']:
            fail('reference_invalid','release original holder association is corrupt')
        return value

    def _freeze_wait_barriers(self,parent,wait):
        resources=self._wait_resource_ids(parent,wait);barriers={};candidates=[]
        for resource_id in resources:
            holder=self.db.execute('SELECT * FROM holders WHERE resource_id=?',(resource_id,)).fetchone()
            if holder is not None:
                original=self._holder_tuple(holder);barriers[encode(original)]=original;candidates.append((original,None))
            for released in self.db.execute('SELECT * FROM releases WHERE resource_id=?',(resource_id,)):
                original=self._release_tuple(released)
                if original is not None:candidates.append((original,decode(released['binding_json'])))
        for ref in wait.get('release_refs',[]):
            found=None
            for original,released in candidates:
                # A historical reference must be the one actually accepted by release.
                if released is not None and not same(released.get('stopped_ref'),ref):continue
                try:self._reference(ref,'stopped',original)
                except ControlError as error:
                    if error.code!='reference_invalid':raise
                else:
                    found=original;break
            if found is None:fail('reference_invalid','stop has no authorized original holder/release association')
            barriers[encode(found)]=found
        return sorted(barriers.values(),key=lambda value:(value['resource_id'],value['execution_id'],encode(value['base_ref'])))

    def _frozen_wait_barriers(self,decision):
        if decision['wait_barriers_json'] is None:fail('reference_invalid','legacy wait holder dependencies are unknown')
        barriers=decode(decision['wait_barriers_json'])
        if type(barriers) is not list:fail('reference_invalid','invalid frozen wait dependencies')
        for item in barriers:
            if type(item) is not dict or set(item)!={'resource_id','execution_id','base_ref'}:fail('reference_invalid','incomplete frozen wait tuple')
        return barriers

    def _require_wait_releases(self,decision):
        barriers=self._frozen_wait_barriers(decision);stops=[]
        for original in barriers:
            row=self.db.execute('SELECT * FROM releases WHERE resource_id=? AND execution_id=?',(original['resource_id'],original['execution_id'])).fetchone()
            if row is None:fail('busy','original wait holder has not completed release')
            released=self._release_tuple(row)
            if released is None:fail('reference_invalid','legacy release holder association is unknown')
            if not same(original,released):fail('busy','no release for the original wait holder tuple')
            binding=decode(row['binding_json'])
            self._reference(binding.get('stopped_ref'),'stopped',original)
            self._reference(binding.get('published_ref'),'published',original)
            stops.append(binding['stopped_ref'])
        wait=decode(decision['body_json'])['wait']
        for ref in wait.get('release_refs',[]):
            if not any(same(ref,stop) for stop in stops):fail('reference_invalid','original wait stop differs from release ledger')
