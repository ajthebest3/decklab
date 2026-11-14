"""Isolated research, watchlist, note and preflight tests. Never uses live data."""
import io,json,os,tempfile,threading,time,unittest,urllib.error,urllib.request
from unittest.mock import patch
from pathlib import Path
TMP=tempfile.TemporaryDirectory();os.environ['MARKET_DECK_DATA']=TMP.name
import server as m
m.init()
httpd=m.ThreadingHTTPServer(('127.0.0.1',0),m.Handler)
threading.Thread(target=httpd.serve_forever,daemon=True).start()
BASE='http://127.0.0.1:'+str(httpd.server_port)
def request(path,body=None):
 req=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=10) as response:return json.load(response)
def wait_brief():
 for _ in range(100):
  if not m.RESEARCH.lock.locked():return
  time.sleep(.01)
 raise AssertionError('Research thread did not finish')
class UpgradeTests(unittest.TestCase):
 def setUp(self):
  wait_brief()
  with m.db() as c:
   c.execute('DELETE FROM orders');c.execute('DELETE FROM positions');c.execute('DELETE FROM research_briefs')
   for k,v in {'cash':100000.,'daily_equity':{},'kill_switch':False,'research_enabled':True,'research_last_attempt':0,'research_provider':'auto'}.items():c.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(v),k))
   c.execute("INSERT OR REPLACE INTO assets VALUES('BTC/USD','Bitcoin','crypto','Global','USD','Kraken','XXBTZUSD',1)")
   m.store(c,'BTC/USD',100.,2.,1000.,time.time(),'isolated fixture')
  self.body={'symbol':'BTC/USD','side':'buy','qty':1}
  self.snap={'asof':time.time(),'assets':[{'symbol':'BTC/USD','price':100.,'currency':'USD','kind':'crypto','asof':time.time(),'fetched':time.time()}], 'headlines':[{'id':'headline-1','title':'Test headline','source':'QA','url':'https://example.com/news'}]}
  self.result={'summary':'Conditional QA research.','regime':'Mixed', 'ideas':[{'symbol':'BTC/USD','bias':'research long','thesis':'Observed momentum.','entry_condition':'Wait for confirmation.','invalidation':'Momentum reversal.','horizon':'Next session.','news_ids':['headline-1']}],'risks':['Prices may be stale.']}
 def test_preview_is_read_only_and_matches_fill(self):
  with m.db() as c:before={t:m.rows(c,'SELECT * FROM '+t) for t in ['settings','positions','orders','events']}
  p=request('/api/order-preview',self.body)
  with m.db() as c:after={t:m.rows(c,'SELECT * FROM '+t) for t in before}
  self.assertEqual(before,after)
  order=request('/api/orders',self.body)
  self.assertEqual(order['price'],p['price']);self.assertEqual(order['fee'],p['fee'])
  self.assertAlmostEqual(request('/api/state')['portfolio']['cash'],p['cash_after'])
 def test_preview_and_execution_share_risk_gate(self):
  for path in ['/api/order-preview','/api/orders']:
   with self.assertRaises(urllib.error.HTTPError) as err:request(path,{**self.body,'qty':100})
   self.assertEqual(err.exception.code,400);self.assertIn('per-order',json.load(err.exception)['error'])
 def test_watchlist_idempotence_and_empty_restart(self):
  body={'symbol':'BTC/USD','saved':True}
  request('/api/watchlist',body);request('/api/watchlist',body)
  self.assertEqual(request('/api/state')['watchlist'].count('BTC/USD'),1)
  for symbol in request('/api/state')['watchlist']:request('/api/watchlist',{'symbol':symbol,'saved':False})
  m.init();self.assertEqual(request('/api/state')['watchlist'],[])
 def test_watchlist_validation(self):
  for body in [{'symbol':'MISSING','saved':True},{'symbol':'BTC/USD','saved':'yes'}]:
   with self.assertRaises(urllib.error.HTTPError):request('/api/watchlist',body)
 def test_notes_roundtrip_and_validation(self):
  note='<script>untrusted & test</script>'
  request('/api/note',{'symbol':'BTC/USD','body':note})
  self.assertEqual(next(n['body'] for n in request('/api/state')['notes'] if n['symbol']=='BTC/USD'),note)
  for body in [{'symbol':'BTC/USD','body':'x'*4001},{'symbol':'MISSING','body':'note'},{'symbol':'BTC/USD','body':[]}]:
   with self.assertRaises(urllib.error.HTTPError):request('/api/note',body)
 def test_api_credentials_are_rejected_and_not_exposed(self):
  with self.assertRaises(urllib.error.HTTPError) as error:
   request('/api/research-settings',{'api_key':'qa-placeholder-secret','model':'qa-model','provider':'mirai','enabled':False})
  self.assertEqual(error.exception.code,400)
  self.assertNotIn('qa-placeholder-secret',json.dumps(request('/api/state')))
 def test_research_settings_validation(self):
  for body in [{'enabled':'yes'},{'provider':'unknown'},{'model':'../../x?key='},{'unknown':True},{'api_key':'with whitespace'}]:
   with self.assertRaises(urllib.error.HTTPError):request('/api/research-settings',body)
 def test_generated_evidence_validation(self):
  out=m.RESEARCH.validate(json.dumps(self.result),self.snap)
  self.assertEqual(out['ideas'][0]['sources'][0]['id'],'headline-1')
  self.assertEqual(out['ideas'][0]['price'],100.)
  self.result['ideas'][0]['symbol']='INVENTED'
  with self.assertRaisesRegex(ValueError,'symbol'):m.RESEARCH.validate(json.dumps(self.result),self.snap)
 def test_generated_unknown_source_rejected(self):
  self.result['ideas'][0]['news_ids']=['invented-source']
  with self.assertRaisesRegex(ValueError,'headline'):m.RESEARCH.validate(json.dumps(self.result),self.snap)
 def test_stale_research_downgraded_to_watch(self):
  self.snap['assets'][0]['asof']=time.time()-500
  out=m.RESEARCH.validate(json.dumps(self.result),self.snap)
  self.assertEqual(out['ideas'][0]['bias'],'watch');self.assertTrue(out['ideas'][0]['stale'])
 def test_thin_crypto_downgraded_to_watch(self):
  self.snap['assets'][0]['liquidity_screen_passed']=False
  out=m.RESEARCH.validate(json.dumps(self.result),self.snap)
  self.assertEqual(out['ideas'][0]['bias'],'watch');self.assertFalse(out['ideas'][0]['liquidity_screen_passed'])
 def test_invalid_model_json_rejected(self):
  for raw in ['not json','[]','{}']:
   with self.assertRaises(ValueError):m.RESEARCH.validate(raw,self.snap)
 def test_external_api_connections_are_disabled(self):
  with self.assertRaises(ValueError):m.MIRAI.request('/chat/completions',{'model':'unused'})
  self.assertFalse(m.MIRAI.status()['enabled'])
 def test_scheduler_runs_once_per_ten_minutes(self):
  with patch.object(m.RESEARCH,'snapshot',return_value=self.snap),patch.object(m.RESEARCH,'mirai',return_value=(json.dumps(self.result),'QA API','qa-model')):
   self.assertTrue(m.RESEARCH.trigger(scheduled=True)['started']);wait_brief()
   self.assertFalse(m.RESEARCH.trigger(scheduled=True)['started'])
  state=request('/api/state')['research'];self.assertEqual(len(state['briefs']),1)
  self.assertEqual(state['briefs'][0]['state'],'completed');self.assertEqual(state['interval'],600)
  with m.db() as c:last=m.setting(c,'research_last_attempt')
  self.assertEqual(state['next_run'],last+600)
 def test_pause_blocks_scheduled_not_manual(self):
  m.RESEARCH.configure({'enabled':False})
  self.assertFalse(m.RESEARCH.trigger(scheduled=True)['started'])
  with patch.object(m.RESEARCH,'snapshot',return_value=self.snap),patch.object(m.RESEARCH,'mirai',return_value=(json.dumps(self.result),'QA API','qa-model')):
   self.assertTrue(m.RESEARCH.trigger()['started']);wait_brief()
 def test_no_overlapping_jobs(self):
  entered=threading.Event();release=threading.Event()
  def provider(prompt):entered.set();release.wait(3);return json.dumps(self.result),'QA','qa-model'
  with patch.object(m.RESEARCH,'snapshot',return_value=self.snap),patch.object(m.RESEARCH,'mirai',side_effect=provider):
   m.RESEARCH.trigger();self.assertTrue(entered.wait(2))
   with self.assertRaisesRegex(ValueError,'already running'):m.RESEARCH.trigger()
   self.assertFalse(m.RESEARCH.trigger(scheduled=True)['started']);release.set();wait_brief()
 def test_failed_api_uses_truthful_codex_fallback(self):
  with patch.object(m.RESEARCH,'snapshot',return_value=self.snap),patch.object(m.RESEARCH,'mirai',side_effect=ValueError('Mirai API returned HTTP 401.')),patch.object(m.RESEARCH,'codex',return_value=(json.dumps(self.result),'Local Codex','CLI')):
   m.RESEARCH.trigger();wait_brief()
  brief=request('/api/state')['research']['briefs'][0]
  self.assertEqual(brief['provider'],'Local Codex');self.assertIn('401',json.loads(brief['result'])['fallback_reason'])
 def test_failure_recorded_without_tight_retry(self):
  with patch.object(m.RESEARCH,'snapshot',return_value=self.snap),patch.object(m.RESEARCH,'mirai',side_effect=ValueError('API unavailable')),patch.object(m.RESEARCH,'codex',side_effect=ValueError('CLI unavailable')):
   m.RESEARCH.trigger(scheduled=True);wait_brief();self.assertFalse(m.RESEARCH.trigger(scheduled=True)['started'])
  brief=request('/api/state')['research']['briefs'][0];self.assertEqual(brief['state'],'failed');self.assertEqual(brief['error'],'CLI unavailable')
if __name__=='__main__':
 try:unittest.main(verbosity=2)
 finally:httpd.shutdown()
