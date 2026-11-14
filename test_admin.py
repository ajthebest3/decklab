"""Isolated admin passkey, command delivery and session privacy checks."""
import hashlib,json,os,socket,struct,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from admin_session import AdminSession,CodexSession,AdminAuthError

THREAD='11111111-1111-4111-8111-111111111111';PASSWORD='isolated-admin-test-passkey'
class Client:
 def __init__(self):self.calls=[];self.status='idle';self.turns=[];self.fail=False
 def rpc(self,method,params=None):
  self.calls.append((method,params))
  if method=='thread/read':return {'thread':{'id':THREAD,'status':{'type':self.status}}}
  if method=='thread/turns/list':return {'data':self.turns}
  if method=='thread/resume':return {}
  if method=='turn/steer':return {'turnId':params['expectedTurnId']}
  if method=='turn/start':
   if self.fail:raise ConnectionError('Private failure detail must not escape')
   self.status='active';return {'turn':{'id':'turn-admin-1'}}
  raise AssertionError(method)
class AdminTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.client=Client()
  self.engine=AdminSession(self.tmp.name,threading.Event(),client_factory=lambda _:self.client);self.engine.init();self.engine.provision(THREAD,PASSWORD)
  self.token=self.engine.unlock(PASSWORD)['session']
 def command(self,rid='request-fixture-1',text='Check status only'):
  return self.engine.submit(dict(session=self.token,command=text,request_id=rid))
 def test_passkey_hashed_private_and_token_hash_only(self):
  self.assertNotIn(PASSWORD,self.engine.path.read_text());self.assertEqual(self.engine.path.stat().st_mode&0o777,0o600);self.assertEqual(self.engine.db_path.stat().st_mode&0o777,0o600)
  with self.engine.db() as c:self.assertNotEqual(c.execute('SELECT token_hash FROM admin_sessions').fetchone()[0],self.token)
 def test_wrong_passkey_and_rate_limit(self):
  for _ in range(5):
   with self.assertRaises(AdminAuthError):self.engine.unlock('wrong')
  with self.assertRaisesRegex(AdminAuthError,'five minutes'):self.engine.unlock(PASSWORD)
 def test_unauthorized_cannot_read_or_submit_or_cancel(self):
  with self.assertRaises(AdminAuthError):self.engine.status('not-a-token')
  with self.assertRaises(AdminAuthError):self.engine.submit(dict(session='not-a-token',command='anything',request_id='request-fixture-1'))
  with self.assertRaises(AdminAuthError):self.engine.cancel(dict(session='not-a-token',id=1))
 def test_lock_revokes_session(self):
  self.engine.logout(self.token)
  with self.assertRaises(AdminAuthError):self.engine.status(self.token)
 def test_expired_sessions_rejected(self):
  with self.engine.db() as c:c.execute('UPDATE admin_sessions SET expires=?',(time.time()-1,))
  with self.assertRaisesRegex(AdminAuthError,'expired'):self.engine.status(self.token)
 def test_rotation_revokes_all_previous_sessions(self):
  self.engine.provision(THREAD,'replacement-admin-passkey')
  with self.assertRaises(AdminAuthError):self.engine.status(self.token)
  self.assertIn('session',self.engine.unlock('replacement-admin-passkey'))
 def test_command_idempotency_prevents_duplicates(self):
  first=self.command();second=self.command();self.assertEqual(first['id'],second['id']);self.assertTrue(second['reused'])
  with self.assertRaises(ValueError):self.command(text='different command')
 def test_command_validation(self):
  for rid,text in [('x','test'),('valid-request-1',''),('valid-request-2','x'*8001)]:
   with self.assertRaises(ValueError):self.command(rid,text)
 def test_active_session_queues_without_steering_or_starting(self):
  self.client.status='active';self.command();self.engine.cycle()
  self.assertFalse(any(m=='turn/start' for m,_ in self.client.calls));self.assertEqual(self.engine.status(self.token)['commands'][0]['state'],'queued')
 def test_explicit_reply_steers_active_turn_without_new_turn(self):
  self.client.status='active';self.client.turns=[dict(id='current-turn',status='inProgress',items=[])]
  self.engine.submit(dict(session=self.token,command='Clarification for the current task',request_id='reply-fixture-1',mode='reply'));self.engine.cycle()
  replies=[p for m,p in self.client.calls if m=='turn/steer'];self.assertEqual(len(replies),1);self.assertEqual(replies[0]['expectedTurnId'],'current-turn');self.assertFalse(any(m=='turn/start' for m,_ in self.client.calls))
 def test_reply_mode_must_be_valid_and_cannot_change_on_retry(self):
  with self.assertRaises(ValueError):self.engine.submit(dict(session=self.token,command='test',request_id='request-fixture-1',mode='exec'))
  self.command()
  with self.assertRaises(ValueError):self.engine.submit(dict(session=self.token,command='Check status only',request_id='request-fixture-1',mode='reply'))
 def test_idle_delivers_exact_bound_session_without_new_thread_or_shell(self):
  self.command();self.engine.cycle();self.assertEqual(self.engine.status(self.token)['commands'][0]['state'],'sent')
  calls=[p for m,p in self.client.calls if m=='turn/start'];self.assertEqual(len(calls),1)
  self.assertIn('[DeckLab Admin request-fixture-1]',calls[0]['input'][0]['text']);self.assertNotIn(PASSWORD,json.dumps(calls))
  self.engine.cycle();self.assertEqual(len([m for m,_ in self.client.calls if m=='turn/start']),1)
 def test_not_loaded_resumes_existing_thread_only(self):
  self.client.status='notLoaded';self.command();self.engine.cycle();self.assertTrue(any(m=='thread/resume' for m,_ in self.client.calls))
  self.assertFalse(any(m=='thread/start' for m,_ in self.client.calls))
 def test_uncertain_delivery_never_auto_retries(self):
  self.client.fail=True;self.command();self.engine.cycle();self.engine.cycle()
  self.assertEqual(len([m for m,_ in self.client.calls if m=='turn/start']),1);state=self.engine.status(self.token)['commands'][0];self.assertEqual(state['state'],'uncertain');self.assertNotIn('Private',state['error'])
 def test_uncertain_requires_explicit_owner_resolution(self):
  job=self.command()
  with self.engine.db() as c:c.execute("UPDATE admin_commands SET state='uncertain' WHERE id=?",(job['id'],))
  with self.assertRaises(AdminAuthError):self.engine.resolve(dict(session='invalid',id=job['id'],action='retry'))
  self.engine.resolve(dict(session=self.token,id=job['id'],action='retry'));self.assertEqual(self.engine.status(self.token)['commands'][0]['state'],'queued')
 def test_owner_dismissal_preserves_audit_without_resending(self):
  job=self.command()
  with self.engine.db() as c:c.execute("UPDATE admin_commands SET state='uncertain' WHERE id=?",(job['id'],))
  self.engine.resolve(dict(session=self.token,id=job['id'],action='dismiss'));self.engine.cycle();self.assertEqual(self.engine.status(self.token)['commands'][0]['state'],'dismissed');self.assertFalse(any(m=='turn/start' for m,_ in self.client.calls))
 def test_restart_marks_inflight_delivery_uncertain(self):
  job=self.command()
  with self.engine.db() as c:c.execute("UPDATE admin_commands SET state='sending' WHERE id=?",(job['id'],))
  self.engine.init();self.assertEqual(self.engine.status(self.token)['commands'][0]['state'],'uncertain')
 def test_lost_ack_reconciles_from_marker_without_resending(self):
  self.command()
  with self.engine.db() as c:c.execute("UPDATE admin_commands SET state='uncertain'")
  self.client.turns=[dict(id='prior-turn',status='completed',items=[dict(type='userMessage',content=[dict(type='text',text='[DeckLab Admin request-fixture-1]\nCheck status')])])]
  self.engine.cycle();self.assertEqual(self.engine.status(self.token)['commands'][0]['state'],'completed');self.assertFalse(any(m=='turn/start' for m,_ in self.client.calls))
 def test_completed_session_result_marks_command_complete(self):
  self.command();self.engine.cycle();self.client.turns=[dict(id='turn-admin-1',status='completed',items=[dict(type='agentMessage',id='reply-1',text='Actual session result',phase='final')])]
  self.engine.cycle();result=self.engine.status(self.token);self.assertEqual(result['commands'][0]['state'],'completed');self.assertEqual(result['session']['messages'][0]['text'],'Actual session result')
 def test_only_human_messages_and_assistant_replies_are_returned(self):
  self.client.turns=[dict(id='turn-private',status='completed',items=[dict(type='reasoning',content='private reasoning'),dict(type='commandExecution',aggregatedOutput='private token'),dict(type='agentMessage',text='Test sk-privatecredentialvalue and DeckLab-12345678901234567890',phase='final'),dict(type='userMessage',content=[dict(type='text',text='Owner question')])])]
  self.engine.cycle();payload=json.dumps(self.engine.status(self.token));self.assertNotIn('private reasoning',payload);self.assertNotIn('private token',payload);self.assertNotIn('sk-privatecredential',payload);self.assertNotIn('DeckLab-12345678901234567890',payload)
 def test_queue_limit_and_cancel(self):
  for i in range(20):self.command('request-fixture-'+str(i))
  with self.assertRaisesRegex(ValueError,'full'):self.command('request-overflow')
  self.engine.cancel(dict(session=self.token,id=1));self.assertEqual(self.engine.status(self.token)['commands'][-1]['state'],'cancelled')
 def test_no_interested_session_means_no_rpc(self):
  self.engine.logout(self.token);self.engine.cycle();self.assertEqual(self.client.calls,[])
 def test_arbitrary_rpc_rejected_before_socket_access(self):
  client=CodexSession(THREAD)
  for method in ('command/exec','thread/start','thread/fork','config/value/write'):
   with self.assertRaises(ValueError):client.rpc(method)
 def test_frame_reader_handles_fragmentation_and_ping(self):
  client=CodexSession(THREAD);left,right=socket.socketpair();self.addCleanup(left.close);self.addCleanup(right.close)
  payload=json.dumps(dict(id=9,result={'ok':True})).encode();half=len(payload)//2
  right.sendall(bytes([1,half])+payload[:half]+bytes([137,1])+b'x'+bytes([128,len(payload)-half])+payload[half:])
  self.assertEqual(client.response(left,9),{'ok':True})
 def test_frame_reader_rejects_huge_payload_before_reading(self):
  client=CodexSession(THREAD);left,right=socket.socketpair();self.addCleanup(left.close);self.addCleanup(right.close)
  right.sendall(bytes([129,127])+struct.pack('!Q',8_000_001))
  with self.assertRaises(ConnectionError):client.response(left,1)

if __name__=='__main__':unittest.main()
