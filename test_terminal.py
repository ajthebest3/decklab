"""Isolated terminal metrics, read-only behavior and Mirai prompt boundary."""
import json,threading,time,unittest
from unittest.mock import Mock
import test_population as fixtures
from terminal_engine import TerminalEngine

class TerminalTests(unittest.TestCase):
 def setUp(self):
  fixtures.PopulationTests.setUp(self)
  with self.source() as c:
   c.execute('CREATE TABLE providers(name TEXT,state TEXT,message TEXT,checked REAL)')
   c.execute("INSERT INTO providers VALUES('Fixture','ok','Observed fixture',?)",(self.now,))
  self.mirai=Mock();self.mirai.status.return_value=dict(enabled=True,key_configured=True,model='fixture-model')
  self.mirai.complete.return_value='Observed: fixture quote only. Watch next: source freshness.'
  self.t=TerminalEngine(self.source,fixtures.rows,self.engine,self.mirai,self.stop)
  with self.source() as c:self.t.init(c)
 def wait(self):
  for _ in range(200):
   with self.source() as c:row=c.execute('SELECT * FROM terminal_briefs ORDER BY id DESC LIMIT 1').fetchone()
   if row and row['state']!='running':return dict(row)
   time.sleep(.01)
  self.fail('Research fixture did not finish')
 def request(self,**kwargs):return self.t.submit(dict(symbol='QA0/USD',topic='Explain observed conditions',request_id='fixture-terminal-1',**kwargs))
 def test_status_cannot_change_financial_tables_or_start_jobs(self):
  with self.engine.db() as c:before={t:c.execute('SELECT * FROM '+t).fetchall() for t in ('demo_wallets','demo_orders','demo_fills','demo_positions','demo_rewards','demo_settings')}
  self.engine.configure({'enabled':False})
  with self.engine.db() as c:before['demo_settings']=c.execute('SELECT * FROM demo_settings').fetchall()
  for _ in range(2):s=self.t.status()
  with self.engine.db() as c:
   for table,value in before.items():self.assertEqual(value,c.execute('SELECT * FROM '+table).fetchall(),table)
  self.assertFalse(s['settings']['enabled']);self.assertFalse(next(r for r in s['rules'] if r['key']=='running')['passed']);self.mirai.complete.assert_not_called()
 def test_public_context_contains_no_accounting_or_private_canary(self):
  self.request();row=self.wait();self.assertEqual(row['state'],'completed')
  context=json.loads(row['input_json']);self.assertEqual(set(context),{'asof','focus','history','headlines'})
  prompt=self.mirai.complete.call_args.args[0]
  for canary in ('DO_NOT_COPY_ACCOUNT','cash_usd','initial_usd','cost_basis','private_wallet','demo_wallets','net_usd'):
   self.assertNotIn(canary,prompt)
  self.assertEqual(self.mirai.complete.call_args.kwargs['model'],'fixture-model')
 def test_request_id_retry_is_idempotent_and_collision_rejected(self):
  first=self.request();self.wait();second=self.request();self.assertEqual(first['id'],second['id']);self.assertTrue(second['reused']);self.assertEqual(self.mirai.complete.call_count,1)
  with self.assertRaisesRegex(ValueError,'another question'):self.t.submit(dict(symbol='QA0/USD',topic='Different',request_id='fixture-terminal-1'))
 def test_research_errors_are_saved_and_credentials_redacted(self):
  self.mirai.complete.side_effect=ValueError('fixture failure sk-THIS_IS_A_PRIVATE_TEST_KEY_12345')
  self.request();row=self.wait();self.assertEqual(row['state'],'failed');self.assertNotIn('sk-',row['error']);self.assertIn('[redacted credential]',row['error'])
 def test_unknown_symbol_and_oversized_question_cannot_call_mirai(self):
  for body in (dict(symbol='UNKNOWN',topic='Test',request_id='fixture-bad-symbol'),dict(symbol='QA0/USD',topic='x'*1001,request_id='fixture-too-long'),dict(symbol='QA0/USD',topic='Test',request_id='short'),dict(symbol='QA0/USD',topic='Test',request_id='fixture-extra',enabled=True)):
   with self.assertRaises(ValueError):self.t.submit(body)
  self.mirai.complete.assert_not_called()
 def test_one_request_inflight_and_global_cooldown(self):
  release=threading.Event();self.addCleanup(release.set)
  self.mirai.complete.side_effect=lambda *a,**kw:(release.wait(1),'Fixture result')[1]
  self.request()
  with self.assertRaisesRegex(ValueError,'already running'):self.t.submit(dict(symbol='QA1/USD',topic='Test',request_id='fixture-parallel'))
  release.set();self.wait()
  with self.assertRaisesRegex(ValueError,'30 seconds'):self.t.submit(dict(symbol='QA1/USD',topic='Test',request_id='fixture-next'))
 def test_restart_interrupts_without_automatic_resubmit(self):
  with self.source() as c:
   c.execute("INSERT INTO terminal_briefs(request_id,created,state,symbol,topic,model) VALUES('fixture-interrupt',?,'running','QA0/USD','Fixture','fixture')",(self.now,));self.t.init(c)
   self.assertEqual(c.execute('SELECT state FROM terminal_briefs').fetchone()[0],'interrupted')
  self.mirai.complete.assert_not_called()
 def test_completed_episode_metrics_are_exact_and_finite(self):
  with self.engine.db() as c:
   for i,(net,points) in enumerate(((5,1),(-2,-5),(0,0))):c.execute('INSERT INTO demo_rewards VALUES(?,?,?,?,?,?,?)',(i+1,self.bot,'QA0/USD',self.now,net,points,i+100))
  s=self.t.status()['statistics'];self.assertEqual(s['closed'],3);self.assertEqual(s['closed_net'],3);self.assertEqual(s['profit_factor'],2.5);self.assertAlmostEqual(s['wins_pct'],100/3);self.assertEqual(s['expectancy'],1)
 def test_no_completed_outcomes_stays_empty(self):
  s=self.t.status()['statistics'];self.assertIsNone(s['wins_pct']);self.assertIsNone(s['profit_factor']);self.assertIsNone(s['expectancy']);self.assertEqual(s['closed_net'],0)
 def test_stale_quote_fails_filter_instead_of_inventing_data(self):
  with self.source() as c:c.execute('UPDATE quotes SET asof=? WHERE symbol=?',(self.now-1000,'QA0/USD'))
  s=self.t.status({'symbol':['QA0/USD']});self.assertFalse(s['focus']['quote_fresh']);self.assertFalse(next(r for r in s['rules'] if r['key']=='fresh')['passed'])
 def test_ratings_are_actual_saved_scores(self):
  with self.engine.db() as c:c.execute('UPDATE population_bots SET score=37,score_reason=? WHERE bot=?',('Saved fixture rating',self.bot))
  s=self.t.status({'bot':[self.bot]});a=next(a for a in s['agents'] if a['bot']==self.bot);self.assertEqual(a['score'],37);self.assertEqual(a['score_reason'],'Saved fixture rating')

if __name__=='__main__':unittest.main(verbosity=2)
