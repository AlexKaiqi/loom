"""Trusted shared service lifecycle; finite streams, no per-wait resource allocation."""
from copy import deepcopy
from pathlib import Path
import re
import nats
import nats.js.errors
from nats.js.api import StreamConfig,StorageType,DiscardPolicy,RetentionPolicy
from .values import fail,identifier,positive,sha
from .publication import Publication
from .receipts import Receipts
from .history import History
from .inputs import Inputs

class EventService(Publication,Receipts,History,Inputs):
    def __init__(self,server_url,control_store,service_profile,checkpoint=None):
        self.url=server_url;self.control=control_store;self.profile=deepcopy(service_profile);self.checkpoint=checkpoint;self.nc=None;self.js=None;self.errors=[]
        self.runtime=self.profile.get('runtime_principal')
        self._validate_profile()

    def _validate_profile(self):
        p=self.profile
        try:
            if type(p['namespaces']) is not list or not 1<=len(p['namespaces'])<=128 or len(set(p['namespaces']))!=len(p['namespaces']):raise ValueError('finite distinct namespaces required')
            if any(type(ns) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',ns) for ns in p['namespaces']):raise ValueError('invalid namespace token')
            for field in ['stream_max_bytes','message_limit_bytes','page_size']:positive(p[field],field)
            if p['storage']!='file' or p['discard']!='new' or p['max_age']!=0 or p['replicas']!=1:raise ValueError('unverified retention/storage profile')
            if type(p['authority']) is not dict or not Path(p['input_root']).is_absolute():raise ValueError('trusted authority and absolute input root required')
            if type(self.runtime) is not str or not self._is_runtime(self.runtime):raise ValueError('trusted runtime principal required')
            if any(ns not in p['authority'][self.runtime].get('namespaces',[]) for ns in p['namespaces']):raise ValueError('runtime namespace grant missing')
            if not re.fullmatch(r'[A-Za-z0-9_-]+',p['stream_prefix']) or not re.fullmatch(r'[A-Za-z0-9_-]+',p['subject_prefix']):raise ValueError('invalid service namespace prefix')
        except (ValueError,KeyError,TypeError) as exc:fail('configuration_error',str(exc))

    def _is_runtime(self,context):return type(context) is str and 'runtime' in self.profile['authority'].get(context,{}).get('roles',[])
    def _authorize(self,context,namespace,submit=False,runtime=False):
        if type(context) is not str or type(namespace) is not str:fail('invalid','context and namespace must be trusted strings')
        entry=self.profile['authority'].get(context,{})
        if namespace not in self.profile['namespaces'] or namespace not in entry.get('namespaces',[]):fail('denied','namespace not authorized')
        roles=entry.get('roles',[])
        if runtime and 'runtime' not in roles:fail('denied','runtime observation role required')
        if submit and not {'submit','runtime','admin'}&set(roles):fail('denied','event submission role required')
    def _stream(self,ns):return self.profile['stream_prefix']+ns
    def _subject(self,ns,id):return self.profile['subject_prefix']+'.'+ns+'.event.'+sha(id.encode())
    async def _checkpoint(self,label,record):
        if self.checkpoint is not None:await self.checkpoint(label,record)
    async def _connection_error(self,error):self.errors.append(type(error).__name__)

    def _expected_config(self,namespace):
        return StreamConfig(name=self._stream(namespace),subjects=[self.profile['subject_prefix']+'.'+namespace+'.event.*'],storage=StorageType.FILE,retention=RetentionPolicy.LIMITS,discard=DiscardPolicy.NEW,max_age=0,num_replicas=1,max_bytes=self.profile['stream_max_bytes'],max_msgs=-1,max_msgs_per_subject=-1,max_consumers=-1)
    def _check_config(self,actual,wanted):
        for key in ['name','subjects','storage','retention','discard','max_age','num_replicas','max_bytes','max_msgs','max_msgs_per_subject']:
            if getattr(actual,key)!=getattr(wanted,key):fail('configuration_error','existing stream '+key+' differs from required preservation profile')
        if actual.sealed or actual.deny_delete is False and actual.max_age:fail('configuration_error','existing stream is not writable or retained')

    async def start(self):
        if self.nc is not None and not self.nc.is_closed:return
        try:
            self.nc=await nats.connect(servers=[self.url],allow_reconnect=False,connect_timeout=2,error_cb=self._connection_error)
            self.js=self.nc.jetstream(timeout=2)
            for namespace in self.profile['namespaces']:
                wanted=self._expected_config(namespace)
                try:info=await self.js.stream_info(wanted.name)
                except nats.js.errors.NotFoundError:info=await self.js.add_stream(config=wanted)
                self._check_config(info.config,wanted)
        except BaseException:
            await self.close();raise
    async def close(self):
        if self.nc is not None:await self.nc.close()
