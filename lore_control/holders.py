"""Exclusive resource responsibility; leases never substitute for actual stop evidence."""
from .values import fail,encode,decode,same,identifier

class Holders:
    def acquire(self,resource_id,execution_id,base_ref):
        identifier(execution_id);encode(base_ref)
        with self._tx():
            resource=self._resource(resource_id);self._current_resource(resource)
            prior=self.db.execute('SELECT * FROM holders WHERE resource_id=?',(resource_id,)).fetchone()
            if prior:
                if prior['execution_id']!=execution_id or not same(decode(prior['base_ref_json']),base_ref):fail('busy','original writer responsibility remains held')
            else:
                self._reference(base_ref,'base',{'resource_id':resource_id})
                self.db.execute('INSERT INTO holders VALUES(?,?,?)',(resource_id,execution_id,encode(base_ref)))
            return {'resource_id':resource_id,'execution_id':execution_id,'base_ref':decode(encode(base_ref))}

    def release(self,resource_id,execution_id,stopped_ref,published_ref):
        with self._tx():
            holder=self.db.execute('SELECT * FROM holders WHERE resource_id=?',(resource_id,)).fetchone()
            binding={'stopped_ref':stopped_ref,'published_ref':published_ref}
            if holder is None:
                released=self.db.execute('SELECT binding_json FROM releases WHERE resource_id=? AND execution_id=?',(resource_id,execution_id)).fetchone()
                if released and same(decode(released[0]),binding):return {'resource_id':resource_id,'execution_id':execution_id,'released':True}
                fail('stale','writer responsibility is no longer held')
            if holder['execution_id']!=execution_id:fail('stale','release refers to a different writer')
            expected={'resource_id':resource_id,'execution_id':execution_id,'base_ref':decode(holder['base_ref_json'])}
            self._reference(stopped_ref,'stopped',expected);self._reference(published_ref,'published',expected)
            self.db.execute('INSERT OR REPLACE INTO releases(resource_id,execution_id,binding_json,holder_json) VALUES(?,?,?,?)',(resource_id,execution_id,encode(binding),encode(expected)))
            self.db.execute('DELETE FROM holders WHERE resource_id=?',(resource_id,))
            return {'resource_id':resource_id,'execution_id':execution_id,'released':True}
