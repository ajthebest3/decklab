"""Isolated Day Trader boundary and actual pinned-tool pipeline checks."""
import json,sqlite3,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from day_trader import DayTrader,VENDOR
class C(sqlite3.Connection):
 def __exit__(self,*args):
  try:return super().__exit__(*args)
  finally:self.close()
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.stop=threading.Event()
  def db():
   c=sqlite3.connect(self.root/'test.db',factory=C);c.row_factory=sqlite3.Row;return c
  self.db=db;self.d=DayTrader(self.root,db,lambda c,q,a=():[dict(r) for r in c.execute(q,a)],self.stop)
  with db() as c:
   self.d.init(c);c.execute('CREATE TABLE protected(cash,canary)');c.execute("INSERT INTO protected VALUES(50000,'PRIVATE_ACCOUNT_CANARY')")
 def req(self,**kw):return self.d.validate(dict(tool='analyze',symbols='TSLA',request_id='fixture-request-001',**kw))
 def wait(self,jid):
  for _ in range(1000):
   j=self.d.status({'id':[str(jid)]})
   if j['state']!='running':return j
   time.sleep(.01)
  self.fail('Job did not finish')
 def test_validation_rejects_execution_shell_and_wrong_markets(self):
  for body in [dict(tool='approve'),dict(symbols='BTC/USD'),dict(symbols='RELIANCE.NS'),dict(symbols='AAPLx/USD'),dict(symbols='$(id)'),dict(budget=float('nan')),dict(budget=True),dict(enabled=True),dict(tool='analyst')]:
   r=dict(tool='analyze',symbols='TSLA',request_id='fixture-invalid-001');r.update(body)
   with self.assertRaises(ValueError):self.d.validate(r)
 def test_idempotency_and_account_preservation(self):
  with patch.object(self.d,'evaluate',return_value={'steps':{'clock':{'state':'completed','data':{'open':False}}}}):
   first=self.d.submit(self.req());j=self.wait(first['id']);again=self.d.submit(self.req())
  self.assertTrue(again['reused']);self.assertEqual(first['id'],again['id']);self.assertEqual(j['state'],'completed')
  with self.db() as c:self.assertEqual(tuple(c.execute('SELECT * FROM protected').fetchone()),(50000,'PRIVATE_ACCOUNT_CANARY'))
  r=self.req();r['symbols']=['MSFT']
  with self.assertRaises(ValueError):self.d.submit(r)
 def test_stop_kills_running_subprocess(self):
  self.stop.set();work=self.root/'stop';work.mkdir()
  value=self.d.command(work,'trader-alerts','alerts.py',['clock','--json'])
  self.assertIn(value['state'],('interrupted','completed'))
 def test_restart_interrupts_without_replay(self):
  with self.db() as c:
   c.execute("INSERT INTO day_trader_jobs(state,request_id,symbols) VALUES('running','interrupted-fixture','[]')");self.d.init(c)
  self.assertEqual(self.d.status()['jobs'][0]['state'],'interrupted')
 def test_public_context_excludes_accounting_and_old_jobs(self):
  value={'steps':{'entry':{'data':{'status':'waiting'}},'budget':{'data':'PRIVATE_ACCOUNT_CANARY'},'ticket':{'data':123},'risk':{'data':456}}}
  with self.db() as c:
   for age in (0,1000):c.execute("INSERT INTO day_trader_jobs(created,state,symbols,result_json) VALUES(?,'completed',?,?)",(time.time()-age,'["TSLA"]',json.dumps(value)))
  public=self.d.public_context(['TSLA']);self.assertEqual(len(public),1)
  self.assertNotIn('PRIVATE_ACCOUNT_CANARY',json.dumps(public));self.assertNotIn('budget',json.dumps(public));self.assertEqual(self.d.public_context(['BTC/USD']),[])
 def test_real_pinned_pipeline_offline(self):
  original=self.d.command;fix=VENDOR/'tests/fixtures'
  def fixture(work,folder,script,args):
   args=list(args)
   if folder=='trader-news':return dict(state='completed',data={'fixture':'offline news; no live provider call'})
   if folder=='trader-entry':args+=['--offline',str(fix/'trader-entry/TSLA-2026-10-19-5m.json')]
   if folder=='trader-timemachine':args+=['--offline',str(fix/'trader-timemachine/TSLA-60d5m.json.gz')];args[args.index('--replays')+1]='100'
   if folder in ('trader-entry','trader-exit','trader-timemachine','trader-budget','trader-risk','trader-broker'):args+=['--now','2026-10-19 10:15']
   return original(work,folder,script,args)
  work=self.root/'pipeline';work.mkdir()
  req=self.req();req.update(budget=1000,max_loss=20) # Offline fixture only: TSLA costs more than the live $250 planning ceiling.
  with patch.object(self.d,'command',side_effect=fixture):result=self.d.evaluate(req,work)
  steps=result['steps'];self.assertEqual(steps['entry']['data']['status'],'triggered')
  for key in ('exit','replay','budget','ticket','alerts'):self.assertEqual(steps[key]['state'],'completed',(key,steps[key]))
  self.assertIn('risk',steps);self.assertTrue((work/'trader/alerts.json').exists())
 def test_waiting_never_builds_a_ticket(self):
  def command(work,folder,script,args):
   if folder=='trader-entry':(work/'trader/entry.json').write_text('{"status":"waiting"}')
   return dict(state='completed',data={'status':'waiting'})
  work=self.root/'waiting';work.mkdir()
  with patch.object(self.d,'command',side_effect=command):result=self.d.evaluate(self.req(),work)
  self.assertNotIn('ticket',result['steps']);self.assertEqual(result['steps']['planning']['state'],'skipped')
if __name__=='__main__':unittest.main(verbosity=2)
