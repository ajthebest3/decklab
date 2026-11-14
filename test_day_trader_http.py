"""Isolated HTTP routes; no live feeds, models or orders."""
import json,os,tempfile,threading,unittest,urllib.request,urllib.error,time
TMP=tempfile.TemporaryDirectory(prefix='day-trader-http-');os.environ['MARKET_DECK_DATA']=TMP.name
import server as s
s.init();httpd=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);s.PORT=httpd.server_port
threading.Thread(target=httpd.serve_forever,daemon=True).start();BASE='http://127.0.0.1:'+str(s.PORT)
def req(path,body=None,headers=None):
 r=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers=headers or {})
 try:
  with urllib.request.urlopen(r) as out:return out.status,out.read()
 except urllib.error.HTTPError as err:return err.code,err.read()
class HTTP(unittest.TestCase):
 def test_assets_and_status(self):
  for path in ('/day-trader','/day-trader.js','/day-trader.css','/api/day-trader'):self.assertEqual(req(path)[0],200)
 def test_locality_and_private_paths(self):
  self.assertEqual(req('/api/day-trader',headers={'Host':'public.example'})[0],403)
  self.assertEqual(req('/api/day-trader/run',{},headers={'Origin':'https://public.example'})[0],403)
  for p in ('/day_trader.py','/vendor/day-trader-skill/trader-broker/ticket.py','/data/day-trader/1/trader/config.json'):self.assertEqual(req(p)[0],404)
 def test_clock_job_and_retry(self):
  body=dict(tool='clock',symbols=[],request_id='http-clock-fixture')
  code,raw=req('/api/day-trader/run',body);self.assertEqual(code,200);jid=json.loads(raw)['id']
  for _ in range(100):
   job=json.loads(req('/api/day-trader?id='+str(jid))[1])
   if job['state']!='running':break
   time.sleep(.03)
  self.assertEqual(job['state'],'completed');self.assertIn('clock',job['result']['steps'])
  self.assertTrue(json.loads(req('/api/day-trader/run',body)[1])['reused'])
  with s.ARENA.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_orders').fetchone()[0],0)
 def test_no_order_or_execution_route(self):
  self.assertEqual(req('/api/day-trader/run',dict(tool='execute',symbols='AAPL',request_id='http-bad-fixture'))[0],400)
  self.assertEqual(req('/api/day-trader/order',{})[0],404)
if __name__=='__main__':
 try:unittest.main(verbosity=2)
 finally:httpd.shutdown();httpd.server_close();s.STOP.set()
