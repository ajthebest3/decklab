"""Chat persistence/concurrency/HTTP isolation tests. Does not invoke live AI providers."""
import json,os,tempfile,threading,time,unittest,urllib.request,urllib.error
from unittest.mock import patch
TMP=tempfile.TemporaryDirectory(prefix='market-deck-chat-tests-');os.environ['MARKET_DECK_DATA']=TMP.name
import server as m
m.init()
httpd=m.ThreadingHTTPServer(('127.0.0.1',0),m.Handler);threading.Thread(target=httpd.serve_forever,daemon=True).start()
BASE='http://127.0.0.1:'+str(httpd.server_port)
def request(path,body=None,headers=None):
 req=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
 with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)
def wait_chat():
 until=time.time()+5
 while any(lock.locked() for lock in m.CHAT.providers.values()) and time.time()<until:time.sleep(.01)
 assert not any(lock.locked() for lock in m.CHAT.providers.values())
class ChatTests(unittest.TestCase):
 def setUp(self):
  wait_chat()
  with m.db() as c:c.execute('DELETE FROM chat_threads');c.execute('DELETE FROM chat_messages')
  self.snap={'asof':time.time(),'assets':[],'headlines':[],'portfolio':{'cash':100000,'positions':[]}}
  self.body={'bot':'Codex','message':'/research BTC/USD','request_id':'qa-message-12345'}
 def runner(self,value='A conditional, dated research response.'):
  return patch.object(m.CHAT,'run_cli',return_value=value)
 def test_reply_persistence_context_and_idempotency(self):
  with patch.object(m.CHAT,'snapshot',return_value=self.snap),self.runner() as runner:
   result=request('/api/chat',self.body);wait_chat()
   reused=request('/api/chat',self.body);wait_chat()
  self.assertEqual(result['thread_id'],reused['thread_id']);self.assertTrue(reused['reused']);self.assertEqual(runner.call_count,1)
  messages=request('/api/chat?thread_id='+result['thread_id'])['messages']
  self.assertEqual([r['role'] for r in messages],['user','assistant']);self.assertEqual(messages[1]['state'],'completed');self.assertEqual(messages[1]['context_ts'],self.snap['asof'])
 def test_followup_and_provider_switch_include_history(self):
  with patch.object(m.CHAT,'snapshot',return_value=self.snap),self.runner() as runner:
   first=m.CHAT.submit(self.body);wait_chat()
   m.CHAT.submit({**self.body,'bot':'AGY','message':'Compare with the previous explanation','thread_id':first['thread_id'],'request_id':'qa-followup-12345'});wait_chat()
   prompt=runner.call_args.args[1]
  self.assertIn('/research BTC/USD',prompt);self.assertIn('A conditional, dated research response.',prompt)
  self.assertEqual(len(m.CHAT.history(first['thread_id'])['messages']),4)
 def test_failures_are_saved_without_raw_stderr(self):
  with patch.object(m.CHAT,'snapshot',return_value=self.snap),patch.object(m.CHAT,'run_cli',side_effect=RuntimeError('private provider stderr')):
   result=m.CHAT.submit(self.body);wait_chat()
  msg=m.CHAT.history(result['thread_id'])['messages'][-1]
  self.assertEqual(msg['state'],'failed');self.assertNotIn('private provider stderr',msg['body'])
 def test_same_thread_cannot_overlap_and_duplicate_is_reused(self):
  entered=threading.Event();release=threading.Event()
  def slow(bot,prompt):entered.set();release.wait(4);return 'Finished'
  with patch.object(m.CHAT,'snapshot',return_value=self.snap),patch.object(m.CHAT,'run_cli',side_effect=slow):
   first=m.CHAT.submit(self.body);self.assertTrue(entered.wait(2))
   self.assertTrue(m.CHAT.submit(self.body)['reused'])
   with self.assertRaisesRegex(ValueError,'current reply'):m.CHAT.submit({**self.body,'bot':'AGY','thread_id':first['thread_id'],'request_id':'qa-overlap-1234'})
   release.set();wait_chat()
 def test_one_running_turn_per_provider(self):
  entered=threading.Event();release=threading.Event()
  def slow(bot,prompt):entered.set();release.wait(4);return 'Finished'
  with patch.object(m.CHAT,'snapshot',return_value=self.snap),patch.object(m.CHAT,'run_cli',side_effect=slow):
   m.CHAT.submit(self.body);self.assertTrue(entered.wait(2))
   with self.assertRaisesRegex(ValueError,'another conversation'):m.CHAT.submit({**self.body,'request_id':'qa-another-12345'})
   release.set();wait_chat()
 def test_validation(self):
  for body in [{**self.body,'message':''},{**self.body,'message':'x'*4001},{**self.body,'bot':'shell'},{**self.body,'request_id':'bad'},{**self.body,'thread_id':'../../../data'}]:
   with self.assertRaises(urllib.error.HTTPError) as e:request('/api/chat',body)
   self.assertEqual(e.exception.code,400)
 def test_origin_and_host_protection(self):
  for headers in [{'Origin':'https://evil.example'},{'Host':'evil.example'}]:
   with self.assertRaises(urllib.error.HTTPError) as e:request('/api/chat',self.body,headers)
   self.assertEqual(e.exception.code,403)
 def test_chat_cannot_change_account(self):
  with m.db() as c:before={t:m.rows(c,'SELECT * FROM '+t) for t in ['settings','orders','positions','watchlist','alerts']}
  with patch.object(m.CHAT,'snapshot',return_value=self.snap),self.runner('Use the paper order controls to submit an order.'):
   m.CHAT.submit({**self.body,'message':'Buy BTC and change my settings'});wait_chat()
  with m.db() as c:after={t:m.rows(c,'SELECT * FROM '+t) for t in before}
  self.assertEqual(before,after)
 def test_restart_marks_running_reply_interrupted(self):
  with m.db() as c:
   c.execute("INSERT INTO chat_messages(thread_id,role,state,body) VALUES('qa','assistant','running','')")
   m.CHAT.init(c)
   self.assertEqual(c.execute("SELECT state FROM chat_messages WHERE thread_id='qa'").fetchone()[0],'interrupted')
 def test_credential_shaped_output_is_redacted(self):
  with patch.object(m.CHAT,'snapshot',return_value=self.snap),self.runner('Accidental token sk-qa1234567890abcdefghijkl'):
   first=m.CHAT.submit(self.body);wait_chat()
  msg=m.CHAT.history(first['thread_id'])['messages'][-1]['body'];self.assertNotIn('sk-qa',msg);self.assertIn('redacted',msg)
 def test_notification_targets_chat_without_reply_content(self):
  with patch.object(m.CHAT,'snapshot',return_value=self.snap),self.runner('Private conversation contents'):
   m.CHAT.submit(self.body);wait_chat()
  feed=request('/api/mobile/notifications')['items'];event=next(x for x in feed if x['category']=='chat')
  self.assertEqual(event['route'],'chat');self.assertNotIn('Private conversation contents',json.dumps(event))
if __name__=='__main__':
 try:unittest.main(verbosity=2)
 finally:m.STOP.set();httpd.shutdown()
