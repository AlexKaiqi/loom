import importlib,json,os,signal,sys
from pathlib import Path
from test_contract import auth,reference,STOP
x=json.loads(Path(sys.argv[1]).read_text());factory=importlib.import_module(x['module']).FileStore
def checkpoint(label,record):
 if label=='after_exchange_before_record':os.kill(os.getpid(),signal.SIGKILL)
store=factory(Path(x['control']),auth,reference,checkpoint=checkpoint);store.install('install-1',x['intent'],STOP)
raise SystemExit('did not reach registered crash point')
