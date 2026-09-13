"""Deliberately wrong test adapter: reports pass but creates no physical object."""
import json,sys
for line in sys.stdin:
 q=json.loads(line);print(json.dumps({'request_id':q['request_id'],'passed':True,'checks':{'all':True},'result':{'execution_state':'STOPPED','output_state':'COMPLETE'}}),flush=True)
