"""DeckLab isolated accounting, timing, liquidity, reward and observation tests."""
import json,os,tempfile,time,threading,unittest
from unittest.mock import patch
TMP=tempfile.TemporaryDirectory(prefix='decklab-tests-');os.environ['MARKET_DECK_DATA']=TMP.name
import server as m
import demo_learning as learning
m.init()

class DemoTests(unittest.TestCase):
 def setUp(self):
  self.now=time.time();m.DEMO.error=''
  with m.db() as c:
   for name in ['demo_wallets','demo_settings','demo_decisions','demo_orders','demo_positions','demo_fills','demo_cash_ledger','demo_rewards','demo_marks','demo_liquidity','demo_rules','demo_fx','demo_equity','demo_activity','demo_policy','demo_learning','demo_policy_seen','demo_strategy_reviews']:c.execute('DELETE FROM '+name)
   m.DEMO.init(c)
   c.execute("DELETE FROM assets WHERE symbol LIKE 'QP%/USD'")
   c.execute("INSERT OR REPLACE INTO assets VALUES('BTC/USD','Bitcoin','crypto','Global','USD','Kraken','XXBTZUSD',1)")
   c.execute("INSERT OR REPLACE INTO assets VALUES('QASTOCK','Test USD share','equity','US','USD','Yahoo Finance',NULL,1)")
   c.execute("DELETE FROM history WHERE symbol='BTC/USD' OR symbol LIKE 'QP%/USD'")
   m.store(c,'BTC/USD',100,2,100000,self.now,'isolated fixture');m.store(c,'QASTOCK',100,1,100000,self.now,'isolated fixture')
   c.execute("INSERT INTO demo_rules VALUES('BTC/USD',6,0.001,1,?)",(self.now,))
   c.execute("INSERT INTO demo_fx VALUES('INR',84,?,?,?)",(self.now,self.now,'isolated FX fixture'))
  m.DEMO.last_policy_quote={};m.DEMO.cached_books={}
  # Accounting/rate tests isolate their existing subject from admission-policy checks.
  self.admission_patch=patch.object(m.DEMO,'entry_safety',return_value=None);self.admission_patch.start();self.addCleanup(self.admission_patch.stop)
 def order(self,bot='Codex',side='buy',key='qa-order-1',symbol='BTC/USD',size='trial'):
  return m.DEMO.submit(bot,symbol,side,size,'crypto|up|normal|neutral','Isolated test decision',None,key)
 def later(self,oid,seconds=5):
  with m.db() as c:c.execute('UPDATE demo_orders SET created=?,earliest=? WHERE id=?',(self.now-seconds,self.now-seconds+3,oid))
 def book(self,bid=99.9,ask=100.1,visible=1000,stamp=None):
  return {'available':True,'source':'isolated observed-book fixture','fetched':self.now if stamp is None else stamp,'bids':[[bid,visible]],'asks':[[ask,visible]]}
 def totals(self):
  with m.db() as c:return m.DEMO.valuation(c)
 def test_funding_is_separate_and_restart_is_idempotent(self):
  with m.db() as c:
   original=m.setting(c,'cash');m.DEMO.init(c);wallets=m.rows(c,'SELECT * FROM demo_wallets');funding=c.execute('SELECT SUM(amount) FROM demo_cash_ledger').fetchone()[0]
  self.assertEqual(sum(w['cash'] for w in wallets),1000000);self.assertEqual(funding,1000000);self.assertEqual(original,100000)
 def test_queue_is_not_an_instant_fill(self):
  oid=self.order();self.assertIsNone(m.DEMO.process_book(oid,self.book(),now=self.now))
  with m.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_fills').fetchone()[0],0)
 def test_pre_submission_stale_and_future_books_do_not_fill(self):
  oid=self.order();self.later(oid)
  for stamp in [self.now-30,self.now+20,self.now-10]:self.assertIsNone(m.DEMO.process_book(oid,self.book(stamp=stamp),now=self.now))
 def test_observed_fill_fee_and_cash_conservation(self):
  oid=self.order();self.later(oid);result=m.DEMO.process_book(oid,self.book(),now=self.now);self.assertEqual(result['state'],'filled')
  with m.db() as c:
   wallet=c.execute("SELECT cash FROM demo_wallets WHERE bot='Codex'").fetchone()[0];position=c.execute("SELECT cost FROM demo_positions WHERE bot='Codex'").fetchone()[0];ledger=c.execute("SELECT SUM(amount) FROM demo_cash_ledger WHERE bot='Codex'").fetchone()[0];fill=c.execute('SELECT * FROM demo_fills').fetchone()
   self.assertAlmostEqual(wallet+position,500000,places=6);self.assertAlmostEqual(wallet,ledger,places=6);self.assertAlmostEqual(fill['fee'],fill['usd_total']*m.DEMO.settings(c)['fee_rate'],places=6)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_learning').fetchone()[0],0)
 def test_small_depth_partial_fill_and_no_snapshot_reuse(self):
  oid=self.order();self.later(oid);book=self.book(visible=1);first=m.DEMO.process_book(oid,book,now=self.now);self.assertEqual(first['state'],'partial');self.assertLessEqual(first['qty'],.05)
  self.assertIsNone(m.DEMO.process_book(oid,book,now=self.now+1))
  self.assertIsNone(m.DEMO.process_book(oid,self.book(visible=1,stamp=self.now+2),now=self.now+2))
 def test_shared_liquidity_prevents_two_bots_reusing_depth(self):
  a=self.order('Codex',key='bot-a');b=self.order('AGY',key='bot-b');self.later(a);self.later(b);book=self.book(visible=1)
  m.DEMO.process_book(a,book,now=self.now);m.DEMO.process_book(b,book,now=self.now)
  with m.db() as c:self.assertLessEqual(c.execute('SELECT SUM(qty) FROM demo_fills').fetchone()[0],.05+1e-10)
 def test_replenishment_adds_only_observed_new_capacity(self):
  oid=self.order();self.later(oid);m.DEMO.process_book(oid,self.book(visible=1),now=self.now)
  result=m.DEMO.process_book(oid,self.book(visible=2,stamp=self.now+2),now=self.now+2)
  self.assertAlmostEqual(result['qty'],.05,places=6)
 def test_profit_reward_and_terminal_q_are_real_and_once(self):
  buy=self.order();self.later(buy);m.DEMO.process_book(buy,self.book(),now=self.now)
  sell=self.order(side='sell',key='exit');self.later(sell)
  result=m.DEMO.process_book(sell,self.book(bid=104,ask=104.1,stamp=self.now+2),now=self.now+2);self.assertEqual(result['points'],1)
  self.assertIsNone(m.DEMO.process_book(sell,self.book(bid=104,ask=104.1,stamp=self.now+3),now=self.now+3))
  with m.db() as c:
   reward=c.execute('SELECT * FROM demo_rewards').fetchone();update=c.execute('SELECT * FROM demo_learning').fetchone()
   self.assertGreater(reward['net_usd'],0);self.assertEqual(update['points'],1);self.assertAlmostEqual(update['new_q'],.2);self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_learning').fetchone()[0],1)
 def test_loss_reward_is_minus_five_after_costs(self):
  buy=self.order();self.later(buy);m.DEMO.process_book(buy,self.book(),now=self.now)
  sell=self.order(side='sell',key='exit');self.later(sell);result=m.DEMO.process_book(sell,self.book(stamp=self.now+2),now=self.now+2);self.assertEqual(result['points'],-5)
  with m.db() as c:self.assertAlmostEqual(c.execute('SELECT q FROM demo_policy').fetchone()[0],-1.)
 def test_position_and_wallet_reservations(self):
  m.DEMO.configure({'max_positions':1});self.order()
  with self.assertRaisesRegex(ValueError,'position limit'):self.order(key='different',symbol='QASTOCK')
 def test_pause_cancels_queued_orders(self):
  oid=self.order();m.DEMO.configure({'enabled':False});self.later(oid);self.assertIsNone(m.DEMO.process_book(oid,self.book(),now=self.now))
  with m.db() as c:self.assertEqual(c.execute('SELECT state FROM demo_orders WHERE id=?',(oid,)).fetchone()[0],'cancelled')
 def test_unsupported_equity_is_not_filled_at_its_close(self):
  oid=self.order(symbol='QASTOCK');self.later(oid);self.assertIsNone(m.DEMO.process_book(oid,self.book(),now=self.now))
  with m.db() as c:self.assertEqual(c.execute('SELECT state FROM demo_orders WHERE id=?',(oid,)).fetchone()[0],'awaiting_data')
 def test_currency_dual_display_is_same_ledger(self):
  value=self.totals();self.assertEqual(value['total']['equity_usd'],1000000);self.assertEqual(value['total']['equity_inr'],84000000)
  with m.db() as c:self.assertEqual(m.DEMO.fx(c,'INR')[0],1/84)
 def test_stale_fx_is_labelled_and_blocks_execution_conversion(self):
  with m.db() as c:
   c.execute("UPDATE demo_fx SET asof=? WHERE currency='INR'",(self.now-7200,))
   with self.assertRaisesRegex(ValueError,'stale'):m.DEMO.fx(c,'INR',execution=True)
  self.assertTrue(self.totals()['fx']['stale']);self.assertEqual(self.totals()['total']['equity_inr'],84000000)
 def test_observation_has_no_private_account_fields(self):
  observation=m.DEMO.market_context('Codex')
  forbidden={'cash','initial','equity','pnl','pnl_usd','profit','loss','cost','entry_price','entry_cost','realized','realized_usd','portfolio','balance','fills','execution_prices'}
  def check(value):
   if isinstance(value,dict):
    self.assertFalse(forbidden.intersection(value));[check(v) for v in value.values()]
   elif isinstance(value,list):[check(v) for v in value]
  check(observation);self.assertNotIn('500000',m.DEMO.advisor_prompt(observation));self.assertNotIn('1000000',m.DEMO.advisor_prompt(observation).split('OBSERVATION_JSON: ')[0])
 def test_action_validation_blocks_unobserved_symbols_and_sources(self):
  obs=m.DEMO.market_context('Codex');result={'regime':'neutral','summary':'Conditional observation','actions':[{'symbol':'UNKNOWN','action':'buy','size':'small','reason':'Test','headline_ids':[]}]}
  with self.assertRaises(ValueError):m.DEMO.validate(json.dumps(result),obs)
  result['actions'][0]['symbol']='BTC/USD';result['actions'][0]['headline_ids']=['invented']
  with self.assertRaises(ValueError):m.DEMO.validate(json.dumps(result),obs)
 def test_learner_rejects_dollar_rewards(self):
  with m.db() as c:
   with self.assertRaises(ValueError):learning.learn(c,'Codex',999,'context',123.45)
 def test_order_request_idempotency(self):
  first=self.order();self.assertEqual(first,self.order())
  with m.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_orders').fetchone()[0],1)
 def test_failed_rules_and_invalid_depth_cannot_produce_profit(self):
  oid=self.order();self.later(oid)
  with m.db() as c:c.execute('DELETE FROM demo_rules')
  self.assertIsNone(m.DEMO.process_book(oid,self.book(),now=self.now));self.assertEqual(self.totals()['total']['equity_usd'],1000000)
 def test_accounting_does_not_touch_original_tables(self):
  with m.db() as c:before={name:m.rows(c,'SELECT * FROM '+name) for name in ['positions','orders','settings']}
  oid=self.order();self.later(oid);m.DEMO.process_book(oid,self.book(),now=self.now)
  with m.db() as c:after={name:m.rows(c,'SELECT * FROM '+name) for name in before}
  self.assertEqual(before,after)
 def test_points_and_all_transactions_are_inspectable(self):
  oid=self.order();self.later(oid);fill=m.DEMO.process_book(oid,self.book(),now=self.now);status=m.DEMO.status();detail=m.DEMO.detail('fills',fill['fill_id'])
  self.assertEqual(status['journal']['total'],1);evidence=json.loads(detail['evidence']);self.assertGreaterEqual(evidence['snapshot_time'],evidence['earliest_allowed']);self.assertEqual(evidence['levels'][0]['price'],100.1)
 def test_future_quote_is_not_a_valid_entry_observation(self):
  with m.db() as c:c.execute("UPDATE quotes SET asof=? WHERE symbol='BTC/USD'",(self.now+30,))
  with self.assertRaisesRegex(ValueError,'future'):self.order()
 def test_invalid_crossed_unsorted_or_duplicate_depth(self):
  oid=self.order();self.later(oid)
  self.assertIsNone(m.DEMO.process_book(oid,self.book(bid=101,ask=100),now=self.now))
  for levels in [[[100.1,1],[100,1]],[[100.1,1],[100.1,1]],[[float('nan'),1]]]:
   book=self.book();book['asks']=levels
   with self.assertRaises(ValueError):m.DEMO.process_book(oid,book,now=self.now)
  with m.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_fills').fetchone()[0],0)
 def test_timeout_keeps_a_partially_filled_position_without_reward(self):
  oid=self.order();self.later(oid);m.DEMO.process_book(oid,self.book(visible=1),now=self.now)
  self.assertIsNone(m.DEMO.process_book(oid,self.book(stamp=self.now+301),now=self.now+301))
  with m.db() as c:
   self.assertEqual(c.execute('SELECT state FROM demo_orders WHERE id=?',(oid,)).fetchone()[0],'expired')
   self.assertGreater(c.execute('SELECT qty FROM demo_positions').fetchone()[0],0)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_rewards').fetchone()[0],0)
 def test_partial_exit_rewards_only_when_fully_closed_and_conserves_cash(self):
  buy=self.order();self.later(buy);m.DEMO.process_book(buy,self.book(),now=self.now)
  sell=self.order(side='sell',key='partial-exit');self.later(sell)
  part=m.DEMO.process_book(sell,self.book(bid=104,ask=104.1,visible=10,stamp=self.now+2),now=self.now+2)
  self.assertEqual(part['state'],'partial');self.assertIsNone(part['points'])
  with m.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_learning').fetchone()[0],0)
  done=m.DEMO.process_book(sell,self.book(bid=104,ask=104.1,visible=1000,stamp=self.now+4),now=self.now+4)
  self.assertEqual(done['state'],'filled');self.assertEqual(done['points'],1)
  with m.db() as c:
   net=c.execute('SELECT net_usd FROM demo_rewards').fetchone()[0]
   cash=c.execute("SELECT cash FROM demo_wallets WHERE bot='Codex'").fetchone()[0]
   realized=c.execute('SELECT SUM(realized) FROM demo_fills').fetchone()[0]
   self.assertAlmostEqual(cash-500000,net,places=7);self.assertAlmostEqual(realized,net,places=7)
 def test_concurrent_snapshot_processing_is_atomic(self):
  oid=self.order();self.later(oid);results=[]
  def fill():results.append(m.DEMO.process_book(oid,self.book(),now=self.now))
  threads=[threading.Thread(target=fill) for _ in range(3)]
  for thread in threads:thread.start()
  for thread in threads:thread.join()
  self.assertEqual(sum(r is not None for r in results),1)
 def test_restart_preserves_ledger_and_interrupts_only_running_decisions(self):
  oid=self.order();self.later(oid);m.DEMO.process_book(oid,self.book(),now=self.now)
  with m.db() as c:
   before={name:m.rows(c,'SELECT * FROM '+name) for name in ['demo_wallets','demo_positions','demo_cash_ledger','demo_fills','demo_orders']}
   c.execute("INSERT INTO demo_decisions(bot,created,state) VALUES('Codex',?,'running')",(self.now,))
   m.DEMO.init(c)
   after={name:m.rows(c,'SELECT * FROM '+name) for name in before}
   self.assertEqual(before,after);self.assertEqual(c.execute('SELECT state FROM demo_decisions').fetchone()[0],'interrupted')
 def test_invalid_settings_roll_back_the_complete_request(self):
  with self.assertRaises(ValueError):m.DEMO.configure({'max_order_usd':2000,'enabled':'false'})
  with m.db() as c:self.assertEqual(m.DEMO.settings(c)['max_order_usd'],25000)
 def test_book_requested_before_execution_window_is_rejected(self):
  oid=self.order();self.later(oid);book=self.book();book['requested']=self.now-10
  self.assertIsNone(m.DEMO.process_book(oid,book,now=self.now))
 def test_older_book_cannot_replenish_another_bots_liquidity(self):
  first=self.order('Codex',key='first');second=self.order('AGY',key='second');self.later(first);self.later(second)
  m.DEMO.process_book(first,self.book(visible=1,stamp=self.now+4),now=self.now+4)
  self.assertIsNone(m.DEMO.process_book(second,self.book(visible=200,stamp=self.now+2),now=self.now+5))
 def test_filters_pagination_and_detail_are_bounded(self):
  with m.db() as c:
   for index in range(65):m.DEMO.log(c,'Codex' if index%2 else 'AGY','qa','Isolated journal row')
  status=m.DEMO.status({'kind':['activity'],'bot':['Codex'],'page':['1']})
  self.assertEqual(status['journal']['total'],32);self.assertEqual(len(status['journal']['items']),2)
  for params in [{'kind':['demo_wallets']},{'bot':['unknown']},{'page':['NaN']}]:
   with self.assertRaises(ValueError):m.DEMO.status(params)
  with self.assertRaises(ValueError):m.DEMO.detail('wallets',1)
 def test_training_export_contains_real_point_outcome_without_dollar_accounting(self):
  from training.export_points import export
  observation=m.DEMO.market_context('Codex')
  with m.db() as c:did=c.execute("INSERT INTO demo_decisions(bot,created,state,context_ts,input_json) VALUES('Codex',?,'completed',?,?)",(self.now,self.now,json.dumps(observation))).lastrowid
  buy=m.DEMO.submit('Codex','BTC/USD','buy','trial','context','Initial bounded RL exploration; isolated test',did,'export-entry');self.later(buy);m.DEMO.process_book(buy,self.book(),now=self.now)
  path=os.path.join(TMP.name,'export-points.jsonl');self.assertEqual(export(m.DB,path),0)
  sell=self.order(side='sell',key='export-exit');self.later(sell);m.DEMO.process_book(sell,self.book(stamp=self.now+2),now=self.now+2)
  self.assertEqual(export(m.DB,path),1)
  with open(path) as source:sample=json.loads(source.read())
  self.assertEqual(sample['reward'],-5);self.assertEqual(sample['behavior_policy'],'initial_rl_exploration')
  self.assertNotIn('net_usd',sample);self.assertNotIn('cash',sample['observation']);self.assertTrue(sample['terminal'])
 def test_float_roundoff_does_not_strand_the_final_executable_lot(self):
  from demo_engine import floor_qty
  self.assertEqual(floor_qty(9.99999993922529e-9,8),1e-8)
  self.assertEqual(floor_qty(.9e-8,8),0)
  buy=self.order();self.later(buy);m.DEMO.process_book(buy,self.book(),now=self.now)
  with m.db() as c:
   c.execute("UPDATE demo_rules SET decimals=8 WHERE symbol='BTC/USD'")
   c.execute("UPDATE demo_positions SET qty=9.99999993922529e-9 WHERE bot='Codex'")
  sell=self.order(side='sell',key='tiny-final-lot');self.later(sell)
  result=m.DEMO.process_book(sell,self.book(stamp=self.now+2),now=self.now+2)
  self.assertEqual(result['state'],'filled');self.assertEqual(result['qty'],1e-8)
  with m.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_learning').fetchone()[0],1)
 def seed_policy_market(self,count=5):
  with m.db() as c:
   for i in range(count):
    symbol='QP'+str(i)+'/USD'
    c.execute('INSERT OR REPLACE INTO assets VALUES(?,?,?,?,?,?,?,1)',(symbol,symbol,'crypto','Global','USD','Kraken','QP'+str(i)))
    m.store(c,symbol,100,2+i/10,100000,self.now,'isolated candidate fixture')
    c.execute('INSERT OR REPLACE INTO demo_rules VALUES(?,?,?,?,?)',(symbol,6,.001,1,self.now))
   result={'regime':'neutral','summary':'Isolated genuine advisor adapter result','actions':[],'policy':{'exploration_rate':.1,'min_change':-5,'batch_size':8,'hold_seconds':120}}
   for bot in ('Codex','AGY'):
    c.execute("INSERT INTO demo_decisions(bot,created,finished,state,result,source) VALUES(?,?,?,'completed',?,'advisor')",(bot,self.now,self.now,json.dumps(result)))
 def test_fast_policy_queues_multiple_orders_without_dollar_observations(self):
  self.seed_policy_market();orders=m.DEMO.fast_policy('Codex');self.assertGreaterEqual(len(orders),5)
  with m.db() as c:
   record=c.execute("SELECT * FROM demo_decisions WHERE source='point_policy'").fetchone();obs=json.loads(record['input_json'])
   self.assertNotIn('cash',obs);self.assertNotIn('portfolio',obs);self.assertNotIn('entry_price',json.dumps(obs))
   self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_fills').fetchone()[0],0)
   self.assertLessEqual(c.execute('SELECT SUM(remaining) FROM demo_orders').fetchone()[0],500000)
  self.assertEqual(m.DEMO.fast_policy('Codex'),[])
 def test_per_second_admission_limit_is_shared_and_atomic(self):
  self.seed_policy_market(10);m.DEMO.configure({'max_orders_per_second':3});results=[]
  def submit(index):
   try:results.append(m.DEMO.submit('Codex' if index%2 else 'AGY','QP'+str(index)+'/USD','buy','policy','test','Isolated burst',None,'burst-'+str(index)))
   except ValueError as e:self.assertIn('Per-second',str(e))
  with patch('demo_engine.time.time',return_value=self.now+.1):
   threads=[threading.Thread(target=submit,args=(i,)) for i in range(8)]
   for t in threads:t.start()
   for t in threads:t.join()
  self.assertEqual(len(results),3)
  with m.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_orders').fetchone()[0],3)
 def test_policy_batches_do_not_delay_real_advisor_schedule(self):
  self.seed_policy_market();m.DEMO.fast_policy('Codex')
  with m.db() as c:c.execute("UPDATE demo_decisions SET created=? WHERE source='advisor'",(self.now-601,))
  with patch.object(m.DEMO,'advisor',return_value=json.dumps({'regime':'neutral','summary':'Actual test adapter strategy review','actions':[],'policy':{'batch_size':3,'hold_seconds':180}})):
   started=m.DEMO.trigger('Codex');self.assertTrue(started['started'])
   deadline=time.time()+3
   while m.DEMO.locks['Codex'].locked() and time.time()<deadline:time.sleep(.01)
  with m.db() as c:
   self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_strategy_reviews').fetchone()[0],1)
   params=json.loads(c.execute('SELECT parameters FROM demo_strategy_reviews').fetchone()[0]);self.assertEqual(params['batch_size'],3)
 def test_invalid_generated_policy_or_code_is_rejected(self):
  observation=m.DEMO.market_context('Codex');base={'regime':'neutral','summary':'A bounded review','actions':[]}
  for policy in [{'exploration_rate':1},{'batch_size':1000},{'code':'run shell'},{'hold_seconds':float('nan')}]:
   with self.assertRaises(ValueError):m.DEMO.validate(json.dumps({**base,'policy':policy}),observation)
 def test_one_second_cycle_has_no_external_quote_calls(self):
  self.seed_policy_market()
  with patch.object(m.DEMO,'book',side_effect=AssertionError('Network must stay out of fast cycle')),patch.object(m.DEMO,'getjson',side_effect=AssertionError('No external HTTP in fast cycle')),patch.object(m.DEMO,'trigger',return_value={'started':False}):m.DEMO.cycle()
  self.assertGreater(m.DEMO.last_check,0);self.assertTrue(m.DEMO.status()['runtime']['worker_healthy'])
 def test_paused_fast_learner_cannot_queue_orders(self):
  self.seed_policy_market();m.DEMO.configure({'policy_enabled':False});self.assertEqual(m.DEMO.fast_policy('Codex'),[])
  m.DEMO.configure({'enabled':False,'policy_enabled':True});self.assertEqual(m.DEMO.fast_policy('Codex'),[])
 def test_restart_does_not_replay_seen_policy_observations(self):
  self.seed_policy_market();first=m.DEMO.fast_policy('Codex');self.assertTrue(first)
  with m.db() as c:
   c.execute("UPDATE demo_orders SET state='cancelled'")
   m.DEMO.init(c)
  m.DEMO.last_policy_quote={};self.assertEqual(m.DEMO.fast_policy('Codex'),[])
 def test_confirmed_negative_points_reduce_next_fast_policy_budget(self):
  self.seed_policy_market(2)
  first=m.DEMO.submit('Codex','QP0/USD','buy','policy','same-context','Isolated policy entry',None,'size-before')
  with m.db() as c:
   learning.learn(c,'Codex',9999,'same-context',-5)
   before=c.execute('SELECT budget FROM demo_orders WHERE id=?',(first,)).fetchone()[0]
  second=m.DEMO.submit('Codex','QP1/USD','buy','policy','same-context','Isolated policy entry',None,'size-after')
  with m.db() as c:after=c.execute('SELECT budget FROM demo_orders WHERE id=?',(second,)).fetchone()[0]
  self.assertEqual(before,750);self.assertEqual(after,600)
 def test_fill_rate_cap_defers_without_consuming_the_next_snapshot(self):
  first=self.order('Codex',key='fill-cap-a');second=self.order('AGY',key='fill-cap-b');self.later(first);self.later(second)
  m.DEMO.configure({'max_orders_per_second':1});book=self.book()
  self.assertIsNotNone(m.DEMO.process_book(first,book,now=self.now))
  self.assertIsNone(m.DEMO.process_book(second,book,now=self.now+.1))
  self.assertIsNotNone(m.DEMO.process_book(second,book,now=self.now+1.1))
 def test_protective_exit_cancels_partial_entry_remainder_without_fabricating_close(self):
  entry=self.order();self.later(entry);m.DEMO.process_book(entry,self.book(visible=1),now=self.now)
  with m.db() as c:c.execute('UPDATE demo_positions SET opened=?',(self.now-2000,))
  with patch.object(m.DEMO,'book',return_value=self.book(visible=1)):m.DEMO.refresh_marks_and_risk()
  with m.db() as c:
   self.assertEqual(c.execute('SELECT state FROM demo_orders WHERE id=?',(entry,)).fetchone()[0],'cancelled')
   self.assertEqual(c.execute("SELECT COUNT(*) FROM demo_orders WHERE side='sell' AND state='queued'").fetchone()[0],1)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_rewards').fetchone()[0],0)
 def test_loss_streak_stops_new_entries_even_if_exploration_is_requested(self):
  self.admission_patch.stop()
  with m.db() as c:
   for episode in range(3):c.execute('INSERT INTO demo_rewards VALUES(?,?,?,?,?,?,?)',(100+episode,'Codex','BTC/USD',self.now+episode,-1,-5,200+episode))
  with self.assertRaisesRegex(ValueError,'circuit breaker'):self.order()
  self.assertEqual(m.DEMO.status()['bots'][1]['entry_protection']['consecutive_losses'],3)
 def test_cost_guard_rejects_short_horizon_without_observed_movement(self):
  self.admission_patch.stop()
  with m.db() as c:
   for offset in [1500,1200,900,600,300,0]:c.execute('INSERT OR REPLACE INTO history VALUES(?,?,?)',('BTC/USD',self.now-offset,100))
  with self.assertRaisesRegex(ValueError,'Cost guard'):self.order()
 def test_new_entry_pause_preserves_exit_processing(self):
  entry=self.order();self.later(entry);m.DEMO.process_book(entry,self.book(),now=self.now)
  m.DEMO.configure({'entries_enabled':False})
  with self.assertRaisesRegex(ValueError,'paused'):self.order(key='new-paused-entry',symbol='QASTOCK')
  exit=self.order(side='sell',key='exit-during-entry-freeze');self.assertIsNotNone(exit)
 def test_one_unresolved_episode_blocks_correlated_context_batch(self):
  self.admission_patch.stop();m.DEMO.configure({'cost_guard':False});self.seed_policy_market(2)
  m.DEMO.submit('Codex','QP0/USD','buy','policy','shared-context','First unresolved trial',None,'correlated-a')
  with self.assertRaisesRegex(ValueError,'One unresolved'):m.DEMO.submit('Codex','QP1/USD','buy','policy','shared-context','Second trial',None,'correlated-b')
 def test_cost_guard_can_admit_sufficient_observed_range_but_does_not_claim_profit(self):
  self.admission_patch.stop()
  with m.db() as c:
   for offset,price in [(1500,98),(1200,99),(900,100),(600,101),(300,102),(0,100)]:c.execute('INSERT OR REPLACE INTO history VALUES(?,?,?)',('BTC/USD',self.now-offset,price))
  self.assertIsNotNone(self.order())
 def test_context_with_last_closed_loss_cannot_repeat_after_a_review(self):
  first=self.order();self.later(first);m.DEMO.process_book(first,self.book(),now=self.now)
  exit=self.order(side='sell',key='context-loss-exit');self.later(exit);m.DEMO.process_book(exit,self.book(stamp=self.now+2),now=self.now+2)
  self.admission_patch.stop();m.DEMO.configure({'cost_guard':False})
  with self.assertRaisesRegex(ValueError,'context lost'):self.order(key='repeat-losing-context')
if __name__=='__main__':unittest.main(verbosity=2)
