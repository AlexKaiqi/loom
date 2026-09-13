"""Bounded independent reads. No product imports or executing archive contents."""
import base64,hashlib,http.client,io,json,os,socket,sqlite3,stat,subprocess,tarfile
from pathlib import Path
from urllib.parse import quote,urlparse
from validation.components.f.observer import archive_tree

class ObserverError(RuntimeError):pass
def require(v,m):
    if not v:raise ObserverError(m)
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def digest(v):return hashlib.sha256(v).hexdigest()
def strict(raw):
    def pairs(items):
        d={}
        for k,v in items:
            require(k not in d,'duplicate JSON member');d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ObserverError('nonfinite JSON')))
def read(path,cap=2097152):
    p=Path(path);require(p.is_absolute() and not p.is_symlink(),'absolute unaliased original file required')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd);require(stat.S_ISREG(st.st_mode) and st.st_size<=cap,'nonregular/unbounded original')
        chunks=[];n=0
        while True:
            b=os.read(fd,min(524288,cap+1-n))
            if not b:break
            n+=len(b);require(n<=cap,'original grew past cap');chunks.append(b)
        end=os.fstat(fd);require((st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)==(end.st_dev,end.st_ino,end.st_size,end.st_mtime_ns,end.st_ctime_ns),'original changed during read')
        return b''.join(chunks)
    finally:os.close(fd)
def refraw(ref,root,cap=2097152):
    p=Path(ref['path']);require(p.resolve().is_relative_to(Path(root).resolve()),'original reference escapes configured owner')
    b=read(p,cap);require(digest(b)==ref['sha256'] and len(b)==ref.get('bytes',ref.get('size',len(b))),'original reference hash/bytes mismatch')
    if 'root' in ref:
        s=p.stat();require(ref['root']=={'dev':s.st_dev,'ino':s.st_ino},'original reference inode mismatch')
    return b
def sql(path):
    p=Path(path);require(p.is_file(),'original R database absent')
    c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=2);c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON')
    try:
        out={}
        for table in ('resources','requests','decisions','inputs','installations','holders','releases','waits'):
            rows=c.execute('SELECT * FROM '+table+' LIMIT 10001').fetchall();require(len(rows)<=10000,'R finite sample row bound')
            out[table]=[{k[:-5] if k.endswith('_json') else k:strict(v) if k.endswith('_json') and v is not None else v for k,v in dict(row).items()} for row in rows]
        return out
    finally:c.close()
def tar_files(raw,cap=18874368):
    require(len(raw)<=cap,'archive observation bound');files={};names=set();total=0
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as src:
        for item in src:
            n=item.name[2:] if item.name.startswith('./') else item.name
            require(n=='.' or n and not n.startswith('/') and all(x not in ('','..','.') for x in n.split('/')),'unsafe archive member')
            require(n not in names and len(names)<8192,'duplicate/unbounded member set');names.add(n)
            if item.isfile():
                total+=item.size;require(total<=cap,'expanded archive bound');data=src.extractfile(item).read(cap+1);require(len(data)==item.size,'truncated member');files[n]=data
            elif item.islnk():require(item.linkname.removeprefix('./') in files,'unresolved hardlink');files[n]=files[item.linkname.removeprefix('./')]
            else:require(item.isdir() or item.issym(),'special archive member')
    return files,names

def git_version(control,ref):
    require(set(ref)=={'resource_id','domain','profile','git_ref','archive_sha256','manifest_sha256'} and ref['git_ref'].startswith('refs/lore/versions/') and ':' not in ref['git_ref'],'invalid complete F version')
    blobs={}
    for name,key in [('archive.tar','archive_sha256'),('manifest.json','manifest_sha256')]:
        p=subprocess.run(['/usr/bin/git','--git-dir='+str(Path(control)/'versions.git'),'-c','core.hooksPath=/dev/null','cat-file','blob',ref['git_ref']+':'+name],capture_output=True,timeout=15,env={'PATH':'/usr/bin:/bin','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'})
        require(p.returncode==0 and len(p.stdout)<=18874368 and digest(p.stdout)==ref[key],'actual F Git blob/hash unavailable');blobs[name]=p.stdout
    manifest=strict(blobs['manifest.json'])
    require(manifest['schema']=='lore-f-manifest/v1' and all(manifest[k]==ref[k] for k in ('resource_id','domain','profile')),'F manifest scope differs')
    require(canonical(archive_tree(blobs['archive.tar']))==canonical(manifest['tree']),'F actual complete archive/manifest mismatch')
    files,_=tar_files(blobs['archive.tar']);return files,manifest,blobs

