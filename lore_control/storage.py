"""One SQLite transaction domain. No external effect is executed here."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import os,sqlite3,threading
from .values import ControlError,fail,encode,decode,same,identifier

SCHEMA="CREATE TABLE meta(key TEXT PRIMARY KEY,value INTEGER NOT NULL);\nINSERT INTO meta VALUES('schema_version',2),('claim_clock',0);\nCREATE TABLE resources(id TEXT PRIMARY KEY,namespace TEXT NOT NULL,kind TEXT NOT NULL,path TEXT NOT NULL,dev INTEGER NOT NULL,ino INTEGER NOT NULL,revision INTEGER NOT NULL,harness_ref_json TEXT NOT NULL,grants_json TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);\nCREATE TABLE operations(id TEXT PRIMARY KEY,binding_json TEXT NOT NULL,response_json TEXT NOT NULL);\nCREATE TABLE requests(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,principal TEXT NOT NULL,namespace TEXT NOT NULL,kind TEXT NOT NULL,payload_json TEXT NOT NULL,phase TEXT NOT NULL,result_ref_json TEXT,query_ref_json TEXT,reason TEXT,token TEXT,worker TEXT,lease_until REAL,receipt_ref_json TEXT,delivery_owner TEXT);\nCREATE INDEX requests_ready ON requests(phase,lease_until,seq);\nCREATE TABLE namespace_turns(namespace TEXT PRIMARY KEY,turn INTEGER NOT NULL);\nCREATE TABLE decisions(id TEXT PRIMARY KEY,parent_id TEXT NOT NULL UNIQUE,source_ref_json TEXT NOT NULL,harness_ref_json TEXT NOT NULL,body_json TEXT NOT NULL,applied INTEGER NOT NULL DEFAULT 0,wait_barriers_json TEXT);\nCREATE TABLE waits(id TEXT PRIMARY KEY,parent_id TEXT NOT NULL,namespace TEXT NOT NULL,binding_json TEXT NOT NULL,event_ref_json TEXT,successor_json TEXT,matched INTEGER NOT NULL DEFAULT 0);\nCREATE TABLE holders(resource_id TEXT PRIMARY KEY,execution_id TEXT NOT NULL,base_ref_json TEXT NOT NULL);\nCREATE TABLE releases(resource_id TEXT NOT NULL,execution_id TEXT NOT NULL,binding_json TEXT NOT NULL,holder_json TEXT,PRIMARY KEY(resource_id,execution_id));\nCREATE TABLE inputs(invocation_id TEXT PRIMARY KEY,binding_json TEXT NOT NULL,input_ref_json TEXT NOT NULL);\nCREATE TABLE installations(request_id TEXT PRIMARY KEY,restore_plan_id TEXT,binding_json TEXT NOT NULL,installation_ref_json TEXT);\nCREATE TABLE restore_installs(request_id TEXT PRIMARY KEY,plan_id TEXT NOT NULL,domain TEXT NOT NULL);\n"

class StoreBase:
    def __init__(self,db_path,authority,lease_seconds=30,request_limit_bytes=262144,transaction_timeout=10,reference_checker=None,checkpoint=None):
        if not isinstance(authority,dict):fail('invalid','authority must be trusted host configuration')
        if type(lease_seconds) not in (int,float) or lease_seconds<=0:fail('invalid','invalid lease duration')
        self.authority=deepcopy(authority)
        self.lease_seconds=lease_seconds
        self.request_limit_bytes=request_limit_bytes
        self.reference_checker=reference_checker
        self.checkpoint=checkpoint or (lambda label,record:None)
        self._lock=threading.RLock()
        self.db=None
        try:
            path=Path(db_path);path.parent.mkdir(parents=True,exist_ok=True)
            existed=path.exists()
            self.db=sqlite3.connect(str(path),timeout=transaction_timeout,isolation_level=None,check_same_thread=False)
            self.db.row_factory=sqlite3.Row
            self.db.execute('PRAGMA foreign_keys=ON')
            mode=self.db.execute('PRAGMA journal_mode').fetchone()[0]
            if mode!='wal':self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA synchronous=FULL')
            tables=self.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if not tables:
                if existed and path.stat().st_size:fail('storage_error','existing database has no acknowledged schema')
                self.db.executescript('BEGIN IMMEDIATE;'+SCHEMA+'COMMIT;')
                fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(fd)
                finally:os.close(fd)
            else:
                version=self.db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
                if version is None or version[0] not in (1,2):fail('storage_error','unsupported control schema')
                if version[0]==1:
                    # Missing legacy associations remain SQL NULL, never inferred from refs.
                    self.db.executescript("BEGIN IMMEDIATE; ALTER TABLE decisions ADD COLUMN wait_barriers_json TEXT; ALTER TABLE releases ADD COLUMN holder_json TEXT; UPDATE meta SET value=2 WHERE key='schema_version'; COMMIT;")
                if self.db.execute('PRAGMA quick_check').fetchone()[0]!='ok':fail('storage_error','database integrity check failed')
        except (sqlite3.Error,OSError) as exc:
            self.close();fail('storage_error',str(exc))
        except BaseException:
            self.close();raise

    @contextmanager
    def _tx(self,write=True):
        with self._lock:
            if self.db is None:fail('storage_error','store is closed')
            try:
                self.db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
                yield
                self.db.commit()
            except (sqlite3.Error,OSError) as exc:
                self.db.rollback();fail('storage_error',str(exc))
            except BaseException:
                self.db.rollback();raise

    def close(self):
        with self._lock:
            if self.db is not None:
                self.db.close();self.db=None

    def _authorize(self,principal,namespace,roles=None):
        entry=self.authority.get(principal,{})
        if namespace not in entry.get('namespaces',[]):fail('denied','namespace not authorized')
        if roles and not set(roles)&set(entry.get('roles',[])):fail('denied','role not authorized')

    def _reference(self,ref,purpose,expected=None):
        if not callable(self.reference_checker):fail('reference_invalid','no authoritative reference resolver')
        try:valid=self.reference_checker(deepcopy(ref),purpose,deepcopy(expected))
        except Exception as exc:fail('reference_invalid','reference authority unavailable: '+str(exc))
        if valid is not True:fail('reference_invalid','original reference or association invalid: '+purpose)

    def _get_request(self,id):
        row=self.db.execute('SELECT * FROM requests WHERE id=?',(id,)).fetchone()
        if row is None:fail('not_found','request not accepted')
        return row

    def _request_value(self,row):
        value={k:row[k] for k in ['id','principal','namespace','kind','phase']}
        value.update(payload=decode(row['payload_json']),result_ref=decode(row['result_ref_json']),query_ref=decode(row['query_ref_json']),receipt_ref=decode(row['receipt_ref_json']))
        if row['kind']=='restore_plan':value['restore']=self._restore_progress(row)
        return value

    def _operation_previous(self,id,binding):
        identifier(id)
        row=self.db.execute('SELECT * FROM operations WHERE id=?',(id,)).fetchone()
        if row:
            if row['binding_json']!=encode(binding):fail('conflict','operation identity reused with different binding')
            return decode(row['response_json'])

    def _operation_saved(self,id,binding,result):
        self.db.execute('INSERT INTO operations VALUES(?,?,?)',(id,encode(binding),encode(result)))
        return result
