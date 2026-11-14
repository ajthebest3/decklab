"""Isolated cross-market execution, source freshness and funding conservation."""
import copy,json,time,unittest
from unittest.mock import patch
from datetime import datetime,timezone
import execution_markets as m
import test_population as fixtures

class MarketsTests(unittest.TestCase):
 def setUp(self):
  fixed=datetime(2026,11,5,8,30,tzinfo=timezone.utc).timestamp()
  self.clock=patch('time.time',return_value=fixed);self.clock.start();self.addCleanup(self.clock.stop)
  fixtures.PopulationTests.setUp(self)
 decision=fixtures.PopulationTests.decision
 seed_model=fixtures.PopulationTests.seed_model
 buy=fixtures.PopulationTests.buy
 later=fixtures.PopulationTests.later
 book=fixtures.PopulationTests.book
 set_cash=fixtures.PopulationTests.set_cash
 def add(self,symbol='RELIANCE.NS',kind='equity',currency='INR',provider='Yahoo Finance',price=1300):
  with self.source() as c:
   c.execute('INSERT OR REPLACE INTO assets VALUES(?,?,?,?,?,?,?,1)',(symbol,symbol,kind,'India' if symbol.endswith('.NS') else 'Global',currency,provider,symbol.replace('/','')))
   c.execute('INSERT OR REPLACE INTO quotes VALUES(?,?,1,10000000,?,?,?,\'current\')',(symbol,price,self.now,self.now,'NSE public five-level book' if symbol.endswith('.NS') else 'Kraken'))
   if provider=='Kraken':c.execute('INSERT OR REPLACE INTO demo_rules VALUES(?,8,.0001,.5,?)',(symbol,self.now))
   for off in (600,300,0):c.execute('INSERT OR REPLACE INTO history VALUES(?,?,?)',(symbol,self.now-off,price*(1-off/100000)))
  self.engine.sync_market()
 def nse(self,oid):
  self.later(oid)
  return dict(available=True,symbol='RELIANCE.NS',adapter='NSE',currency='INR',fetched=self.now,requested=self.now,source_asof=self.now-1,source='NSE public five-level book',bids=[[1299,1000]],asks=[[1300,1000]])
 def test_nse_whole_shares_native_currency_fees_and_cash_conserved(self):
  self.add();oid=self.buy(symbol='RELIANCE.NS');b=self.nse(oid)
  with self.engine.db() as c:before=c.execute('SELECT cash FROM demo_wallets WHERE bot=?',(self.bot,)).fetchone()[0]
  result=self.engine.process_book(oid,b,now=self.now)
  self.assertIsNotNone(result);self.assertEqual(result['qty'],int(result['qty']))
  with self.engine.db() as c:
   fill=dict(c.execute('SELECT * FROM demo_fills WHERE id=?',(result['fill_id'],)).fetchone());after=c.execute('SELECT cash FROM demo_wallets WHERE bot=?',(self.bot,)).fetchone()[0]
  self.assertEqual(fill['currency'],'INR');self.assertAlmostEqual(fill['usd_total'],fill['qty']*1300/94)
  self.assertAlmostEqual(before-after,fill['usd_total']+fill['fee']);self.assertEqual(json.loads(fill['evidence'])['source_asof'],self.now-1)
 def test_nse_pre_submission_snapshot_cannot_fill(self):
  self.add();oid=self.buy(symbol='RELIANCE.NS');b=self.nse(oid);b['source_asof']=self.now-20
  self.assertIsNone(self.engine.process_book(oid,b,now=self.now))
 def test_nse_stale_or_future_exchange_time_cannot_fill(self):
  self.add();oid=self.buy(symbol='RELIANCE.NS');b=self.nse(oid)
  for stamp in (self.now-121,self.now+1):
   b['source_asof']=stamp;self.assertIsNone(self.engine.process_book(oid,b,now=self.now))
 def test_nse_wrong_symbol_adapter_or_currency_cannot_fill(self):
  self.add();oid=self.buy(symbol='RELIANCE.NS');b=self.nse(oid)
  for key,value in [('symbol','TCS.NS'),('adapter','Yahoo'),('currency','USD')]:
   other={**b,key:value};self.assertIsNone(self.engine.process_book(oid,other,now=self.now))
 def test_nse_stale_fx_blocks_fill(self):
  self.add();oid=self.buy(symbol='RELIANCE.NS');b=self.nse(oid)
  with self.engine.db() as c:c.execute("UPDATE demo_fx SET asof=? WHERE currency='INR'",(self.now-3601,))
  with self.assertRaisesRegex(ValueError,'FX conversion is stale'):self.engine.process_book(oid,b,now=self.now)
 def test_nse_shared_capacity_across_bots(self):
  self.add();a=self.buy(symbol='RELIANCE.NS',key='a');other=self.engine.bot_names()[1];b=self.buy(bot=other,symbol='RELIANCE.NS',key='b');book=self.nse(a);self.later(b);book['asks'][0][1]=100
  results=[self.engine.process_book(o,book,now=self.now) for o in (a,b)]
  self.assertLessEqual(sum(r['qty'] for r in results if r),5)
 def test_xstocks_forex_and_gold_are_candidates_and_can_shadow_fill(self):
  for i,(symbol,kind) in enumerate([('AAPLx/USD','tokenized_equity'),('SPYx/USD','tokenized_etf'),('EUR/USD','forex'),('PAXG/USD','commodity_token')]):
   self.add(symbol,kind,'USD','Kraken',100)
   self.assertIn(symbol,{a['symbol'] for a in self.engine.market_context(self.bot)['markets']})
   oid=self.buy(symbol=symbol,key=symbol);self.later(oid)
   self.assertIsNotNone(self.engine.process_book(oid,self.book(),now=self.now))
 def test_research_index_and_direct_us_equity_stay_unsupported(self):
  for symbol,kind in [('AAPL','equity'),('^NSEI','index'),('GC=F','commodity')]:
   self.assertFalse(m.supported(dict(symbol=symbol,kind=kind,provider='Yahoo Finance',currency='USD')))
 def test_nse_source_parser_checks_identity_and_closed_session(self):
  depth={}
  for side in ('buy','sell'):
   depth[side+'Price1']=1300 if side=='buy' else 1301;depth[side+'Quantity1']=10
  raw={'equityResponse':[dict(orderBook={**depth,'lastPrice':1300},metaData=dict(symbol='RELIANCE',series='EQ',marketType='N',pChange=1),tradeInfo=dict(totalTradedVolume=1000),lastUpdateTime='05-Nov-2026 14:00:00')]}
  b=m.nse_book('RELIANCE.NS',lambda _:raw);self.assertTrue(b['available'])
  raw['equityResponse'][0]['lastUpdateTime']='05-Nov-2026 08:00:00';self.assertFalse(m.nse_book('RELIANCE.NS',lambda _:raw)['available'])
  raw['equityResponse'][0]['metaData']['symbol']='TCS'
  with self.assertRaisesRegex(ValueError,'mismatch'):m.nse_book('RELIANCE.NS',lambda _:raw)
 def test_ten_million_and_fifty_thousand_allocations_preserve_pnl(self):
  self.set_cash(self.bot,4900);self.engine.configure({'enabled':False});before=self.engine.status()['total']['pnl_usd']
  self.engine.configure(dict(portfolio_capital_usd=10000000,bot_allocation_usd=50000,bot_allocations={b:50000 for b in self.engine.bot_names()}))
  s=self.engine.status();self.assertEqual(s['total']['initial_usd'],10000000);self.assertEqual(s['portfolio']['reserve_usd'],9600000)
  self.assertAlmostEqual(s['total']['pnl_usd'],before);self.assertFalse(s['settings']['enabled']);self.assertTrue(all(b['initial']==50000 for b in s['bots']))

if __name__=='__main__':unittest.main(verbosity=2)
