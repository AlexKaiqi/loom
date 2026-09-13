"""Authorized historical reads and materialization; retained versions stay in Git."""
from pathlib import Path
from .authority import detached
from .archive import materialize_tree,member_name
from .errors import FileError,require
from .metadata import walk
from .util import identity,ordinary_path,digest


class HistoricalFiles:
    def materialize(self,request_id,version_ref,target_path,authorization,profile="host-v1"):
        version_ref,authorization=detached(version_ref),detached(authorization,"UNAUTHORIZED")
        target=ordinary_path(target_path);self.external_path(target)
        inputs=dict(operation="materialize",version_ref=version_ref,target_path=str(target),authorization=authorization,profile=profile)
        with self.journal.lock():
            require(profile==version_ref.get("profile")=="host-v1","UNSUPPORTED","profile change not authorized")
            _,tree,contents=self.versions.load(version_ref)
            parent=ordinary_path(target.parent);parent_root=identity(parent)
            context=self.context("materialize",request_id=request_id,version_ref=version_ref,target_path=str(target),target_parent=dict(path=str(parent),root=parent_root),profile=profile)
            self.authorize(authorization,"materialize",context)
            old=self._existing(request_id,inputs)
            if old is not None:
                require(identity(target)==old["root"],"STALE_BINDING","materialized object replaced")
                require(walk(target,self.limits)[0]==tree,"BASE_CHANGED","materialized object changed")
                return old
            require(identity(ordinary_path(parent))==parent_root,"STALE_BINDING","authorized target parent replaced")
            materialize_tree(tree,contents,target,self.limits)
            result=dict(path=str(target),root=identity(target),version_ref=version_ref)
            return self._complete(request_id,inputs,result)

    def read_reference(self,reference,authorization):
        reference,authorization=detached(reference),detached(authorization,"UNAUTHORIZED")
        reference["path"]=member_name(reference["path"])
        with self.journal.lock():
            _,tree,contents=self.versions.load(reference["version_ref"])
            self.authorize(authorization,"read_reference",self.context("read_reference",reference=reference))
            name=reference["path"]
            require(reference.get("kind")=="file" and tree["entries"].get(name,{}).get("kind")=="file","REFERENCE_TYPE","historical reference is not a regular file")
            data=contents[name]
            require(reference.get("sha256",digest(data))==digest(data),"VERSION_CORRUPT","reference content digest differs")
            return data

    def retain(self,pin_id,version_ref):
        version_ref=detached(version_ref)
        with self.journal.lock():self.versions.retain(pin_id,version_ref)

    def release(self,pin_id,authorization):
        authorization=detached(authorization,"UNAUTHORIZED")
        with self.journal.lock():
            original=self.versions.pin_reference(pin_id)
            self.authorize(authorization,"release",self.context("release",pin_id=pin_id,version_ref=original))
            self.versions.release(pin_id)

    def gc(self):
        with self.journal.lock():self.versions.gc()
