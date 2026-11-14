"""Android push protocol checks. All writes use an isolated temporary database."""
import json, os, tempfile, threading, time, unittest, urllib.request, urllib.error
TMP=tempfile.TemporaryDirectory(prefix='market-deck-mobile-qa-')
os.environ['MARKET_DECK_DATA']=TMP.name
import server as m
from mobile_events import batch
m.init()
httpd=m.ThreadingHTTPServer(('127.0.0.1',0),m.Handler)
threading.Thread(target=httpd.serve_forever,daemon=True).start()
BASE='http://127.0.0.1:'+str(httpd.server_port)

def request(path,headers=None):return urllib.request.urlopen(urllib.request.Request(BASE+path,headers=headers or {}),timeout=8)
def frame(stream):
 result={}
 while True:
  line=stream.readline().decode().strip()
  if not line:return result
  key,value=line.split(': ',1);result[key]=json.loads(value) if key=='data' else value

class MobileTests(unittest.TestCase):
 def setUp(self):
  with m.db() as c:c.execute('DELETE FROM events');c.execute('DELETE FROM research_briefs')
 def test_only_meaningful_events_notify(self):
  with m.db() as c:
   m.event(c,'alert','Price alert created',{'symbol':'BTC/USD'})
   m.event(c,'research','Research schedule settings updated')
   m.event(c,'system','Restarted')
   self.assertEqual(batch(c)['items'],[])
   m.event(c,'alert_triggered','BTC/USD crossed above 100')
   m.event(c,'order','PAPER BUY 0.1 BTC/USD')
   items=batch(c)['items'];self.assertEqual([i['category'] for i in items],['price','orders'])
   self.assertEqual(items[-1]['route'],'portfolio')
 def test_completed_and_failed_briefs(self):
  with m.db() as c:
   for state in ['completed','failed']:
    cursor=c.execute('INSERT INTO research_briefs(state,result) VALUES(?,?)',(state,json.dumps({'summary':'Isolated research summary'})))
    m.event(c,'research','Brief state updated',{'brief_id':cursor.lastrowid,'error':'private provider detail'})
   items=batch(c)['items'];self.assertEqual(len(items),2)
   self.assertEqual(items[0]['body'],'Isolated research summary')
   self.assertNotIn('private',json.dumps(items[1]))
 def test_cursor_advances_across_filtered_events(self):
  with m.db() as c:
   for i in range(125):m.event(c,'system',str(i))
   page=batch(c,0);self.assertEqual(page['cursor'],100);self.assertEqual(page['items'],[])
   self.assertEqual(batch(c,page['cursor'])['cursor'],125)
 def test_first_connect_avoids_old_alerts(self):
  with m.db() as c:m.event(c,'order','PAPER historical fill')
  with request('/api/mobile/stream') as r:
   event=frame(r);self.assertEqual(event['event'],'ready');self.assertEqual(event['data']['cursor'],1)
 def test_reconnect_replays_and_then_advances(self):
  with m.db() as c:
   m.event(c,'system','Filtered event');m.event(c,'alert_triggered','BTC/USD crossed above 100')
  with request('/api/mobile/stream',{'Last-Event-ID':'0'}) as r:
   self.assertEqual(frame(r)['event'],'ready')
   event=frame(r);self.assertEqual(event['event'],'notification');self.assertEqual(event['id'],'2');self.assertEqual(event['data']['category'],'price')
   self.assertEqual(frame(r)['data']['cursor'],2)
 def test_bad_cursor_and_host_rejected(self):
  for cursor in ['-1','not-a-number',str(2**64)]:
   with self.assertRaises(urllib.error.HTTPError) as e:request('/api/mobile/stream',{'Last-Event-ID':cursor})
   self.assertEqual(e.exception.code,400)
  with self.assertRaises(urllib.error.HTTPError) as e:request('/api/mobile/stream',{'Host':'evil.example'})
  self.assertEqual(e.exception.code,403)
 def test_journal_persists_across_connection_and_restart(self):
  with m.db() as c:m.event(c,'alert_triggered','Persistent price crossing')
  first=json.load(request('/api/mobile/notifications'));m.init()
  second=json.load(request('/api/mobile/notifications'))
  self.assertEqual(first['items'],second['items'])
 def test_source_and_keys_not_downloadable(self):
  for path in ['/android/app/build.gradle','/android/../data/android-release.jks','/android/dist/market-deck.apk','/data/android-signing.json']:
   with self.assertRaises(urllib.error.HTTPError) as e:request(path)
   self.assertEqual(e.exception.code,404)

if __name__=='__main__':
 try:unittest.main(verbosity=2)
 finally:m.STOP.set();httpd.shutdown();httpd.server_close()
