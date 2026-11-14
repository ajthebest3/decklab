"""Population API checks against temporary databases only."""
import json,os,tempfile,threading,unittest,urllib.request,urllib.error
TMP=tempfile.TemporaryDirectory(prefix='population-http-tests-');os.environ['MARKET_DECK_DATA']=TMP.name
import server as m
m.init();httpd=m.ThreadingHTTPServer(('127.0.0.1',0),m.Handler);m.PORT=httpd.server_port
threading.Thread(target=httpd.serve_forever,daemon=True).start();BASE='http://127.0.0.1:'+str(m.PORT)
def request(path,body=None,headers=None):
 data=json.dumps(body).encode() if body is not None else None
 req=urllib.request.Request(BASE+path,data=data,headers=headers or {})
 try:
  with urllib.request.urlopen(req) as r:return r.status,json.load(r)
 except urllib.error.HTTPError as e:return e.code,json.load(e)
class PopulationHTTPTests(unittest.TestCase):
 def test_start_is_idempotent_and_separate_from_old_account(self):
  for _ in range(2):self.assertEqual(request('/api/population/start',{})[0],200)
  _,result=request('/api/population?view=summary');self.assertEqual(result['population']['active'],8);self.assertEqual(result['total']['initial_usd'],1000000)
  with m.db() as c:
   self.assertEqual(m.setting(c,'cash'),100000);self.assertEqual(c.execute('SELECT SUM(initial) FROM demo_wallets').fetchone()[0],1000000)
 def test_host_and_origin_checks_protect_population(self):
  self.assertEqual(request('/api/population',headers={'Host':'bad.example'})[0],403)
  self.assertEqual(request('/api/population/settings',{'enabled':False},{'Origin':'https://bad.example'})[0],403)
 def test_no_model_output_lifecycle_mutation_route(self):
  for path in ['/api/population/review','/api/population/kill','/api/population/fund','/api/population/order']:
   self.assertEqual(request(path,{'bot':'Codex','cash':5000})[0],404)
 def test_invalid_detail_and_filters_are_bounded(self):
  self.assertEqual(request('/api/population?kind=population_config')[0],400)
  self.assertEqual(request('/api/population?bot=unrecognized')[0],400)
  self.assertEqual(request('/api/population/detail?kind=wallets&id=1')[0],400)
 def test_population_pause_does_not_pause_original_portfolio(self):
  request('/api/population/start',{});self.assertEqual(request('/api/population/settings',{'enabled':False})[0],200)
  with m.db() as c:self.assertTrue(m.DEMO.settings(c)['enabled'])
  _,data=request('/api/population?view=summary');self.assertFalse(data['settings']['enabled'])
 def test_private_population_database_is_not_served(self):
  self.assertEqual(request('/data/population.db')[0],404)
  self.assertEqual(request('/population_engine.py')[0],404)
 def test_resume_has_no_new_grant(self):
  request('/api/population/start',{});_,before=request('/api/population?view=summary')
  request('/api/population/settings',{'enabled':False});request('/api/population/settings',{'enabled':True})
  _,after=request('/api/population?view=summary')
  self.assertEqual(before['population']['cumulative_funding_usd'],after['population']['cumulative_funding_usd'])
if __name__=='__main__':
 try:unittest.main()
 finally:httpd.shutdown();httpd.server_close();m.STOP.set()
