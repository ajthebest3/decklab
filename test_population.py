"""Isolated population funding, lifecycle, model boundary and execution checks."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from population_engine import PopulationEngine, Connection, STRATEGY_DEFAULT, strategy


def rows(c,sql,args=()):return [dict(r) for r in c.execute(sql,args)]

class PopulationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='decklab-population-test-');self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.now=time.time();self.stop=threading.Event()
  def source():
   c=Connection(self.root/'source.db');c.row_factory=__import__('sqlite3').Row;return c
  self.source=source
  with source() as c:
   c.executescript('''CREATE TABLE assets(symbol TEXT PRIMARY KEY,name TEXT,kind TEXT,region TEXT,currency TEXT,provider TEXT,pair TEXT,tracked INTEGER);
   CREATE TABLE quotes(symbol TEXT PRIMARY KEY,price REAL,change REAL,volume REAL,asof REAL,fetched REAL,source TEXT,status TEXT);
   CREATE TABLE history(symbol TEXT,ts REAL,price REAL,PRIMARY KEY(symbol,ts));
   CREATE TABLE news(id TEXT PRIMARY KEY,title TEXT,url TEXT,source TEXT,published_ts REAL);
   CREATE TABLE demo_rules(symbol TEXT PRIMARY KEY,decimals INTEGER,min_qty REAL,min_cost REAL,checked REAL);
   CREATE TABLE demo_fx(currency TEXT PRIMARY KEY,units_per_usd REAL,asof REAL,fetched REAL,source TEXT);
   CREATE TABLE private_wallet(cash REAL,secret TEXT);INSERT INTO private_wallet VALUES(100000,'DO_NOT_COPY_ACCOUNT');''')
   for i in range(4):
    symbol=f'QA{i}/USD'
    c.execute('INSERT INTO assets VALUES(?,?,\'crypto\',\'Global\',\'USD\',\'Kraken\',?,1)',(symbol,symbol,symbol))
    c.execute('INSERT INTO quotes VALUES(?,100,2,100000,?,?,\'fixture\',\'current\')',(symbol,self.now,self.now))
    c.execute('INSERT INTO demo_rules VALUES(?,6,.001,1,?)',(symbol,self.now))
    for offset in (600,300,0):c.execute('INSERT INTO history VALUES(?,?,?)',(symbol,self.now-offset,100-offset*.001))
   c.execute("INSERT INTO demo_fx VALUES('INR',94,?,?,'fixture')",(self.now,self.now))
  self.cli_calls=[]
  def cli(provider,prompt,**kwargs):
   self.cli_calls.append((provider,prompt,kwargs))
   return json.dumps(dict(regime='neutral',summary='Isolated bounded model fixture',strategy=STRATEGY_DEFAULT))
  self.engine=PopulationEngine(self.root,source,rows,lambda _: {},lambda _: {},cli,self.stop)
  self.engine.initialize();self.engine.start_population();self.engine.sync_market()
  self.bot=self.engine.bot_names()[0]
 def decision(self,bot=None,source='point_policy',state='completed',policy=None):
  bot=bot or self.bot
  selected={**STRATEGY_DEFAULT,**(policy or {})}
  result=dict(regime='neutral',summary='Isolated strategy fixture',strategy=selected,policy=dict(exploration_rate=selected['exploration_rate'],min_change=0,batch_size=selected['batch_size'],hold_seconds=selected['hold_seconds']))
  with self.engine.db() as c:
   if source=='advisor' and state=='completed':c.execute('UPDATE population_bots SET strategy=? WHERE bot=?',(json.dumps(selected),bot))
   return c.execute('INSERT INTO demo_decisions(bot,created,finished,state,result,source) VALUES(?,?,?,?,?,?)',(bot,time.time(),time.time(),state,json.dumps(result),source)).lastrowid
 def seed_model(self,bot=None,policy=None):return self.decision(bot,'advisor',policy=policy)
 def buy(self,bot=None,symbol='QA0/USD',key='isolated-buy',policy=None):
  bot=bot or self.bot;self.seed_model(bot,policy);did=self.decision(bot,policy=policy)
  return self.engine.submit(bot,symbol,'buy','policy','fixture|'+symbol,'Isolated signal',did,key)
 def later(self,oid):
  with self.engine.db() as c:c.execute('UPDATE demo_orders SET created=?,earliest=? WHERE id=?',(self.now-5,self.now-2,oid))
 def book(self,bid=99.9,ask=100.1,visible=10000,offset=0):
  return dict(available=True,source='isolated observed depth',fetched=self.now+offset,bids=[[bid,visible]],asks=[[ask,visible]])
 def set_cash(self,bot,cash):
  with self.engine.db() as c:
   old=c.execute('SELECT cash FROM demo_wallets WHERE bot=?',(bot,)).fetchone()[0]
   c.execute('UPDATE demo_wallets SET cash=? WHERE bot=?',(cash,bot))
   c.execute('INSERT INTO demo_cash_ledger(bot,ts,kind,amount,ref) VALUES(?,?,\'isolated outcome fixture\',?,?)',(bot,time.time(),cash-old,'fixture-'+bot+'-'+str(time.time_ns())))
 def review(self,target=None,action='keep',parent=None):
  with self.engine.db() as c:
   observation=self.engine.review_observation(c)
   rid=c.execute("INSERT INTO population_reviews(created,state,input_json) VALUES(?,'running',?)",(time.time(),json.dumps(observation))).lastrowid
  result=dict(summary='Isolated reviewer fixture',ratings=[dict(bot=b['bot'],score=25,action=action if b['bot']==target else 'keep',parent=parent if b['bot']==target else None,reason='Recorded fixture evidence') for b in observation['bots']])
  return rid,result
 def wait_job(self,did):
  for _ in range(100):
   with self.engine.db() as c:r=c.execute('SELECT * FROM demo_decisions WHERE id=?',(did,)).fetchone()
   if r['state']!='running':return dict(r)
   time.sleep(.01)
  self.fail('Fixture strategy worker did not finish')
 def test_initial_funding_and_restart_are_idempotent(self):
  self.engine.start_population();self.engine.initialize()
  with self.engine.db() as c:
   self.assertEqual(c.execute('SELECT SUM(cash) FROM demo_wallets').fetchone()[0],40000)
   self.assertEqual(c.execute('SELECT SUM(amount) FROM demo_cash_ledger').fetchone()[0],40000)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM population_bots').fetchone()[0],8)
  with self.source() as c:self.assertEqual(c.execute('SELECT cash FROM private_wallet').fetchone()[0],100000)
 def test_provider_split_and_exact_model_settings(self):
  with self.engine.db() as c:
   agents=rows(c,'SELECT * FROM population_bots')
  self.assertEqual(sum(a['provider']=='Codex' for a in agents),4)
  for a in agents:
   self.assertEqual(a['model'],'gpt-6.1-sol' if a['provider']=='Codex' else 'gemini-3.8-flash-high')
   self.assertEqual(a['effort'],'low' if a['provider']=='Codex' else None)
 def test_source_mirror_excludes_private_account(self):
  with self.engine.db() as c:
   self.assertFalse(c.execute("SELECT 1 FROM sqlite_master WHERE name='private_wallet'").fetchone())
   self.assertEqual(c.execute('SELECT COUNT(*) FROM assets').fetchone()[0],4)
 def test_strategy_worker_uses_exact_model_and_private_sandbox(self):
  started=self.engine.trigger(self.bot);r=self.wait_job(started['decision_id'])
  self.assertEqual(r['state'],'completed',r['error'])
  self.assertEqual({k:v for k,v in self.cli_calls[0][2].items() if k!='cancel'},dict(private=True,model='gpt-6.1-sol',effort='low'))
 def test_observation_has_no_wallet_or_execution_history(self):
  oid=self.buy();self.later(oid);self.engine.process_book(oid,self.book(),now=self.now)
  obs=self.engine.market_context(self.bot)
  forbidden={'cash','equity_usd','net_usd','pnl_usd','cost','usd_total','native_price','fee','initial','fills','orders','wallet'}
  def keys(x):
   if isinstance(x,dict):return set(x)|set().union(*(keys(v) for v in x.values()))
   if isinstance(x,list):return set().union(*(keys(v) for v in x)) if x else set()
   return set()
  self.assertFalse(forbidden&keys(obs),forbidden&keys(obs));self.assertIn('features',obs['markets'][0])
 def test_no_buy_before_actual_model_strategy(self):
  did=self.decision()
  with self.assertRaisesRegex(ValueError,'actual model'):
   self.engine.submit(self.bot,'QA0/USD','buy','policy','c','fixture',did,'no-model')
 def test_review_only_model_cannot_submit_buy(self):
  self.seed_model();did=self.decision(source='reviewer')
  with self.assertRaises(ValueError):self.engine.submit(self.bot,'QA0/USD','buy','policy','c','fixture',did,'reviewer-buy')
 def test_queue_delay_and_replay_evidence(self):
  oid=self.buy();self.assertIsNone(self.engine.process_book(oid,self.book(),now=self.now));self.later(oid)
  result=self.engine.process_book(oid,self.book(),now=self.now);self.assertTrue(result)
  self.assertIsNone(self.engine.process_book(oid,self.book(),now=self.now+1))
 def test_shared_capacity_across_population_bots(self):
  a=self.buy(key='shared-a');b=self.buy(self.engine.bot_names()[1],key='shared-b');self.later(a);self.later(b)
  self.engine.process_book(a,self.book(visible=1),now=self.now);self.engine.process_book(b,self.book(visible=1),now=self.now)
  with self.engine.db() as c:self.assertLessEqual(c.execute('SELECT SUM(qty) FROM demo_fills').fetchone()[0],.05+1e-10)
 def test_remaining_cash_can_fund_smaller_entry(self):
  self.set_cash(self.bot,1.5);oid=self.buy(policy={'allocation_pct':100})
  with self.engine.db() as c:self.assertAlmostEqual(c.execute('SELECT budget FROM demo_orders WHERE id=?',(oid,)).fetchone()[0],1.5)
 def test_model_strategy_exploration_queues_multiple_but_no_quote_replay(self):
  self.seed_model()
  with patch('population_engine.random.random',return_value=0):
   first=self.engine.fast_policy(self.bot);second=self.engine.fast_policy(self.bot)
  self.assertEqual(len(first),2);self.assertEqual(second,[])
 def test_stale_model_does_not_start_new_buys(self):
  did=self.seed_model()
  with self.engine.db() as c:c.execute('UPDATE demo_decisions SET created=? WHERE id=?',(self.now-1900,did))
  with patch('population_engine.random.random',return_value=0):self.assertEqual(self.engine.fast_policy(self.bot),[])
 def test_strategy_schema_rejects_generated_code_and_nan(self):
  with self.assertRaises(ValueError):strategy(dict(STRATEGY_DEFAULT,code='run()'))
  with self.assertRaises(ValueError):strategy(dict(STRATEGY_DEFAULT,threshold_pct=float('nan')))
 def test_fully_invested_bot_is_not_depleted(self):
  self.set_cash(self.bot,0)
  with self.engine.db() as c:
   c.execute('INSERT INTO demo_positions VALUES(?,?,1,5000,?,1,\'c\',0)',(self.bot,'QA0/USD',self.now))
   self.assertFalse(self.engine._depleted(c,self.bot))
 def test_pending_order_prevents_depletion(self):
  oid=self.buy();self.set_cash(self.bot,0)
  with self.engine.db() as c:self.assertFalse(self.engine._depleted(c,self.bot))
 def test_reviewer_replaces_depleted_bot_preserving_lifetime_loss(self):
  self.set_cash(self.bot,0);rid,result=self.review(self.bot,'replace');self.engine.apply_review(rid,result)
  with self.engine.db() as c:
   self.assertEqual(c.execute('SELECT state FROM population_bots WHERE bot=?',(self.bot,)).fetchone()[0],'retired')
   self.assertEqual(c.execute('SELECT COUNT(*) FROM population_bots').fetchone()[0],9)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM population_bots WHERE state=\'active\'').fetchone()[0],8)
   value=self.engine.valuation(c);self.assertEqual(value['total']['initial_usd'],1000000);self.assertEqual(value['total']['equity_usd'],995000);self.assertEqual(value['total']['pnl_usd'],-5000)
   self.assertEqual(c.execute('SELECT SUM(amount) FROM population_funding').fetchone()[0],45000)
  with self.assertRaises(ValueError):self.engine.apply_review(rid,result)
 def test_reviewer_cannot_retire_solvent_bot(self):
  rid,result=self.review(self.bot,'replace')
  with self.assertRaises(ValueError):self.engine.apply_review(rid,result)
  with self.engine.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM population_bots').fetchone()[0],8)
 def test_depleted_bot_cannot_be_kept_forever_by_invalid_review(self):
  self.set_cash(self.bot,0);rid,result=self.review()
  with self.assertRaises(ValueError):self.engine.apply_review(rid,result)
 def test_clone_requires_actual_positive_outcomes(self):
  self.set_cash(self.bot,0);rid,result=self.review(self.bot,'clone',self.engine.bot_names()[1])
  with self.assertRaisesRegex(ValueError,'eligible profitable'):self.engine.apply_review(rid,result)
 def test_eligible_clone_preserves_parent_lineage_and_scores(self):
  parent=self.engine.bot_names()[1];self.set_cash(parent,5300)
  with self.engine.db() as c:
   for i in range(5):c.execute('INSERT INTO demo_rewards VALUES(?,?,?,?,?,?,?)',(100+i,parent,'QA0/USD',self.now+i,60,1,100+i))
  self.set_cash(self.bot,0);rid,result=self.review(self.bot,'clone',parent);self.engine.apply_review(rid,result)
  with self.engine.db() as c:
   child=c.execute('SELECT * FROM population_bots WHERE parent=?',(parent,)).fetchone();donor=c.execute('SELECT * FROM population_bots WHERE bot=?',(parent,)).fetchone()
   self.assertEqual(child['strategy'],donor['strategy']);self.assertEqual(child['generation'],2);self.assertEqual(donor['last_clone'],5)
   self.assertEqual(c.execute('SELECT points FROM demo_rewards WHERE bot=? LIMIT 1',(parent,)).fetchone()[0],1)
 def test_clone_cannot_change_half_provider(self):
  parent=self.engine.bot_names()[4];self.set_cash(parent,5300)
  with self.engine.db() as c:
   for i in range(5):c.execute('INSERT INTO demo_rewards VALUES(?,?,?,?,?,?,?)',(100+i,parent,'QA0/USD',self.now+i,60,1,100+i))
  self.set_cash(self.bot,0);rid,result=self.review(self.bot,'clone',parent)
  with self.assertRaises(ValueError):self.engine.apply_review(rid,result)
 def test_pause_cancels_entries_and_prevents_fills(self):
  oid=self.buy();self.later(oid);self.engine.configure({'enabled':False})
  self.assertIsNone(self.engine.process_book(oid,self.book(),now=self.now))
  with self.engine.db() as c:self.assertEqual(c.execute('SELECT state FROM demo_orders WHERE id=?',(oid,)).fetchone()[0],'cancelled')
 def test_terminal_points_are_real_and_cash_reconciles(self):
  oid=self.buy();self.later(oid);self.engine.process_book(oid,self.book(),now=self.now)
  sell=self.engine.submit(self.bot,'QA0/USD','sell','large','fixture|QA0/USD','isolated exit',None,'terminal-sell');self.later(sell)
  closed=self.engine.process_book(sell,self.book(bid=104,ask=104.1,offset=2),now=self.now+2)
  self.assertEqual(closed['points'],1)
  with self.engine.db() as c:
   wallet=c.execute('SELECT cash FROM demo_wallets WHERE bot=?',(self.bot,)).fetchone()[0];ledger=c.execute('SELECT SUM(amount) FROM demo_cash_ledger WHERE bot=?',(self.bot,)).fetchone()[0]
   self.assertAlmostEqual(wallet,ledger,places=8)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_rewards').fetchone()[0],1)
 def test_ledger_summary_includes_reviewer_and_generations(self):
  status=self.engine.status({'view':['summary']})
  self.assertEqual(status['population']['active'],8);self.assertEqual(status['population']['cumulative_funding_usd'],40000)
  self.assertEqual(status['reviewer']['model'],'gpt-6.1-sol');self.assertEqual(len(status['bots']),8)
 def test_fractional_dust_writeoff_preserves_cost_without_fake_fill(self):
  with self.engine.db() as c:
   c.execute('INSERT INTO demo_positions VALUES(?,?,?,0.000001,?,999,\'dust\',-4)',(self.bot,'QA0/USD',0.00000001,self.now))
   c.execute("INSERT INTO demo_marks VALUES('QA0/USD',100,'USD',1,?,?,'isolated bid')",(self.now,self.now))
   before=c.execute('SELECT cash FROM demo_wallets WHERE bot=?',(self.bot,)).fetchone()[0]
  self.engine.settle_fractional_dust();self.engine.settle_fractional_dust()
  with self.engine.db() as c:
   self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_fills').fetchone()[0],0)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM population_dust').fetchone()[0],1)
   r=c.execute('SELECT * FROM demo_rewards').fetchone();self.assertEqual(r['points'],-5);self.assertAlmostEqual(r['net_usd'],-4.000001)
   self.assertEqual(c.execute('SELECT cash FROM demo_wallets WHERE bot=?',(self.bot,)).fetchone()[0],before)
   self.assertEqual(next(b for b in self.engine.valuation(c)['bots'] if b['bot']==self.bot)['dust_writeoff_usd'],0.000001)
 def test_stale_bid_cannot_write_off_dust_or_trigger_depletion(self):
  self.set_cash(self.bot,0)
  with self.engine.db() as c:
   c.execute('INSERT INTO demo_positions VALUES(?,?,?,0.000001,?,999,\'dust\',-4)',(self.bot,'QA0/USD',0.00000001,self.now))
   c.execute("INSERT INTO demo_marks VALUES('QA0/USD',100,'USD',1,?,?,'isolated stale bid')",(self.now-50,self.now-50))
  self.engine.settle_fractional_dust()
  with self.engine.db() as c:
   self.assertEqual(c.execute('SELECT COUNT(*) FROM population_dust').fetchone()[0],0)
   self.assertFalse(self.engine._depleted(c,self.bot))
 def test_depletion_uses_actual_lot_minimum_and_fresh_quotes(self):
  self.set_cash(self.bot,2)
  with self.engine.db() as c:
   c.execute('UPDATE demo_rules SET min_qty=.1')
   self.assertTrue(self.engine._depleted(c,self.bot))
   c.execute('UPDATE quotes SET asof=?',(self.now-300,))
   self.assertFalse(self.engine._depleted(c,self.bot))
 def test_failed_strategy_job_cannot_enable_entries(self):
  self.engine.cli=lambda *args,**kwargs:'{"code":"run()"}'
  did=self.engine.trigger(self.bot)['decision_id'];r=self.wait_job(did)
  self.assertEqual(r['state'],'failed');self.assertEqual(self.engine.fast_policy(self.bot),[])
 def test_invalid_review_rolls_back_all_ratings_and_funding(self):
  rid,result=self.review();result['ratings'][-1]['score']=999
  with self.assertRaises(ValueError):self.engine.apply_review(rid,result)
  with self.engine.db() as c:
   self.assertEqual(c.execute('SELECT COUNT(*) FROM population_bots WHERE score IS NOT NULL').fetchone()[0],0)
   self.assertEqual(c.execute('SELECT SUM(amount) FROM population_funding').fetchone()[0],40000)
 def test_population_backup_is_durable_and_kept_separate(self):
  self.engine.daily_backup();self.engine.daily_backup()
  backups=list(self.root.glob('population-backup-*.sqlite'));self.assertEqual(len(backups),1)
  with Connection(backups[0]) as c:self.assertEqual(c.execute('SELECT SUM(amount) FROM population_funding').fetchone()[0],40000)
  self.assertEqual(backups[0].stat().st_mode & 0o777,0o600)
 def test_replacement_inherits_point_evidence_without_dollar_history(self):
  with self.engine.db() as c:
   import demo_learning
   demo_learning.learn(c,self.bot,999,'failed|momentum',-5)
  self.set_cash(self.bot,0);rid,result=self.review(self.bot,'replace');self.engine.apply_review(rid,result)
  with self.engine.db() as c:child=c.execute('SELECT bot FROM population_bots WHERE slot=1 AND state=\'active\'').fetchone()[0]
  obs=self.engine.market_context(child)
  self.assertEqual(obs['lineage_point_feedback'][0]['feedback']['points'],-5)
  self.assertEqual(obs['provider_point_feedback'][0]['points'],-5)
  text=json.dumps(obs);self.assertNotIn('"net_usd":',text);self.assertNotIn('"cash":',text);self.assertNotIn('"equity_usd":',text)
 def test_model_can_allocate_all_free_funds_above_old_fixed_cap(self):
  oid=self.buy(policy={'allocation_pct':100})
  with self.engine.db() as c:self.assertEqual(c.execute('SELECT budget FROM demo_orders WHERE id=?',(oid,)).fetchone()[0],5000)
 def test_model_percentage_applies_to_unreserved_cash(self):
  first=self.buy(symbol='QA0/USD',key='fraction-a',policy={'allocation_pct':50})
  second=self.buy(symbol='QA1/USD',key='fraction-b',policy={'allocation_pct':50})
  with self.engine.db() as c:
   self.assertEqual(c.execute('SELECT budget FROM demo_orders WHERE id=?',(first,)).fetchone()[0],2500)
   self.assertEqual(c.execute('SELECT budget FROM demo_orders WHERE id=?',(second,)).fetchone()[0],1250)
 def test_more_than_three_open_positions_is_allowed(self):
  for i in range(4):
   oid=self.buy(symbol=f'QA{i}/USD',key=f'no-slot-quota-{i}',policy={'allocation_pct':10});self.later(oid);self.engine.process_book(oid,self.book(),now=self.now)
  with self.engine.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_positions WHERE bot=?',(self.bot,)).fetchone()[0],4)
 def test_model_can_select_batch_above_three_and_no_daily_quota(self):
  self.seed_model(policy={'batch_size':1000,'allocation_pct':10})
  with patch('population_engine.random.random',return_value=0):orders=self.engine.fast_policy(self.bot)
  self.assertEqual(len(orders),4)
  status=self.engine.status({'view':['summary']});self.assertIsNone(status['population']['daily_trade_limit']);self.assertIsNone(status['population']['position_limit'])
 def test_zero_model_allocation_holds_cash(self):
  self.seed_model(policy={'allocation_pct':0})
  with patch('population_engine.random.random',return_value=0):self.assertEqual(self.engine.fast_policy(self.bot),[])
 def test_invalid_model_allocation_cannot_overdraw_or_inject_values(self):
  for value in [-1,101,True,float('nan')]:
   with self.assertRaises(ValueError):strategy(dict(STRATEGY_DEFAULT,allocation_pct=value))
 def test_atomic_allocation_prevents_two_orders_spending_same_funds(self):
  self.seed_model(policy={'allocation_pct':100});did=self.decision(policy={'allocation_pct':100});accepted=[];rejected=[]
  def submit(symbol):
   try:accepted.append(self.engine.submit(self.bot,symbol,'buy','policy','ctx|'+symbol,'fixture',did,'concurrent-'+symbol))
   except ValueError as e:rejected.append(str(e))
  threads=[threading.Thread(target=submit,args=(f'QA{i}/USD',)) for i in range(2)]
  for t in threads:t.start()
  for t in threads:t.join()
  self.assertEqual(len(accepted),1);self.assertEqual(len(rejected),1)
  with self.engine.db() as c:self.assertEqual(c.execute('SELECT SUM(remaining) FROM demo_orders').fetchone()[0],5000)
 def test_old_strategy_without_allocation_waits_for_actual_new_choice(self):
  self.seed_model()
  with self.engine.db() as c:
   r=json.loads(c.execute("SELECT result FROM demo_decisions WHERE bot=?",(self.bot,)).fetchone()[0]);r['strategy'].pop('allocation_pct');c.execute('UPDATE demo_decisions SET result=? WHERE bot=?',(json.dumps(r),self.bot))
  with patch('population_engine.random.random',return_value=0):self.assertEqual(self.engine.fast_policy(self.bot),[])
 def test_model_may_add_to_existing_position_without_new_reward(self):
  first=self.buy(policy={'allocation_pct':10,'add_to_positions':True});self.later(first);self.engine.process_book(first,self.book(),now=self.now)
  with self.engine.db() as c:before=c.execute('SELECT qty FROM demo_positions WHERE bot=?',(self.bot,)).fetchone()[0]
  added=self.buy(key='position-add',policy={'allocation_pct':10,'add_to_positions':True});self.later(added);self.engine.process_book(added,self.book(ask=100.2,offset=2),now=self.now+2)
  with self.engine.db() as c:
   self.assertGreater(c.execute('SELECT qty FROM demo_positions WHERE bot=?',(self.bot,)).fetchone()[0],before)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_positions').fetchone()[0],1)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_rewards').fetchone()[0],0)
 def test_model_can_disable_adding_to_positions(self):
  first=self.buy(policy={'allocation_pct':10,'add_to_positions':False});self.later(first);self.engine.process_book(first,self.book(),now=self.now)
  with self.assertRaisesRegex(ValueError,'pyramiding'):
   self.buy(key='disallowed-add',policy={'allocation_pct':10,'add_to_positions':False})
 def test_addition_and_full_exit_conserve_cash_and_award_one_episode(self):
  first=self.buy(policy={'allocation_pct':10});self.later(first);self.engine.process_book(first,self.book(),now=self.now)
  added=self.buy(key='add-before-exit',policy={'allocation_pct':10});self.later(added);self.engine.process_book(added,self.book(ask=100.2,offset=2),now=self.now+2)
  sell=self.engine.submit(self.bot,'QA0/USD','sell','large','fixture','fixture close',None,'close-added-position');self.later(sell)
  closed=self.engine.process_book(sell,self.book(bid=104,ask=104.1,offset=4),now=self.now+4)
  self.assertEqual(closed['points'],1)
  with self.engine.db() as c:
   self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_rewards').fetchone()[0],1)
   cash=c.execute('SELECT cash FROM demo_wallets WHERE bot=?',(self.bot,)).fetchone()[0];net=c.execute('SELECT net_usd FROM demo_rewards').fetchone()[0]
   self.assertAlmostEqual(cash-5000,net,places=7)
 def test_existing_population_migrates_without_refunding_or_inventing_allocation(self):
  self.seed_model()
  with self.engine.db() as c:
   legacy=dict(STRATEGY_DEFAULT);legacy.pop('allocation_pct');legacy.pop('add_to_positions')
   c.execute('UPDATE population_bots SET strategy=?',(json.dumps(legacy),))
   c.execute("DELETE FROM population_config WHERE key='allocation_policy_since'")
   c.execute("UPDATE demo_settings SET value='3' WHERE key='max_positions'")
  self.engine.initialize()
  with self.engine.db() as c:
   self.assertIsNone(self.engine.settings(c)['max_positions'])
   self.assertEqual(c.execute('SELECT SUM(amount) FROM population_funding').fetchone()[0],40000)
   self.assertNotIn('allocation_pct',json.loads(c.execute('SELECT strategy FROM population_bots WHERE bot=?',(self.bot,)).fetchone()[0]))
  did=self.engine.trigger(self.bot)['decision_id'];record=self.wait_job(did)
  self.assertEqual(record['state'],'completed',record['error']);self.assertIn('allocation_pct',json.loads(record['result'])['strategy'])

if __name__=='__main__':unittest.main()
