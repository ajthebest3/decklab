"""Control center accounting, stopped worker and AI assignment regression tests."""
import json,time,unittest
from unittest.mock import Mock
from test_population import PopulationTests as Fixtures

class ControlTests(Fixtures):
 # Reuse only the isolated fixture setup/helpers, not inherited test cases.
 def test_reserve_matches_allocation_and_lifetime_equity(self):
  with self.engine.db() as c:v=self.engine.valuation(c)
  self.assertEqual(v['portfolio']['reserve_usd'],960000)
  self.assertEqual(v['total']['initial_usd'],1000000)
  self.assertEqual(v['total']['equity_usd'],1000000)
 def test_stop_cancels_pending_and_stale_jobs_without_reset(self):
  oid=self.buy();before=self.engine.status()['total']['equity_usd']
  with self.engine.db() as c:epoch=self.engine.controls.epoch(c)
  self.engine.configure({'enabled':False})
  with self.engine.db() as c:
   self.assertFalse(self.engine.current_job(c,epoch,self.bot));self.assertEqual(c.execute('SELECT state FROM demo_orders WHERE id=?',(oid,)).fetchone()[0],'cancelled')
  self.assertEqual(self.engine.status()['total']['equity_usd'],before)
 def test_launch_plan_parks_bots_and_restart_does_not_refund(self):
  self.engine.configure({'enabled':False});self.engine.configure({'codex_bots':1,'agy_bots':1})
  self.engine.start_population();self.engine.reload_names()
  s=self.engine.status();self.assertEqual(s['population']['active'],2);self.assertEqual(s['population']['parked'],6)
  self.assertEqual(s['portfolio']['reserve_usd'],960000)
  self.engine.configure({'enabled':False});self.engine.start_population()
  self.assertEqual(self.engine.status()['portfolio']['reserve_usd'],960000)
 def test_new_bot_launch_funding_comes_from_reserve(self):
  self.engine.configure({'enabled':False});self.engine.configure({'codex_bots':5,'agy_bots':4,'bot_allocation_usd':10000})
  self.engine.start_population();s=self.engine.status()
  self.assertEqual(s['population']['active'],9);self.assertEqual(s['portfolio']['reserve_usd'],950000);self.assertEqual(s['total']['equity_usd'],1000000)
 def test_capital_transfers_preserve_prior_pnl(self):
  self.set_cash(self.bot,4900);self.engine.configure({'enabled':False})
  before=self.engine.status()['total']['pnl_usd'];self.engine.configure({'bot_allocations':{self.bot:7000}})
  s=self.engine.status();self.assertEqual(s['total']['pnl_usd'],before);self.assertEqual(s['portfolio']['reserve_usd'],958000)
 def test_overdraw_and_insufficient_launch_roll_back(self):
  self.engine.configure({'enabled':False})
  s=self.engine.status()
  with self.assertRaises(ValueError):self.engine.configure({'bot_allocations':{self.bot:100000000}})
  self.assertEqual(self.engine.status()['portfolio'],s['portfolio'])
  self.engine.configure({'codex_bots':200,'agy_bots':0,'bot_allocation_usd':1000000})
  with self.assertRaises(ValueError):self.engine.start_population()
  self.assertFalse(self.engine.status()['settings']['enabled'])
 def test_stopped_worker_does_not_trade_or_call_advisors(self):
  self.engine.configure({'enabled':False});self.engine.cli=Mock(side_effect=AssertionError('No advisor while stopped'))
  with self.engine.db() as c:n=c.execute('SELECT COUNT(*) FROM demo_orders').fetchone()[0]
  self.engine.cycle()
  with self.engine.db() as c:self.assertEqual(n,c.execute('SELECT COUNT(*) FROM demo_orders').fetchone()[0])
  self.engine.cli.assert_not_called()
 def test_ai_assignments_preserve_capital_and_require_stop(self):
  self.engine.mirai=Mock();route=dict(provider='Mirai',model='model-one',effort=None)
  with self.assertRaisesRegex(ValueError,'Stop bots'):self.engine.configure_ai({'assignments':{self.bot:route}})
  self.engine.configure({'enabled':False});before=self.engine.status()['portfolio']
  self.engine.configure_ai({'assignments':{self.bot:route,'reviewer':route}})
  self.assertEqual(self.engine.ai_assignments()['assignments'][self.bot],route)
  self.assertEqual(self.engine.status()['reviewer']['model'],'model-one');self.assertEqual(self.engine.status()['portfolio'],before)
 def test_changed_model_waits_for_fresh_actual_strategy(self):
  self.seed_model();self.engine.configure({'enabled':False});self.engine.mirai=Mock()
  self.engine.configure_ai({'assignments':{self.bot:dict(provider='Mirai',model='model-one',effort=None)}})
  self.engine.start_population();self.assertEqual(self.engine.fast_policy(self.bot),[])
 def test_future_bots_inherit_configured_model(self):
  self.engine.configure({'enabled':False});self.engine.mirai=Mock()
  route=dict(provider='Mirai',model='model-one',effort=None)
  self.engine.configure_ai({'assignments':{'default_Codex':route}})
  self.engine.configure({'codex_bots':5});self.engine.start_population()
  with self.engine.db() as c:self.assertEqual(c.execute("SELECT model FROM population_bots WHERE provider='Codex' ORDER BY slot DESC LIMIT 1").fetchone()[0],'model-one')

 def roster(self,counts=None):
  self.engine.configure({'enabled':False});self.engine.mirai=Mock()
  self.engine.mirai.models.return_value={'models':[{'id':'model-one','chat_supported':True},{'id':'model-two','chat_supported':True}], 'error':''}
  return self.engine.model_roster.configure({'models':[{'model':m,'count':n,'effort':None} for m,n in (counts or {'model-one':2,'model-two':3}).items()]})
 def test_roster_funds_from_reserve_parks_old_bots_and_preserves_history(self):
  self.roster();self.engine.start_population();s=self.engine.status()
  self.assertEqual(s['population']['active'],5);self.assertEqual(s['population']['parked'],8)
  self.assertEqual(s['portfolio']['reserve_usd'],935000);self.assertEqual(s['total']['equity_usd'],1000000)
  self.assertEqual(s['population']['slots'],5)
 def test_roster_restart_no_duplicate_funding(self):
  self.roster();self.engine.start_population();before=self.engine.status()['portfolio']
  self.engine.configure({'enabled':False});self.engine.start_population()
  self.assertEqual(self.engine.status()['portfolio'],before)
 def test_roster_overdraw_is_atomic(self):
  self.roster({'model-one':200});before=self.engine.status()['portfolio']
  with self.assertRaises(ValueError):self.engine.start_population()
  self.assertEqual(self.engine.status()['portfolio'],before)
 def test_roster_unknown_models_negative_counts_and_running_changes_blocked(self):
  self.roster()
  for model,count in [('unknown',1),('model-one',-1),('model-one',201)]:
   with self.assertRaises(ValueError):self.engine.model_roster.configure({'models':[dict(model=model,count=count,effort=None)]})
  self.engine.start_population()
  with self.assertRaisesRegex(ValueError,'Stop bots'):self.engine.model_roster.configure({'models':[dict(model='model-one',count=1,effort=None)]})
 def test_replacement_keeps_predecessor_model_route(self):
  self.roster({'model-two':1});self.engine.start_population()
  with self.engine.db() as c:
   agent=dict(c.execute("SELECT * FROM population_bots WHERE provider='Mirai'").fetchone())
   c.execute("UPDATE population_bots SET state='retired' WHERE bot=?",(agent['bot'],))
   successor=self.engine._spawn(c,agent['slot'],'Mirai')
   self.assertEqual(self.engine.ai_route(c,successor,'Mirai')['model'],'model-two')
 def seed_share_evidence(self):
  self.set_cash(self.bot,5300);self.seed_model()
  with self.engine.db() as c:model=c.execute('SELECT model FROM population_bots WHERE bot=?',(self.bot,)).fetchone()[0]
  for i in range(5):
   episode=1000+i;did=self.decision(self.bot)
   result=dict(strategy=__import__('population_engine').STRATEGY_DEFAULT,model=model)
   with self.engine.db() as c:
    c.execute('UPDATE demo_decisions SET result=? WHERE id=?',(json.dumps(result),did))
    c.execute("INSERT INTO demo_orders(id,bot,symbol,side,created,state,decision_id) VALUES(?,?,?,'buy',?,'filled',?)",(episode,self.bot,'QA0/USD',time.time(),did))
    c.execute('INSERT INTO demo_rewards VALUES(?,?,?,?,?,?,?)',(episode,self.bot,'QA0/USD',time.time(),60,1,None))
    __import__('demo_learning').learn(c,self.bot,episode,'isolated-pass-fixture',1)
  rid,result=self.review()
  for rating in result['ratings']:
   if rating['bot']==self.bot:rating['score']=80
  return rid,result
 def test_passed_strategy_publishes_once_and_reaches_other_models_without_dollars(self):
  rid,result=self.seed_share_evidence();self.engine.apply_review(rid,result)
  with self.engine.db() as c:
   self.engine.model_roster.publish_lessons(c,rid,result)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM population_lessons').fetchone()[0],1)
  target=self.engine.bot_names()[-1];observation=self.engine.market_context(target)
  self.assertEqual(len(observation['shared_strategy_lessons']),1)
  payload=json.dumps(observation['shared_strategy_lessons']).lower()
  for private in ['net_usd','equity','cash','cost_basis','entry_price']:self.assertNotIn(private,payload)
 def test_passing_reviewer_score_alone_cannot_publish_losing_strategy(self):
  rid,result=self.review();result['ratings'][0]['score']=100;self.engine.apply_review(rid,result)
  self.assertEqual(self.engine.model_roster.status()['lessons'],[])
 def test_different_model_or_strategy_outcomes_cannot_be_relabelled_as_passing(self):
  rid,result=self.seed_share_evidence()
  with self.engine.db() as c:c.execute("UPDATE population_bots SET model='different-model' WHERE bot=?",(self.bot,));c.execute("UPDATE population_ai SET config=? WHERE target=?",(json.dumps(dict(provider='Mirai',model='different-model',effort=None)),self.bot))
  self.engine.apply_review(rid,result);self.assertEqual(self.engine.model_roster.status()['lessons'],[])

# Avoid duplicating the fixture's inherited suite; these are new targeted checks.
for name in list(vars(Fixtures)):
 if name.startswith('test_') and name not in vars(ControlTests):setattr(ControlTests,name,None)
if __name__=='__main__':
 suite=unittest.TestLoader().loadTestsFromTestCase(ControlTests)
 result=unittest.TextTestRunner(verbosity=1).run(suite)
 raise SystemExit(0 if result.wasSuccessful() else 1)