class EngineRead:
    def __init__(self,endpoint):
        require(endpoint.startswith('unix://'),'only original local Unix Engine');self.path=endpoint[7:]
    def get(self,path):
        sockpath=self.path
        class Conn(http.client.HTTPConnection):
            def connect(self):self.sock=socket.socket(socket.AF_UNIX);self.sock.settimeout(2);self.sock.connect(sockpath)
        c=Conn('localhost',timeout=2)
        try:
            c.request('GET','/v1.48'+path);r=c.getresponse();data=r.read(2097153);require(len(data)<=2097152,'Engine GET bound')
            require(r.status in (200,404),'Engine GET failed '+str(r.status));return {'status':r.status,'body':strict(data) if data else None}
        finally:c.close()

def allocation(roots):
    seen=set();size=count=0
    for root in roots:
        root=Path(root)
        if not root.exists():continue
        for p in [root,*root.rglob('*')]:
            s=p.lstat();require(not stat.S_ISLNK(s.st_mode),'private storage unexpected link');key=(s.st_dev,s.st_ino)
            if key not in seen:seen.add(key);size+=s.st_blocks*512;count+=1
            require(count<=200000,'storage observation bound')
    return {'allocated_bytes':size,'inodes':count}
def rss(pid):
    b=Path('/proc/'+str(pid)+'/status').read_text();return int(next(x.split()[1] for x in b.splitlines() if x.startswith('VmRSS:')))*1024

def nats_listener(url):
    port=urlparse(url).port;require(port is not None and urlparse(url).hostname in ('localhost','127.0.0.1','::1'),'local NATS observer scope')
    sockets=set()
    for p in (Path('/proc/net/tcp'),Path('/proc/net/tcp6')):
        for row in p.read_text().splitlines()[1:]:
            a=row.split()
            if int(a[1].rsplit(':',1)[1],16)==port and a[3]=='0A':sockets.add(a[9])
    ids=set()
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            for fd in (p/'fd').iterdir():
                if os.readlink(fd) in {'socket:['+x+']' for x in sockets}:ids.add(int(p.name));break
        except (OSError,PermissionError):continue
    require(len(ids)==1,'unique actual configured NATS listener PID unavailable');return next(iter(ids))

def raw_value(jsonl,namespace,key):
    # Exact source value slice; never approximate JSON.stringify with Python serialization.
    dec=json.JSONDecoder();found=None
    def fields(text):
        i=1;result={}
        while text[i:].lstrip() and text[i:].lstrip()[0]!='}':
            while text[i].isspace() or text[i]==',':i+=1
            k,end=dec.raw_decode(text,i);i=end
            while text[i].isspace():i+=1
            require(text[i]==':','object separator');i+=1
            while text[i].isspace():i+=1
            start=i;_,i=dec.raw_decode(text,i);result[k]=text[start:i]
        return result
    for line in jsonl.decode('utf8').splitlines():
        pending=[line]
        if line.startswith('['):
            pending=[];i=1
            while line[i:].lstrip() and line[i:].lstrip()[0]!=']':
                while line[i].isspace() or line[i]==',':i+=1
                start=i;_,i=dec.raw_decode(line,i);pending.append(line[start:i])
        for item in pending:
            row=strict(item)
            if isinstance(row,dict) and row.get('namespace')==namespace and row.get('key')==key and row.get('op')=='set':found=fields(item)['value'].encode('utf8')
    require(found is not None,'original raw value missing');return found

