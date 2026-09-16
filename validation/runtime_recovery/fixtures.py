"""Only five original cut fixtures; reuse the already prepared ordinary directories."""
import json,os,shlex
from pathlib import Path
from validation.runtime_security.fixtures import prepare as ordinary,response,save,sha
ROOT=Path(__file__).resolve().parents[2]
CUTS=('accept','provider','tool','decision','install')

def prepare(base,cut,repeat):
    # M02 factory only creates its ordinary file fixture; no M02 owner/test is invoked.
    sample=ordinary(base,'m03-'+cut,repeat)
    previous=Path(sample['out']);out=base/('M03-'+cut+'-'+str(repeat));previous.rename(out)
    for key in ('surface','workspace','private','canary','out'):sample[key]=str(out/Path(sample[key]).relative_to(previous))
    sample.update(id=out.name,cut=cut,repeat=repeat)
    (Path(sample['workspace'])/'effects.log').write_bytes(b'')
    program="from pathlib import Path; import os; p=Path('effects.log'); f=p.open('ab'); f.write(b'M03_EFFECT\\n'); f.flush(); os.fsync(f.fileno()); f.close(); print(p.read_text(),end='')"
    sample['effect_marker']='M03_EFFECT';sample['script']='python3 -c '+shlex.quote(program)
    message=dict(role='assistant',content='The finite recovery fixture is complete.')
    finish='stop'
    if cut in ('tool','install'):
        message=dict(role='assistant',content=None,tool_calls=[dict(id='native-m03-call',type='function',function=dict(name='shell',arguments=json.dumps(dict(target='workspace',script=sample['script']))))]);finish='tool_calls'
    if cut!='accept':(out/'response.body').write_bytes(response(message,finish,1))
    save(out/'fixture.json',sample);return sample

def durable(path,value):
    path=Path(path);data=json.dumps(value,sort_keys=True,ensure_ascii=False).encode()+b'\n'
    temp=path.with_name(path.name+'.pending')
    with temp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    os.replace(temp,path);fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
