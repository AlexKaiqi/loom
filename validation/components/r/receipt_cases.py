"""R20 revised real-reference sequence; all receipts are explicit authority fixtures."""
import copy,hashlib,json

def exercise(t):
 t.result_ready()
 def request(id):return {'id':id,'namespace':'n1','kind':'event','payload':{'name':'notice','parent_id':'op1','value':'original'}}
 def receipt(key,req,outcome,definite=True,overrides=None):
  fields={'request_id':req['id'],'namespace':'n1','source':'alice','delivery_owner':'E','request_digest':hashlib.sha256(json.dumps({'principal':'alice',**req},sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest(),'outcome':outcome,'definite':definite}
  fields.update(overrides or {})
  raw=json.dumps({'fixture_receipt':key,**fields},sort_keys=True).encode();(t.refroot/key).write_bytes(raw)
  ref={'owner':'E','id':key,'kind':'delivery_receipt','sha256':hashlib.sha256(raw).hexdigest(),**fields};t.refs[key]=ref;return ref
 event=request('event-request');t.store.accept('alice',event)
 t.expect_error('denied',t.store.mark_dispatched,'alice',event['id'],'E')
 t.assertIs(t.store.mark_dispatched('admin',event['id'],'E')['fresh'],True);t.assertIs(t.store.mark_dispatched('admin',event['id'],'E')['fresh'],False)
 positive=receipt('positive-receipt',event,'positive')
 wrong_digest=receipt('wrong-associated-receipt',event,'positive',overrides={'request_digest':'0'*64});t.assertTrue(t.checker(wrong_digest,'receipt'));t.expect_error('reference_invalid',t.store.confirm_delivery,'admin',event['id'],wrong_digest)
 t.expect_error('invalid',t.store.confirm_delivery,'admin','op1',positive)
 t.expect_error('reference_invalid',t.store.confirm_delivery,'admin',event['id'],t.refs['ev2'])
 t.store.confirm_delivery('admin',event['id'],positive);t.store.confirm_delivery('admin',event['id'],positive)
 negative_request=request('negative-request');t.store.accept('alice',negative_request);t.store.mark_dispatched('admin',negative_request['id'],'E')
 negative=receipt('negative-receipt',negative_request,'negative');t.assertTrue(t.checker(negative,'receipt'))
 t.store.confirm_delivery('admin',negative_request['id'],negative);t.store.confirm_delivery('admin',negative_request['id'],negative)
 other=receipt('other-negative-receipt',negative_request,'negative');t.assertTrue(t.checker(other,'receipt'));t.expect_error('conflict',t.store.confirm_delivery,'admin',negative_request['id'],other)
 t.assertIs(t.store.mark_dispatched('admin',negative_request['id'],'E')['fresh'],False)
 unknown_request=request('unknown-request');t.store.accept('alice',unknown_request);t.store.mark_dispatched('admin',unknown_request['id'],'E')
 unknown=receipt('unknown-observation',unknown_request,'unknown',False);t.assertTrue(t.checker(unknown,'receipt'))
 t.expect_error('reference_invalid',t.store.confirm_delivery,'admin',unknown_request['id'],unknown)
 t.assertEqual(t.store.query('alice',unknown_request['id'])['phase'],'issued')
 inconclusive=receipt('inconclusive-negative',unknown_request,'negative',False);t.assertTrue(t.checker(inconclusive,'receipt'));t.expect_error('reference_invalid',t.store.confirm_delivery,'admin',unknown_request['id'],inconclusive);t.assertEqual(t.store.query('alice',unknown_request['id'])['phase'],'issued')
 retry=request('retry-negative');retry['payload']['retry_of']={'request_id':negative_request['id'],'receipt_ref':negative};t.store.accept('alice',retry)
 t.assertIs(t.store.mark_dispatched('admin',retry['id'],'E')['fresh'],True)
 bypass=request('retry-unknown');bypass['payload']['retry_of']={'request_id':unknown_request['id'],'receipt_ref':unknown};t.expect_error('reference_invalid',t.store.accept,'alice',bypass)
 t.assertEqual(t.sql("select count(*) from requests where id='retry-unknown'")[0][0],0)
 not_yet_accepted=receipt('unaccepted-negative-for-issued',unknown_request,'negative');t.assertTrue(t.checker(not_yet_accepted,'receipt'))
 bypass2=request('retry-unaccepted-negative');bypass2['payload']['retry_of']={'request_id':unknown_request['id'],'receipt_ref':not_yet_accepted};t.expect_error('reference_invalid',t.store.accept,'alice',bypass2)
 t.assertEqual(t.sql("select count(*) from requests where id='retry-unaccepted-negative'")[0][0],0)
 t.store.close();t.store=t.new_store()
 for req,ref in [(event,positive),(negative_request,negative)]:
  row=t.store.query('alice',req['id']);t.assertEqual(row['phase'],'confirmed');t.assertEqual(row['receipt_ref'],ref)
 t.assertEqual(t.store.query('alice','op1')['phase'],'decide');t.assertIn('op1',[x['id'] for x in t.store.pending()]);t.assertEqual(t.store.query('alice',unknown_request['id'])['phase'],'issued')
 t.assertEqual(t.store.query('alice','negative-request')['receipt_ref']['outcome'],'negative')
 (t.root/'R20-authority-receipts.json').write_text(json.dumps({'positive':positive,'negative':negative,'unknown':unknown,'retry':retry},indent=2))
