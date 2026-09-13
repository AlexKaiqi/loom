"""Independent matrix arithmetic and original-input/raw-report verification for X04.

No task loop, candidate import, Runtime execution, timing claim or storage authority.
Callers must obtain job_index/input_sha256 from independently checked original refs.
"""
from dataclasses import dataclass
import hashlib,json,re

class OracleInvalid(ValueError):pass

def require(ok,message):
    if not ok:raise OracleInvalid(message)

def integer(value,lo,hi,label):
    require(type(value) is int and lo<=value<=hi,label+' must be an in-range integer')

@dataclass(frozen=True)
class Workload:
    jobs:int=64
    seed_base:int=871203
    rounds:int=500000
    multiplier:int=1664525
    increment:int=1013904223
    modulus:int=4294967296

    def __post_init__(self):
        integer(self.jobs,1,64,'jobs');integer(self.modulus,2,4294967296,'modulus')
        integer(self.seed_base,0,self.modulus-1,'seed_base')
        integer(self.rounds,0,500000,'rounds')
        integer(self.multiplier,0,self.modulus-1,'multiplier')
        integer(self.increment,0,self.modulus-1,'increment')

def load_workload(path):
    raw=path.read_bytes();obj=json.loads(raw);j=obj['jobs']
    require(j['seed_formula']=='(871203 + job_index) modulo 2^32','unreviewed seed formula')
    return Workload(jobs=j['count'],seed_base=871203,rounds=j['rounds'],
                    multiplier=j['multiplier'],increment=j['increment'],modulus=j['modulus'])

def multiply(left,right,modulus):
    # Fixed dimension; no workload-round loop and no floating point.
    return tuple(tuple(sum(left[row][k]*right[k][col] for k in range(3))%modulus
                       for col in range(3)) for row in range(3))

def expected_result(seed,rounds,*,multiplier=1664525,increment=1013904223,modulus=4294967296):
    integer(modulus,2,4294967296,'modulus');integer(seed,0,modulus-1,'seed')
    integer(rounds,0,500000,'rounds');integer(multiplier,0,modulus-1,'multiplier');integer(increment,0,modulus-1,'increment')
    power=((multiplier,1,increment),(0,1,1),(0,0,1));acc=((1,0,0),(0,1,0),(0,0,1));n=rounds
    while n:
        if n&1:acc=multiply(acc,power,modulus)
        power=multiply(power,power,modulus);n>>=1
    return (acc[0][0]*seed+acc[0][2])%modulus

def parse(raw,keys,label):
    require(type(raw) is bytes and 0<len(raw)<=65536,label+' actual bytes missing or outside budget')
    def pairs(items):
        value={}
        for key,item in items:
            require(key not in value,label+' duplicate JSON field');value[key]=item
        return value
    try:value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs)
    except (UnicodeError,ValueError,TypeError,RecursionError) as exc:raise OracleInvalid(label+' invalid JSON') from exc
    require(type(value) is dict and set(value)==keys,label+' exact field set required')
    require(all(type(x) is int for x in value.values()),label+' all fields must be integer values, not bool/float')
    return value

def verify_report(report_bytes,input_bytes,*,job_index,input_sha256,workload=Workload()):
    """Validate bytes against trusted original job/source identity, never report-selected math."""
    integer(job_index,0,workload.jobs-1,'original job_index')
    require(type(input_sha256) is str and re.fullmatch(r'[0-9a-f]{64}',input_sha256) is not None,'original SHA missing')
    require(type(input_bytes) is bytes and hashlib.sha256(input_bytes).hexdigest()==input_sha256,'original input SHA mismatch')
    keys={'schema_version','job_index','seed','rounds'}
    source=parse(input_bytes,keys,'input');report=parse(report_bytes,keys|{'result'},'report')
    expected={'schema_version':1,'job_index':job_index,'seed':(workload.seed_base+job_index)%workload.modulus,'rounds':workload.rounds}
    require(source==expected,'input differs from original expected job/seed/rounds')
    require({key:report[key] for key in keys}==expected,'report differs from original expected job/seed/rounds')
    result=expected_result(expected['seed'],workload.rounds,multiplier=workload.multiplier,increment=workload.increment,modulus=workload.modulus)
    require(report['result']==result,'wrong result')
    return {'job_index':job_index,'input_sha256':input_sha256,'report_sha256':hashlib.sha256(report_bytes).hexdigest(),'expected_result':result}
