"""Pass actual operation scope to trusted authorities without sharing mutable inputs."""
import json
import math
from .errors import FileError,require
from .util import canonical,identity,ordinary_path


def detached(value,code="REFERENCE_INVALID"):
    def finite(item,depth=0):
        require(depth<=32,code,"authority context nesting limit")
        if isinstance(item,dict):
            require(all(isinstance(k,str) for k in item),code,"nontext context key")
            for child in item.values():finite(child,depth+1)
        elif isinstance(item,list):
            for child in item:finite(child,depth+1)
        else:require(item is None or type(item) in (str,int,bool) or type(item) is float and math.isfinite(item),code,"non-JSON authority context")
    try:
        finite(value);raw=canonical(value)
        require(len(raw)<=1048576,code,"authority context byte limit")
        return json.loads(raw)
    except (ValueError,TypeError,RecursionError) as exc:raise FileError(code,"invalid finite authority context") from exc


class FileAuthority:
    def context(self,operation,**fields):
        return detached(dict(schema="lore-f-authority-context/v1",operation=operation,**fields))

    def _authority_call(self,checker,value,purpose,context,code):
        try:accepted=checker(detached(value,code),purpose,detached(context,code))
        except Exception as exc:raise FileError(code,purpose+" authority unavailable or lacks complete context") from exc
        require(accepted is True,code,purpose+" authority rejected actual operation")

    def authorize(self,value,purpose,context):
        self._authority_call(self.authorization_checker,value,purpose,context,"UNAUTHORIZED")

    def check_reference(self,value,purpose,context):
        self._authority_call(self.reference_checker,value,purpose,context,"REFERENCE_INVALID")

    def binding_value(self,binding):
        value=detached(binding);value["path"]=str(ordinary_path(value["path"]))
        return value
