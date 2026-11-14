"""Isolated feed-worker recovery tests: no provider requests or production writes."""
import os,tempfile,sqlite3,unittest,time
from unittest.mock import patch,Mock
TMP=tempfile.TemporaryDirectory(prefix='feed-recovery-');os.environ['MARKET_DECK_DATA']=TMP.name
import server as s
class FeedRecoveryTests(unittest.TestCase):
 def test_status_write_failure_is_contained(self):
  with patch.object(s,'provider',side_effect=sqlite3.OperationalError('database is locked')):
   s.feed_failure('Kraken quotes',sqlite3.OperationalError('database is locked'))
 def test_worker_retries_cycle_after_database_lock(self):
  stop=Mock();stop.is_set.side_effect=[False,False,True]
  with patch.object(s,'STOP',stop),patch.object(s,'poll_cycle',side_effect=[sqlite3.OperationalError('database is locked'),None]) as cycle:
   s.poll();self.assertEqual(cycle.call_count,2);self.assertIs(cycle.call_args_list[0].args[0],cycle.call_args_list[1].args[0]);self.assertEqual(stop.wait.call_count,2)
 def test_quote_and_error_write_failure_do_not_stop_next_cycle(self):
  now=time.time();schedule=dict.fromkeys(['stocks','news','catalog','clean'],now)
  with patch.object(s,'crypto_quotes',side_effect=[sqlite3.OperationalError('database is locked'),None]) as crypto,patch.object(s,'nse_quotes') as nse,patch.object(s,'provider',side_effect=sqlite3.OperationalError('database is locked')),patch.object(s,'automation'):
   s.poll_cycle(schedule);s.poll_cycle(schedule);self.assertEqual(crypto.call_count,2);self.assertEqual(nse.call_count,2)
 def test_normal_cadence_is_retained(self):
  now=time.time();schedule=dict(stocks=0,news=0,catalog=now,clean=now)
  with patch.object(s,'crypto_quotes'),patch.object(s,'nse_quotes'),patch.object(s,'stocks') as stocks,patch.object(s,'news_feed') as news,patch.object(s,'automation'):
   s.poll_cycle(schedule);s.poll_cycle(schedule);self.assertEqual(stocks.call_count,1);self.assertEqual(news.call_count,len(s.FEEDS))
if __name__=='__main__':unittest.main(verbosity=2)
