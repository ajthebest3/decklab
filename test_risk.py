"""Isolated account tests: never writes to the running account."""
import os,tempfile,unittest,uuid,time,concurrent.futures
TMP=tempfile.TemporaryDirectory();os.environ['MARKET_DECK_DATA']=TMP.name
import server as m
class RiskTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):m.init()
 def setUp(self):
  with m.db() as c:
   c.execute('DELETE FROM orders');c.execute('DELETE FROM positions');c.execute("UPDATE settings SET value='100000.0' WHERE key='cash'");c.execute("UPDATE settings SET value='false' WHERE key='kill_switch'");c.execute("UPDATE settings SET value='{}' WHERE key='daily_equity'")
   c.execute("INSERT OR REPLACE INTO assets VALUES('BTC/USD','Bitcoin','crypto','Global','USD','Kraken','XXBTZUSD',1)")
   c.execute("INSERT OR REPLACE INTO assets VALUES('TEST.NS','INR stock','equity','India','INR','Yahoo Finance',NULL,1)")
   m.store(c,'BTC/USD',100.,1,1000,time.time(),'test');m.store(c,'TEST.NS',100.,1,1000,time.time(),'test')
 def order(self,**kw):return m.execute_order({'symbol':'BTC/USD','side':'buy','qty':1,**kw})
 def test_fill_accounting(self):
  o=self.order();self.assertAlmostEqual(o['price'],100.05);self.assertAlmostEqual(o['fee'],.10005)
  with m.db() as c:self.assertAlmostEqual(m.setting(c,'cash'),100000-100.15005)
  self.order(side='sell')
  with m.db() as c:self.assertAlmostEqual(m.portfolio(c)['positions'].__len__(),0);self.assertLess(m.setting(c,'cash'),100000)
 def test_finite_quantity(self):
  for n in [float('nan'),float('inf'),-1,0]:
   with self.assertRaises(ValueError):self.order(qty=n)
 def test_stale(self):
  with m.db() as c:c.execute('UPDATE quotes SET asof=? WHERE symbol=?',(time.time()-180,'BTC/USD'))
  with self.assertRaisesRegex(ValueError,'stale'):self.order()
 def test_kill(self):
  with m.db() as c:c.execute("UPDATE settings SET value='true' WHERE key='kill_switch'")
  with self.assertRaisesRegex(ValueError,'stop'):self.order()
 def test_currency(self):
  with self.assertRaisesRegex(ValueError,'USD'):self.order(symbol='TEST.NS')
 def test_limit(self):
  with self.assertRaisesRegex(ValueError,'per-order'):self.order(qty=100)
 def test_no_short(self):
  with self.assertRaisesRegex(ValueError,'holdings'):self.order(side='sell')
 def test_idempotency_concurrent(self):
  rid=uuid.uuid4().hex
  with concurrent.futures.ThreadPoolExecutor(4) as pool:results=list(pool.map(lambda _:self.order(request_id=rid),range(4)))
  self.assertEqual(len(set(o['id'] for o in results)),1)
  with m.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM orders').fetchone()[0],1)
 def test_concentration(self):
  with m.db() as c:c.execute("UPDATE settings SET value='999900' WHERE key='cash'");c.execute("INSERT INTO positions VALUES('BTC/USD',100000,100)")
  with self.assertRaisesRegex(ValueError,'concentration'):self.order()
 def test_daily_loss(self):
  import json,datetime
  with m.db() as c:c.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps({'day':datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d'),'equity':102000}),'daily_equity'))
  with self.assertRaisesRegex(ValueError,'loss'):self.order()
 def test_cash(self):
  with m.db() as c:c.execute("UPDATE settings SET value='1' WHERE key='cash'")
  with self.assertRaisesRegex(ValueError,'cash'):self.order()
if __name__=='__main__':unittest.main(verbosity=2)
