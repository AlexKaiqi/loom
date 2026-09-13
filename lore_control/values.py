"""Finite canonical control values and explicit error vocabulary."""
import json,math,re

class ControlError(ValueError):
    def __init__(self,code,message):
        self.code=code
        super().__init__(message)

def fail(code,message):raise ControlError(code,message)
def finite(value,depth=0):
    if depth>32:fail('invalid','control value nesting exceeds32')
    if type(value) is dict:
        if any(type(k) is not str for k in value):fail('invalid','JSON keys must be strings')
        for v in value.values():finite(v,depth+1)
    elif type(value) is list:
        for v in value:finite(v,depth+1)
    elif value is not None and type(value) not in (str,int,float,bool):fail('invalid','non-JSON control value')
    elif type(value) is float and not math.isfinite(value):fail('invalid','nonfinite control number')

def encode(value):
    finite(value)
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def decode(value):return json.loads(value) if value is not None else None
def same(a,b):return encode(a)==encode(b)
def identifier(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',value) is None:fail('invalid','invalid stable identifier')
    return value

def fields(value,required,label):
    if type(value) is not dict or set(value)!=set(required):fail('invalid','invalid '+label+' fields')

def positive_int(value,label="value"):
    if type(value) is not int or value<1:fail('invalid',label+' must be positive integer')
    return value
