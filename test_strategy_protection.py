"""Isolated regressions for the changes justified by the frozen strategy audit."""
import json
import time
import unittest
from unittest.mock import patch

from test_population import PopulationTests as Fixtures
from population_engine import STRATEGY_DEFAULT, strategy


class StrategyProtectionTests(Fixtures):
 def protect(self,**values):
  self.engine.configure(values)

 def reward(self,points=-5,context='old',episode=9000):
  with self.engine.db() as c:
   c.execute('INSERT INTO demo_rewards VALUES(?,?,?,?,?,?,?)',(episode,self.bot,'QA0/USD',time.time()+episode,-1,points,episode))

 def test_zero_exploration_is_a_valid_model_choice(self):
  self.assertEqual(strategy(dict(STRATEGY_DEFAULT,exploration_rate=0))['exploration_rate'],0)
  for value in (-.01,.251):
   with self.assertRaises(ValueError):strategy(dict(STRATEGY_DEFAULT,exploration_rate=value))

 def test_zero_owner_cap_blocks_random_entries_even_with_model_exploration(self):
  self.protect(exploration_cap=0)
  self.seed_model(policy={'threshold_pct':5})
  with patch('population_engine.random.random',return_value=0):
   self.assertEqual(self.engine.fast_policy(self.bot),[])

 def test_zero_exploration_still_allows_ready_signals(self):
  self.protect(exploration_cap=0)
  self.seed_model(policy={'exploration_rate':0,'threshold_pct':.1})
  ids=self.engine.fast_policy(self.bot)
  self.assertTrue(ids)
  with self.engine.db() as c:
   result=json.loads(c.execute("SELECT result FROM demo_decisions WHERE source='point_policy' ORDER BY id DESC LIMIT 1").fetchone()[0])
   self.assertTrue(all(not a['exploration'] for a in result['actions']))

 def test_unready_features_never_explore(self):
  with self.engine.db() as c:c.execute('DELETE FROM history')
  self.seed_model(policy={'threshold_pct':5})
  with patch('population_engine.random.random',return_value=0):
   self.assertEqual(self.engine.fast_policy(self.bot),[])

 def test_three_losses_override_learning_mode(self):
  self.protect(respect_loss_brakes=True,learning_mode=True,cost_guard=False)
  for n in range(3):self.reward(episode=9000+n)
  with self.assertRaisesRegex(ValueError,'circuit breaker'):self.buy()
  self.assertTrue(next(b for b in self.engine.status()['bots'] if b['bot']==self.bot)['entry_brake']['blocked'])

 def test_context_loss_is_blocked_before_streak_limit(self):
  self.protect(respect_loss_brakes=True,cost_guard=False)
  oid=self.buy();self.reward(context='fixture|QA0/USD',episode=oid)
  with self.engine.db() as c:c.execute("UPDATE demo_orders SET state='filled' WHERE id=?",(oid,))
  with self.assertRaisesRegex(ValueError,'context lost'):self.buy(key='repeat')

 def test_review_cannot_clear_entry_brake(self):
  self.protect(respect_loss_brakes=True,cost_guard=False)
  for n in range(3):self.reward(episode=9000+n)
  rid,result=self.review();self.engine.apply_review(rid,result)
  with self.assertRaisesRegex(ValueError,'circuit breaker'):self.buy()

 def test_brakes_never_prevent_exits(self):
  oid=self.buy();self.later(oid);self.engine.process_book(oid,self.book(),now=self.now)
  self.protect(respect_loss_brakes=True,cost_guard=False)
  for n in range(3):self.reward(episode=9000+n)
  sell=self.engine.submit(self.bot,'QA0/USD','sell','large','fixture','exit',None,'exit-under-brake')
  self.assertIsInstance(sell,int)

 def test_coverage_cost_guard_cannot_be_bypassed_by_learning_mode(self):
  self.protect(respect_loss_brakes=True,cost_guard=True,learning_mode=True)
  with self.engine.db() as c:c.execute('DELETE FROM history')
  with self.assertRaisesRegex(ValueError,'Cost guard'):self.buy()

 def test_cost_guard_also_works_without_loss_brakes(self):
  self.protect(respect_loss_brakes=False,cost_guard=True)
  with self.engine.db() as c:c.execute('DELETE FROM history')
  with self.assertRaisesRegex(ValueError,'Cost guard'):self.buy()

 def test_negative_q_reduces_final_percentage_budget(self):
  self.protect(point_scaled_allocation=True,max_allocation_pct=5)
  with self.engine.db() as c:c.execute('INSERT INTO demo_policy VALUES(?,?,?,?,?)',(self.bot,'fixture|QA0/USD',-2,1,self.now))
  oid=self.buy(policy={'allocation_pct':100})
  with self.engine.db() as c:
   budget=c.execute('SELECT budget FROM demo_orders WHERE id=?',(oid,)).fetchone()[0]
   self.assertAlmostEqual(budget,5000*.05*.45)

 def test_new_context_uses_disclosed_point_scale_and_keeps_cash(self):
  self.protect(point_scaled_allocation=True,max_allocation_pct=5)
  oid=self.buy(policy={'allocation_pct':100})
  with self.engine.db() as c:
   self.assertAlmostEqual(c.execute('SELECT budget FROM demo_orders WHERE id=?',(oid,)).fetchone()[0],187.5)
   self.assertEqual(c.execute('SELECT cash FROM demo_wallets WHERE bot=?',(self.bot,)).fetchone()[0],5000)

 def test_exact_q_lookup_works_beyond_latest_twenty_feedback_rows(self):
  context='older'
  with self.engine.db() as c:
   c.execute('INSERT INTO demo_policy VALUES(?,?,?,?,?)',(self.bot,context,-2,4,self.now-100))
   for n in range(30):c.execute('INSERT INTO demo_policy VALUES(?,?,?,?,?)',(self.bot,'recent-'+str(n),1,1,self.now+n))
   import demo_learning
   self.assertNotIn(context,{r['context'] for r in demo_learning.feedback(c,self.bot)['contexts']})
   self.assertEqual(self.engine.context_q(c,self.bot,context),-2)

 def test_parameter_identity_changes_learning_context_without_rewriting_history(self):
  a={'symbol':'QA0/USD','kind':'crypto','change':2}
  first=self.engine.strategy_context(a,'neutral',STRATEGY_DEFAULT)
  second=self.engine.strategy_context(a,'neutral',dict(STRATEGY_DEFAULT,hold_seconds=1200))
  self.assertNotEqual(first,second)
  self.assertEqual(first,self.engine.strategy_context(a,'neutral',dict(reversed(list(STRATEGY_DEFAULT.items())))))
  self.assertEqual(first,self.engine.strategy_context(a,'neutral',dict(STRATEGY_DEFAULT,hold_seconds=900.0)))

 def test_candidate_ranking_uses_older_persisted_q(self):
  self.protect(policy_batch_size=1)
  self.seed_model(policy={'threshold_pct':.1,'exploration_rate':0})
  obs=self.engine.market_context(self.bot)
  policy=obs['strategy'];context=self.engine.strategy_context(obs['markets'][0],'neutral',policy)
  with self.engine.db() as c:
   c.execute('INSERT INTO demo_policy VALUES(?,?,?,?,?)',(self.bot,context,-2,1,self.now-100))
   for n in range(30):c.execute('INSERT INTO demo_policy VALUES(?,?,?,?,?)',(self.bot,'other-'+str(n),1,1,self.now+n))
  ids=self.engine.fast_policy(self.bot)
  self.assertEqual(len(ids),1)
  with self.engine.db() as c:self.assertEqual(c.execute('SELECT symbol FROM demo_orders WHERE id=?',(ids[0],)).fetchone()[0],'QA1/USD')

 def test_exit_rules_fixed_through_model_revision_and_owner_relaxation(self):
  self.protect(pin_exit_rules=True)
  oid=self.buy(policy={'hold_seconds':1200,'stop_pct':3,'take_pct':4});self.later(oid)
  self.engine.process_book(oid,self.book(),now=self.now)
  self.seed_model(policy={'hold_seconds':120,'stop_pct':10,'take_pct':20})
  self.protect(max_hold_seconds=86400,stop_pct=100,take_pct=1000,pin_exit_rules=False)
  with self.engine.db() as c:
   p=c.execute('SELECT * FROM demo_positions WHERE episode=?',(oid,)).fetchone()
   self.assertEqual(self.engine.exit_rules(c,p,self.engine.settings(c),None),dict(hold_seconds=1200,stop_pct=3,take_pct=4))

 def test_global_safety_can_tighten_pinned_rules(self):
  self.protect(pin_exit_rules=True)
  oid=self.buy(policy={'hold_seconds':1200,'stop_pct':3,'take_pct':4});self.later(oid)
  self.engine.process_book(oid,self.book(),now=self.now)
  self.protect(max_hold_seconds=600,stop_pct=1,take_pct=2)
  with self.engine.db() as c:
   p=c.execute('SELECT * FROM demo_positions WHERE episode=?',(oid,)).fetchone()
   self.assertEqual(self.engine.exit_rules(c,p,self.engine.settings(c),None),dict(hold_seconds=600,stop_pct=1,take_pct=2))

 def test_actual_risk_cycle_keeps_pinned_horizon_after_revision(self):
  self.protect(pin_exit_rules=True)
  oid=self.buy(policy={'hold_seconds':1200});self.later(oid)
  self.engine.process_book(oid,self.book(),now=self.now)
  with self.engine.db() as c:c.execute('UPDATE demo_positions SET opened=?',(self.now-600,))
  self.seed_model(policy={'hold_seconds':120})
  self.engine.cached_books['QA0/USD']=self.book()
  self.engine.refresh_marks_and_risk(cached_only=True)
  with self.engine.db() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM demo_orders WHERE side='sell'").fetchone()[0],0)
  with self.engine.db() as c:c.execute('UPDATE demo_positions SET opened=?',(self.now-1300,))
  self.engine.refresh_marks_and_risk(cached_only=True)
  with self.engine.db() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM demo_orders WHERE side='sell'").fetchone()[0],1)

 def test_legacy_exit_uses_recorded_entry_not_new_model_rules(self):
  oid=self.buy(policy={'hold_seconds':1200});self.later(oid)
  self.engine.process_book(oid,self.book(),now=self.now)
  self.seed_model(policy={'hold_seconds':120})
  self.protect(pin_exit_rules=True)
  p=next(b for b in self.engine.status()['bots'] if b['bot']==self.bot)['positions'][0]
  self.assertEqual(p['exit_rules']['hold_seconds'],1200)
  self.assertEqual(p['exit_rule_basis'],'legacy_entry_record')

 def test_additions_cannot_mix_revisions_in_pinned_position(self):
  self.protect(pin_exit_rules=True)
  oid=self.buy();self.later(oid);self.engine.process_book(oid,self.book(),now=self.now)
  with self.assertRaisesRegex(ValueError,'pyramiding'):self.buy(key='mixed-add',policy={'threshold_pct':.5})

 def test_risk_control_change_cancels_pending_buys_and_demands_new_model(self):
  oid=self.buy()
  self.protect(exploration_cap=0)
  with self.engine.db() as c:self.assertEqual(c.execute('SELECT state FROM demo_orders WHERE id=?',(oid,)).fetchone()[0],'cancelled')
  self.assertEqual(self.engine.fast_policy(self.bot),[])
  self.seed_model(policy={'exploration_rate':0})
  self.assertTrue(self.engine.fast_policy(self.bot))

 def test_stopped_protection_changes_preserve_wallets_and_positions(self):
  oid=self.buy();self.later(oid);self.engine.process_book(oid,self.book(),now=self.now)
  self.protect(enabled=False)
  with self.engine.db() as c:
   before={t:[tuple(r) for r in c.execute('SELECT * FROM '+t)] for t in ('demo_wallets','demo_positions','demo_fills','demo_rewards','demo_cash_ledger','population_funding')}
  self.protect(exploration_cap=0,respect_loss_brakes=True,point_scaled_allocation=True,pin_exit_rules=True,allow_additions=False,auto_replace=False)
  self.engine.initialize();self.engine.cycle()
  with self.engine.db() as c:
   for t,rows in before.items():self.assertEqual(rows,[tuple(r) for r in c.execute('SELECT * FROM '+t)],t)
   self.assertFalse(self.engine.settings(c)['enabled'])

 def test_new_phase_excludes_old_entries_even_when_they_close_later(self):
  oid=self.buy()
  self.protect(exploration_cap=0)
  self.reward(episode=oid)
  evaluation=self.engine.status()['strategy_evaluation']
  self.assertEqual(evaluation['closed_episodes'],0)
  self.assertEqual(evaluation['net_usd'],0)
  # Fresh actual model after control change; count only this new entry.
  new=self.buy(symbol='QA1/USD',key='new-phase')
  self.reward(episode=new)
  self.assertEqual(self.engine.status()['strategy_evaluation']['closed_episodes'],1)

 def test_pause_does_not_queue_exit_at_expired_horizon(self):
  oid=self.buy();self.later(oid);self.engine.process_book(oid,self.book(),now=self.now)
  self.protect(enabled=False,pin_exit_rules=True)
  with self.engine.db() as c:c.execute('UPDATE demo_positions SET opened=?',(self.now-10000,))
  self.engine.refresh_marks_and_risk(cached_only=True)
  with self.engine.db() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM demo_orders WHERE side='sell'").fetchone()[0],0)

 def test_observation_remains_point_only_and_discloses_controls(self):
  self.protect(exploration_cap=0,respect_loss_brakes=True,point_scaled_allocation=True,pin_exit_rules=True)
  self.check_observation_boundary()

 def check_observation_boundary(self):
  # Called explicitly below; retain the original boundary check unchanged.
  Fixtures.test_observation_has_no_wallet_or_execution_history(self)
  obs=self.engine.market_context(self.bot)
  self.assertEqual(obs['owner_limits']['exploration_cap'],0)
  self.assertIn('Loss brakes are enforced',obs['entry_protection']['rule'])


for name in vars(Fixtures):
 if name.startswith('test_') and name not in vars(StrategyProtectionTests):setattr(StrategyProtectionTests,name,None)
if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.TestLoader().loadTestsFromTestCase(StrategyProtectionTests))
 raise SystemExit(0 if result.wasSuccessful() else 1)
