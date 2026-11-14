"""DeckLab HTTP contract using an empty isolated ledger and no advisor calls."""
import json,os,tempfile,threading,time,unittest,urllib.request,urllib.error
TMP=tempfile.TemporaryDirectory(prefix='decklab-http-');os.environ['MARKET_DECK_DATA']=TMP.name
import server as m
m.init()
httpd=m.ThreadingHTTPServer(('127.0.0.1',0),m.Handler);m.PORT=httpd.server_port
threading.Thread(target=httpd.serve_forever,daemon=True).start()
BASE='http://127.0.0.1:'+str(m.PORT)
def request(path,body=None,headers=None):
 return urllib.request.urlopen(urllib.request.Request(BASE+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json',**(headers or {})}),timeout=10)
class DemoHTTPTests(unittest.TestCase):
 def test_independent_funding_and_owner_journal(self):
  status=json.load(request('/api/demo?kind=orders'));self.assertEqual(status['total']['initial_usd'],1000000);self.assertEqual(len(status['bots']),2)
  self.assertEqual(json.load(request('/api/state'))['portfolio']['cash'],100000)
 def test_host_origin_restrictions_apply_to_demo(self):
  for path,body,headers in [('/api/demo',None,{'Host':'evil.example'}),('/api/demo/settings',{'enabled':False},{'Origin':'https://evil.example'})]:
   with self.assertRaises(urllib.error.HTTPError) as error:request(path,body,headers)
   self.assertEqual(error.exception.code,403)
 def test_controls_validation_and_pause_prevents_jobs(self):
  for body in [{'enabled':'false'},{'fee_rate':0},{'max_order_usd':float('nan')},{'max_positions':0}]:
   with self.assertRaises(urllib.error.HTTPError) as error:request('/api/demo/settings',body)
   self.assertEqual(error.exception.code,400)
  json.load(request('/api/demo/settings',{'enabled':False}))
  self.assertFalse(json.load(request('/api/demo/run',{'bot':'Codex'}))['started'])
 def test_no_public_order_or_wallet_mutation_endpoint(self):
  for path in ['/api/demo/orders','/api/demo/reset','/api/demo/wallet']:
   with self.assertRaises(urllib.error.HTTPError) as error:request(path,{'cash':10000000})
   self.assertEqual(error.exception.code,404)
 def test_detail_and_filters_reject_arbitrary_tables(self):
  for path in ['/api/demo?kind=wallets','/api/demo?bot=unknown','/api/demo/detail?kind=settings&id=1','/api/demo/detail?kind=fills&id=999']:
   with self.assertRaises(urllib.error.HTTPError) as error:request(path)
   self.assertEqual(error.exception.code,400)
 def test_shared_demo_javascript_is_served_without_private_sources(self):
  self.assertIn('window.demoView',request('/demo.js').read().decode())
  for path in ['/demo_engine.py','/private_advisor.py','/data/training-points.jsonl']:
   with self.assertRaises(urllib.error.HTTPError) as error:request(path)
   self.assertEqual(error.exception.code,404)
 def test_home_summary_matches_wallet_without_loading_private_journals(self):
  summary=json.load(request('/api/demo?view=summary'));full=json.load(request('/api/demo'))
  self.assertEqual(summary['total'],full['total']);self.assertEqual(summary['stats'],full['stats'])
  self.assertEqual(summary['stats']['open_positions'],0)
  self.assertNotIn('journal',summary);self.assertNotIn('decisions',summary);self.assertNotIn('policy',summary)
  self.assertIn('sim-home',request('/demo.css').read().decode())
if __name__=='__main__':
 try:unittest.main(verbosity=2)
 finally:httpd.shutdown();httpd.server_close();m.STOP.set()
