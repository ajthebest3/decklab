import os,tempfile,threading,json,urllib.request,urllib.error,time,unittest
TMP=tempfile.TemporaryDirectory();os.environ['MARKET_DECK_DATA']=TMP.name
os.environ['DECKLAB_OWNER_SENDER']='15555550123'
import server as m
m.init()
with m.db() as c:
 c.execute("INSERT OR REPLACE INTO assets VALUES('BTC/USD','Bitcoin','crypto','Global','USD','Kraken','XXBTZUSD',1)")
 m.store(c,'BTC/USD',100,1,1000,time.time(),'isolated QA')
httpd=m.ThreadingHTTPServer(('127.0.0.1',0),m.Handler);threading.Thread(target=httpd.serve_forever,daemon=True).start()
BASE='http://127.0.0.1:'+str(httpd.server_port)
def request(path,body=None,headers=None):
 h={'Content-Type':'application/json'};h.update(headers or {})
 return urllib.request.urlopen(urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers=h),timeout=20)
class HttpTests(unittest.TestCase):
 def test_assets_hidden(self):
  for path in ['/server.py','/data/market.db','/data/hermes.token','/../server.py']:
   with self.assertRaises(urllib.error.HTTPError) as err:request(path)
   self.assertEqual(err.exception.code,404)
 def test_origin(self):
  with self.assertRaises(urllib.error.HTTPError) as e:request('/api/settings',{'kill_switch':True},{'Origin':'https://evil.example'})
  self.assertEqual(e.exception.code,403)
 def test_host(self):
  with self.assertRaises(urllib.error.HTTPError) as e:request('/api/state',headers={'Host':'evil.example'})
  self.assertEqual(e.exception.code,403)
 def test_hermes_auth(self):
  with self.assertRaises(urllib.error.HTTPError) as e:request('/api/hermes',{'sender':'15555550123','action':'status'})
  self.assertEqual(e.exception.code,401)
  h={'Authorization':'Bearer '+m.TOKEN}
  with self.assertRaises(urllib.error.HTTPError) as e:request('/api/hermes',{'sender':'000','action':'status'},h)
  self.assertEqual(e.exception.code,403)
  self.assertEqual(json.load(request('/api/hermes',{'sender':'15555550123','action':'status'},h))['mode'],'paper')
 def test_order_roundtrip(self):
  body={'symbol':'BTC/USD','side':'buy','qty':.1,'request_id':'qa-http-1'}
  a=json.load(request('/api/orders',body));b=json.load(request('/api/orders',body));self.assertEqual(a['id'],b['id'])
  self.assertEqual(json.load(request('/api/state'))['portfolio']['positions'][0]['qty'],.1)
  json.load(request('/api/orders',{'symbol':'BTC/USD','side':'sell','qty':.1}))
  self.assertEqual(json.load(request('/api/state'))['portfolio']['positions'],[])
  csv=request('/api/export?table=orders').read().decode();self.assertIn('qa-http-1',csv)
 def test_alert_controls(self):
  self.assertTrue(json.load(request('/api/alerts',{'symbol':'BTC/USD','op':'above','price':110}))['ok'])
  self.assertTrue(json.load(request('/api/settings',{'max_order':1234}))['ok'])
if __name__=='__main__':
 try:unittest.main(verbosity=2)
 finally:httpd.shutdown()
