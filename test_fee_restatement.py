"""Fee restatement accounting checks against isolated observed-fill fixtures."""
import json,sqlite3,time,unittest
from test_population import PopulationTests as Fixtures
from fee_restatement import apply,replay,validate_replay,annotate

class FeeTests(Fixtures):
 def setUp(self):
  super().setUp()
  with self.engine.db() as c:c.execute("UPDATE demo_settings SET value='0.008' WHERE key='fee_rate'")
 def enter(self,partial=False):
  oid=self.buy();self.later(oid)
  self.engine.process_book(oid,self.book(visible=1 if partial else 10000),now=self.now)
  return oid
 def exit(self,bid=100.6,partial=False):
  oid=self.engine.submit(self.bot,'QA0/USD','sell','large','fixture|QA0/USD','Isolated fee fixture exit',None,'fixture-exit-'+str(time.time_ns()));self.later(oid)
  self.engine.process_book(oid,self.book(bid=bid,ask=bid+.1,visible=1 if partial else 10000,offset=.01),now=self.now+.01)
  return oid
 def pause(self):self.engine.configure({'enabled':False})
 def restate(self,rid='fixture-fee-change',rate=.001):
  with self.engine.db() as c:return apply(c,rid,rate)
 def test_closed_loss_can_become_scenario_win_with_original_reward_audited(self):
  self.enter();self.exit();self.pause()
  with self.engine.db() as c:old=dict(c.execute('SELECT * FROM demo_rewards').fetchone());self.assertEqual(old['points'],-5)
  summary=self.restate()
  with self.engine.db() as c:
   result=annotate(c,'outcomes',dict(c.execute('SELECT * FROM demo_rewards').fetchone()))
   self.assertEqual(result['points'],1);self.assertEqual(result['as_executed']['points'],-5)
   self.assertEqual(c.execute('SELECT points FROM demo_learning').fetchone()[0],1)
   self.assertAlmostEqual(c.execute('SELECT q FROM demo_policy').fetchone()[0],.2)
   self.assertEqual(summary['changed_outcomes'],1)
 def test_fee_refund_and_cash_ledger_conserve_value(self):
  self.enter();self.exit();self.pause()
  with self.engine.db() as c:old_cash=c.execute('SELECT cash FROM demo_wallets WHERE bot=?',(self.bot,)).fetchone()[0];old_fees=c.execute('SELECT SUM(fee) FROM demo_fills').fetchone()[0]
  result=self.restate()
  with self.engine.db() as c:
   cash=c.execute('SELECT cash FROM demo_wallets WHERE bot=?',(self.bot,)).fetchone()[0]
   self.assertAlmostEqual(cash-old_cash,old_fees*7/8)
   self.assertAlmostEqual(cash,c.execute('SELECT SUM(amount) FROM demo_cash_ledger WHERE bot=?',(self.bot,)).fetchone()[0])
   self.assertAlmostEqual(result['fees_after'],old_fees/8)
 def test_prices_quantities_evidence_times_and_original_cash_entries_unchanged(self):
  self.enter();self.exit();self.pause()
  with self.engine.db() as c:
   fields='id,order_id,bot,symbol,side,ts,qty,native_price,currency,fx_usd,fx_asof,usd_total,book_ts,book_hash,evidence'
   before=[tuple(r) for r in c.execute('SELECT '+fields+' FROM demo_fills ORDER BY id')];ledger=[tuple(r) for r in c.execute('SELECT * FROM demo_cash_ledger ORDER BY id')]
  self.restate()
  with self.engine.db() as c:
   self.assertEqual(before,[tuple(r) for r in c.execute('SELECT '+fields+' FROM demo_fills ORDER BY id')]);self.assertEqual(ledger,[tuple(r) for r in c.execute('SELECT * FROM demo_cash_ledger ORDER BY id LIMIT ?',(len(ledger),))])
 def test_open_and_partially_realized_position_costs_are_recomputed(self):
  self.enter();self.exit(partial=True);self.pause()
  with self.engine.db() as c:old=dict(c.execute('SELECT * FROM demo_positions').fetchone())
  self.restate()
  with self.engine.db() as c:
   new=dict(c.execute('SELECT * FROM demo_positions').fetchone());self.assertEqual(new['qty'],old['qty']);self.assertLess(new['cost'],old['cost']);self.assertGreater(new['realized_parts'],old['realized_parts']);self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_rewards').fetchone()[0],0)
 def test_repeated_same_request_never_refunds_twice(self):
  self.enter();self.exit();self.pause();self.restate()
  with self.engine.db() as c:before=c.execute('SELECT SUM(cash) FROM demo_wallets').fetchone()[0];count=c.execute('SELECT COUNT(*) FROM demo_cash_ledger').fetchone()[0]
  self.assertTrue(self.restate()['reused'])
  with self.engine.db() as c:self.assertEqual(c.execute('SELECT SUM(cash) FROM demo_wallets').fetchone()[0],before);self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_cash_ledger').fetchone()[0],count)
 def test_different_rate_restatement_conserves_audit_and_ledger(self):
  self.enter();self.exit();self.pause();self.restate();self.restate('second-fixture-fee-change',.002)
  with self.engine.db() as c:
   self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_fee_restatements').fetchone()[0],2);validate_replay(c,replay(c))
   self.assertEqual(annotate(c,'fills',dict(c.execute('SELECT * FROM demo_fills LIMIT 1').fetchone()))['as_executed']['fee'],c.execute("SELECT json_extract(before_json,'$.fee') FROM demo_fee_audit WHERE batch=1 AND table_name='demo_fills' ORDER BY row_key LIMIT 1").fetchone()[0])
 def test_stopped_and_no_pending_orders_required(self):
  self.enter()
  with self.assertRaisesRegex(ValueError,'Stop'):self.restate()
  self.pause()
  with self.engine.db() as c:c.execute("UPDATE demo_orders SET state='queued' WHERE id=1")
  with self.assertRaisesRegex(ValueError,'Cancel pending'):self.restate()
 def test_invalid_source_accounting_rolls_back_every_change(self):
  self.enter();self.exit();self.pause()
  with self.engine.db() as c:c.execute('UPDATE demo_fills SET realized=999 WHERE side=\'sell\'');before=[tuple(r) for r in c.execute('SELECT * FROM demo_wallets')]
  with self.assertRaises(ValueError):self.restate()
  with self.engine.db() as c:self.assertEqual(before,[tuple(r) for r in c.execute('SELECT * FROM demo_wallets')]);self.assertEqual(json.loads(c.execute("SELECT value FROM demo_settings WHERE key='fee_rate'").fetchone()[0]),.008)
 def test_history_is_preserved_and_new_chart_uses_current_basis(self):
  self.enter();self.exit();self.pause()
  with self.engine.db() as c:c.execute('INSERT INTO demo_equity VALUES(?,?,?,NULL)',(int(time.time())-120,999000,None))
  result=self.restate()
  with self.engine.db() as c:self.assertEqual(c.execute('SELECT usd FROM demo_equity WHERE ts<?',(result['chart_from'],)).fetchone()[0],999000)
  state=self.engine.status();self.assertTrue(all(r['ts']>=result['chart_from'] for r in state['history']));self.assertIsNotNone(state['fee_basis']['restatement'])
 def test_original_funding_and_treasury_never_change(self):
  self.enter();self.exit();self.pause()
  with self.engine.db() as c:before=([tuple(r) for r in c.execute('SELECT * FROM population_funding')],[tuple(r) for r in c.execute('SELECT * FROM population_treasury')])
  self.restate()
  with self.engine.db() as c:self.assertEqual(before,([tuple(r) for r in c.execute('SELECT * FROM population_funding')],[tuple(r) for r in c.execute('SELECT * FROM population_treasury')]))
 def test_fee_change_requires_fresh_strategy_and_reviewer_results(self):
  self.enter();self.exit();self.pause();self.restate()
  with self.engine.db() as c:
   self.assertIsNone(c.execute('SELECT score FROM population_bots WHERE bot=?',(self.bot,)).fetchone()[0]);self.assertIsNotNone(c.execute('SELECT value FROM population_config WHERE key=?',('ai_since_'+self.bot,)).fetchone())
  self.engine.start_population();self.assertEqual(self.engine.fast_policy(self.bot),[])
 def test_additional_entries_share_one_recomputed_episode(self):
  self.enter();extra=self.buy(key='fixture-addition');self.later(extra)
  self.engine.process_book(extra,self.book(offset=.005),now=self.now+.005)
  self.exit();self.pause();self.restate()
  with self.engine.db() as c:
   self.assertEqual(c.execute("SELECT COUNT(*) FROM demo_fills WHERE side='buy'").fetchone()[0],2)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_rewards').fetchone()[0],1);validate_replay(c,replay(c))
 def test_fractional_dust_writeoff_cost_and_terminal_reward_restate(self):
  with self.engine.db() as c:c.execute("UPDATE quotes SET price=.1008,volume=1000000000 WHERE symbol='QA0/USD'")
  oid=self.buy();self.later(oid)
  self.engine.process_book(oid,self.book(bid=.1007,ask=.1008,visible=1000000000),now=self.now)
  with self.engine.db() as c:c.execute("UPDATE demo_rules SET decimals=3 WHERE symbol='QA0/USD'")
  sell=self.engine.submit(self.bot,'QA0/USD','sell','large','fixture','Isolated precision change',None,'fixture-dust-exit');self.later(sell)
  self.engine.process_book(sell,self.book(bid=.1009,ask=.101,visible=1000000000,offset=.01),now=self.now+.01)
  with self.engine.db() as c:c.execute("INSERT OR REPLACE INTO demo_marks VALUES(?, ?,'USD',1,NULL,?,'Isolated observed book')",('QA0/USD',.1009,self.now))
  self.engine.settle_fractional_dust();self.pause()
  with self.engine.db() as c:old=c.execute('SELECT cost FROM population_dust').fetchone()[0]
  self.restate()
  with self.engine.db() as c:
   self.assertLess(c.execute('SELECT cost FROM population_dust').fetchone()[0],old);self.assertEqual(c.execute('SELECT COUNT(*) FROM demo_rewards').fetchone()[0],1);validate_replay(c,replay(c))
 def test_same_request_cannot_silently_change_its_fee_rate(self):
  self.enter();self.exit();self.pause();self.restate()
  with self.assertRaisesRegex(ValueError,'different fee rate'):self.restate(rate=.002)
 def test_invalid_rate_rejected(self):
  self.pause()
  for rate in (-1,float('nan'),True,.6):
   with self.assertRaises(ValueError):self.restate(rate=rate)

for name in list(vars(Fixtures)):
 if name.startswith('test_') and name not in vars(FeeTests):setattr(FeeTests,name,None)
if __name__=='__main__':
 result=unittest.TextTestRunner().run(unittest.TestLoader().loadTestsFromTestCase(FeeTests));raise SystemExit(0 if result.wasSuccessful() else 1)