# Exact already-verified X exporter commands (archives.py), independently frozen
# in resource-calibration-002/protocol.json; not a candidate-defined allowlist.
_EXPORT_IMAGE='python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea'
_EXPORT_CMDS={'7c2c414b4502a10b5098136853f91afbbe477ce6b5eacebc0c23494c4b592a66','367d95f320c571b1e69c87a2ea3a85d33c0afedb60bc26cddc2f3d6f0d879e16'}

def helper_allowed(actual,binding,slot_owner,volume):
    try:
        c=actual['Config'];h=actual['HostConfig'];labels=c['Labels'];mounts=actual['Mounts']
        if c['Image']!=_EXPORT_IMAGE or c.get('Entrypoint') not in (None,[]):return False
        if labels.get('lore.x.role')!='helper' or labels.get('lore.x.slot_owner')!=slot_owner or labels.get('lore.x.slot_id')!=binding['slot_id'] or labels.get('lore.x.execution_id')!=binding['execution_id']:return False
        if not binding.get('request_digest') or not binding.get('object_generation') or len(mounts)!=1 or volume.get('status')!=200:return False
        m=mounts[0];v=volume['body']
        if m['Type']!='volume' or m['Name']!=binding['volume_id'] or m['Destination']!='/work' or v['Name']!=m['Name'] or v['Mountpoint']!=m['Source'] or v['Driver']!=m['Driver']:return False
        if not h['ReadonlyRootfs'] or h['NetworkMode']!='none' or h.get('Privileged') or h.get('PidMode') not in ('',None) or set(h['CapDrop'])!={'ALL'} or not any('no-new-privileges' in x for x in h['SecurityOpt']):return False
        if c['User']=='0:0':return m['RW'] is False and [x.removeprefix('CAP_') for x in h.get('CapAdd') or []]==['DAC_OVERRIDE'] and digest(canonical(c['Cmd'])) in _EXPORT_CMDS
        return c['User']=='1000:1000' and not h.get('CapAdd') and m['RW'] is True and c['Cmd']==['tar','--numeric-owner','--no-same-owner','-xpf','-','-C','/work']
    except (KeyError,TypeError,ValueError):return False

def confirmed_removal(tick,volume_id):
    # Only fresh same-round GET responses may prove a disappearance. Old ticks
    # lacking these reads remain incomplete; a later batch never fills them in.
    try:
        if tick['volumes'][volume_id]['status']!=404:return False
        proof=tick['volume_transitions'][volume_id]
        expected={o['inspect']['body']['Id'] for o in tick['objects'] if o['inspect']['status']==200 and any(m.get('Type')=='volume' and m.get('Name')==volume_id for m in o['inspect']['body']['Mounts'])}
        rows=proof['containers'];ids=[x['container_id'] for x in rows]
        return bool(expected) and len(ids)==len(set(ids)) and set(ids)==expected and proof['volume_id']==volume_id and proof['volume_response']['status']==404 and all(x['response']['status']==404 for x in rows)
    except (KeyError,TypeError):return False

def complete_tool_result(record):
    result=record.get('result',{});code=result.get('exit_code')
    return record.get('released') is True and result.get('output_state')=='COMPLETE' and type(code) is int and 0<=code<=255

def complete_tool_feedback(message,stdout,stderr,exit_code,original_result_ref):
    try:
        d=message['details'];texts=[dict(type='text',text=stdout.decode('utf8'))]
        if stderr:texts.append(dict(type='text',text='stderr:\n'+stderr.decode('utf8')))
        texts.append(dict(type='text',text='Command exited with code '+str(exit_code)))
        return (message['role']=='toolResult' and message['content']==texts and d['result_ref']==original_result_ref
                and d['stdout']==dict(bytes=len(stdout),sha256=digest(stdout))
                and d['stderr']==dict(bytes=len(stderr),sha256=digest(stderr))
                and type(d['exit_code']) is int and d['exit_code']==exit_code
                and (exit_code==0 or message.get('isError') is True))
    except (KeyError,TypeError,UnicodeError):return False
