"""Readonly original evidence analysis, no transport/tokenizer/Engine."""
from pathlib import Path
import copy, hashlib, json, sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from lore_provider.request import BINDING, encode_request
from lore_provider.jsoncodec import encode
HOME=Path(__file__).resolve().parent
OUT=Path(sys.argv[1]).absolute() if len(sys.argv)>1 else HOME
OUT.mkdir(parents=True,exist_ok=True)
P=ROOT/'validation/system/evidence/m01-real-004/M01-v5-2'
INTENT=json.loads((HOME/'revision-002.json').read_text())
def sha(raw): return hashlib.sha256(raw).hexdigest()
def ref(path):
 raw=path.read_bytes();return {'path':str(path),'bytes':len(raw),'sha256':sha(raw)}
def raw_for(frame, binding):
 scope={k:copy.deepcopy(binding[k]) for k in BINDING}
 scope.update(operation_id=frame['operation_id'],response_entry_id=frame['response_entry_id'])
 return encode_request(dict(binding=scope,model='gpt-5.6-terra',max_completion_tokens=2048,context=frame['payload']),scope)
rows=[]
for d in (P/'provider').iterdir():
 prepared=json.loads((d/'prepared.json').read_text());original=(d/'wire/request.body').read_bytes()
 assert raw_for(prepared['frame'],prepared['binding'])==original
 usage=json.loads((d/'wire/response.body').read_bytes())['usage']
 rows.append(dict(frame=prepared['frame'],binding=prepared['binding'],request=original,usage=usage,source=ref(d/'wire/request.body'),prepared=ref(d/'prepared.json'),response=ref(d/'wire/response.body')))
rows.sort(key=lambda row:len(json.loads(row['request'])['messages']))
eid='s-exec-9430164ae71c94a92e2095cd5a2d74a35134934b920eb66f62a66a62fd611481'
d=P/'host/X-state'/sha(eid.encode());record=json.loads((d/'record.json').read_text());path=Path(record['artifacts']['stdout']['path']);data=path.read_bytes()
assert len(data)==record['artifacts']['stdout']['size'] and sha(data)==record['artifacts']['stdout']['sha256']
frame=json.loads(data);raw=raw_for(frame,rows[0]['binding']);assert len(raw)==10881
rows.append(dict(frame=frame,binding=rows[0]['binding'],request=raw,usage=None,source=ref(path),record=ref(d/'record.json')))
used=0;summary=[]
for i,row in enumerate(rows,1):
 r=json.loads(row['request']);context=row['frame']['payload'];changed=copy.deepcopy(row['frame'])
 users=[m for m in context['messages'] if m['role']=='user'];assert len(users)==i
 prompts=[]
 for m in changed['payload']['messages']:
  if m['role']!='user':continue
  old=m['content'] if type(m['content']) is str else ''.join(b['text'] for b in m['content'])
  prefix='/input/history/';a=old.index(prefix);path=old[a:a+len(prefix)+64]
  assert len(old.encode())==591 and len(path)==79
  new=INTENT['candidate_prompt_template'].replace('PATH',path);assert len(new.encode())==INTENT['expected_prompt_bytes']
  m['content']=[{'type':'text','text':new}];prompts.append(new)
 prompt_raw=raw_for(changed,row['binding'])
 blocks=json.loads(changed['payload']['systemPrompt']);original_blocks=copy.deepcopy(blocks)
 indexes=[j for j,b in enumerate(blocks['context_blocks']) if b.startswith('Current Step Workspace snapshot is available now at:')];assert len(indexes)==1
 j=indexes[0];blocks['context_blocks'][j]=INTENT['candidate_projection_explanation']
 changed['payload']['systemPrompt']=json.dumps(blocks,ensure_ascii=False,separators=(',',':'))
 for k,b in enumerate(original_blocks['context_blocks']):
  if k!=j:assert blocks['context_blocks'][k]==b
 for a,b in zip(context['messages'],changed['payload']['messages']):
  if a['role']!='user':assert a==b
 candidate=raw_for(changed,row['binding']);actual_usage=row['usage']['prompt_tokens'] if row['usage'] else None
 summary.append(dict(step=i,original_body_bytes=len(row['request']),used_original_prompt_tokens_before=used,actual_original_prompt_tokens=actual_usage,original_preflight_sum=used+len(row['request']),prompt_only_body_bytes=len(prompt_raw),both_text_changes_body_bytes=len(candidate),both_changes_with_unchanged_original_usage=used+len(candidate),wire_message_bytes=[dict(role=m['role'],bytes=len(encode(m))) for m in r['messages']],top_level_non_messages_bytes=len(row['request'])-len(encode(r['messages'])),system_blocks=[dict(index=k,utf8_bytes=len(b.encode()),json_string_bytes=len(encode(b))) for k,b in enumerate(original_blocks['context_blocks'])],candidate_sha256=sha(candidate),source={k:row[k] for k in ('source','prepared','response','record') if k in row},all_nonexplanatory_blocks_and_nonuser_messages_identical=True))
 if actual_usage is not None:used+=actual_usage
 if i==5:
  out=OUT/'derived';out.mkdir(exist_ok=False);(out/'original-unsent-5.body').write_bytes(row['request']);(out/'counterfactual-concise-5.body').write_bytes(candidate);(out/'counterfactual-prompts.json').write_text(json.dumps(prompts,indent=2)+'\n')
last=summary[-1];original_prompt=591;new_prompt=INTENT['expected_prompt_bytes']
result={'status':'READONLY_COUNTERFACTUAL_BYTES_ONLY','rows':summary,'six_step_prompt_contribution':[{'step':i,'original_prompt_content_bytes_in_history':i*original_prompt,'candidate_prompt_content_bytes_in_history':i*new_prompt,'savings':i*(original_prompt-new_prompt)} for i in range(1,7)],'six_calls_sum_prompt_content_bytes':{'original':21*original_prompt,'candidate':21*new_prompt,'savings':21*(original_prompt-new_prompt)},'fifth_margin_at_original_used':15360-used-last['both_text_changes_body_bytes'],'sixth_condition':{'actual_test':'6196 + actual_new_response5.prompt_tokens + actual_request6.bytes <= 15360 (holding observed first-four usage unchanged for this counterfactual replay only; not a bound on changed-model usage)','unknown':'No fifth HTTP exists. Neither future token usage nor assistant/tool output or next system delta is known. Do not derive tokens from historical byte ratios.','same_system_growth_formula':f'B6 = B5_concise + encoded assistant5 bytes + encoded tool5 bytes + {new_prompt+31} user-message-and-three-separator bytes + delta(system5->system6). Only applies if fifth returns one tool; a final answer needs no sixth request.','unchanged_system_available_for_usage_and_new_pair':15360-used-last['both_text_changes_body_bytes']-new_prompt-31},'source_inputs':{name:ref(ROOT/name) for name in INTENT['source_before']}}
assert used==6196 and last['original_preflight_sum']==17077
(OUT/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'steps':[{k:v for k,v in x.items() if k in ('step','original_body_bytes','used_original_prompt_tokens_before','both_text_changes_body_bytes','both_changes_with_unchanged_original_usage')} for x in summary],'fifth_margin':result['fifth_margin_at_original_used'],'sixth':result['sixth_condition']}))
