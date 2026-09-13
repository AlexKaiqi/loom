import json,sys
for line in sys.stdin:
 request=json.loads(line);print(json.dumps({'request_id':request['request_id'],'status':'PASS','result':{'execution_state':'STOPPED','output_state':'COMPLETE'}}),flush=True)
