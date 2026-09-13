"""Canonical event values. No persistence or delivery decisions."""
import hashlib,json,math,re

class EventError(ValueError):
    def __init__(self,code,message):self.code=code;super().__init__(message)
def fail(code,message):raise EventError(code,message)
def finite(value,depth=0):
    if depth>32:fail('invalid','JSON nesting exceeds32')
    if type(value) is dict:
        if any(type(k) is not str for k in value):fail('invalid','JSON object keys must be strings')
        for item in value.values():finite(item,depth+1)
    elif type(value) is list:
        for item in value:finite(item,depth+1)
    elif value is not None and type(value) not in (str,bool,int,float):fail('invalid','non-JSON value')
    elif type(value) is float and not math.isfinite(value):fail('invalid','nonfinite number')
def encode(value):
    finite(value)
    try:return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
    except (UnicodeError,ValueError,TypeError) as exc:fail('invalid',str(exc))
def decode(raw):
    def duplicate(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate JSON field')
            result[key]=value
        return result
    try:
        value=json.loads(raw,object_pairs_hook=duplicate);finite(value);return value
    except (UnicodeError,ValueError,TypeError) as exc:fail('reference_invalid','invalid original JSON: '+str(exc))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def same(a,b):return encode(a)==encode(b)
def identifier(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',value) is None:fail('invalid','invalid stable identity')
    return value
def positive(value,label):
    if type(value) is not int or value<1:fail('invalid',label+' must be a positive integer')
def original_request(row):
    return {k:row[k] for k in ['principal','id','namespace','kind','payload']}
def envelope(source,id,namespace,name,payload,origin='application'):
    return {'schema_version':1,'origin':origin,'source':source,'namespace':namespace,'request_id':id,'name':name,'payload':payload}
