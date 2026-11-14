"""Isolated terminal protocol, assets and locality boundary."""
import json,os,tempfile,threading,unittest,urllib.request,urllib.error
TMP=tempfile.TemporaryDirectory(prefix='terminal-http-');os.environ['MARKET_DECK_DATA']=TMP.name
import server as s
s.init();httpd=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);s.PORT=httpd.server_port
threading.Thread(target=httpd.serve_forever,daemon=True).start();BASE='http://127.0.0.1:'+str(s.PORT)
def request(path,body=None,headers=None):
 r=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers=headers or {})
 try:
  with urllib.request.urlopen(r) as out:return out.status,out.read()
 except urllib.error.HTTPError as err:return err.code,err.read()
class TerminalHTTPTests(unittest.TestCase):
 def test_empty_terminal_works_without_starting_bots(self):
  code,raw=request('/api/terminal');self.assertEqual(code,200);value=json.loads(raw);self.assertEqual(value['markets'],[]);self.assertFalse(value['settings']['enabled'])
 def test_hosts_and_origins_are_restricted(self):
  self.assertEqual(request('/api/terminal',headers={'Host':'public.example'})[0],403)
  self.assertEqual(request('/api/terminal/research',{},headers={'Origin':'https://public.example'})[0],403)
 def test_unknown_instrument_or_parameters_cannot_create_jobs(self):
  for body in (dict(symbol='UNKNOWN',request_id='valid-fixture-request'),dict(symbol='BTC/USD',request_id='valid-fixture-request',enabled=True)):
   self.assertEqual(request('/api/terminal/research',body)[0],400)
  with s.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM terminal_briefs').fetchone()[0],0)
 def test_only_pinned_chart_bundle_and_licenses_are_served(self):
  for path in ('/terminal.js','/terminal.css','/vendor/lightweight-charts.js','/vendor/lightweight-charts.LICENSE.txt','/vendor/lightweight-charts.NOTICE.txt'):
   code,body=request(path);self.assertEqual(code,200);self.assertGreater(len(body),10)
  for path in ('/terminal_engine.py','/vendor/../../data/research-ai.json','/data/market.db'):
   self.assertEqual(request(path)[0],404)
 def test_no_terminal_execution_route(self):
  for path in ('/api/terminal/order','/api/terminal/start','/api/terminal/execute'):
   self.assertEqual(request(path,dict(enabled=True))[0],404)
if __name__=='__main__':
 try:unittest.main(verbosity=2)
 finally:httpd.shutdown();httpd.server_close();s.STOP.set()
