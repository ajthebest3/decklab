"""Phase1 read-only readiness contracts on disposable stores only."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from foundation import readiness


class ClosingConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try:return super().__exit__(*args)
        finally:self.close()


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.db = self.data/'fixture.db'
        self.now = 1000000.
        with self.connect() as c:
            c.executescript('''
                CREATE TABLE assets(symbol TEXT PRIMARY KEY,kind TEXT);
                CREATE TABLE quotes(symbol TEXT PRIMARY KEY,price REAL,asof REAL,fetched REAL,source TEXT);
                CREATE TABLE providers(name TEXT,state TEXT,checked REAL);
                CREATE TABLE demo_fx(currency TEXT,units_per_usd REAL,asof REAL,fetched REAL,source TEXT);
                CREATE TABLE settings(key TEXT,value TEXT);
                INSERT INTO settings VALUES('kill_switch','true'),('autopilot','false'),('private-key','"do-not-expose"');
            ''')
        self.connections = []

    def connect(self):
        return sqlite3.connect(self.db,factory=ClosingConnection)

    def snapshot(self):
        return readiness(self.data, self.connect, 'http://localhost:8790', now=self.now)

    def quote(self, symbol, kind, source_age=10, receipt_age=5, price=1):
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO assets VALUES(?,?)',(symbol,kind))
            c.execute('INSERT OR REPLACE INTO quotes VALUES(?,?,?,?,?)',(symbol,price,self.now-source_age,self.now-receipt_age,'Kraken public observations'))

    def test_pause_is_explicit_and_does_not_unpause_from_absence(self):
        result=self.snapshot()
        self.assertEqual(result['owner_pause']['state'],'unknown')
        (self.data/'owner-research-paused-until-asked').write_text('secret marker contents must never be read')
        result=self.snapshot()
        self.assertEqual(result['health_state'],'paused')
        self.assertTrue(result['owner_pause']['active'])
        self.assertNotIn('secret marker',json.dumps(result))

    def test_mixed_freshness_uses_asset_kind_not_provider_name(self):
        self.quote('BTC/USD','crypto',source_age=180)
        self.quote('AAPL','equity',source_age=180)
        result=self.snapshot()['resources']['quotes']
        self.assertEqual(result['state'],'partial')
        rows={r['symbol']:r for r in result['items']}
        self.assertEqual(rows['BTC/USD']['state'],'stale')
        self.assertEqual(rows['AAPL']['state'],'fresh')
        self.assertIsNone(rows['AAPL']['last_success'])
        self.assertIsNone(rows['AAPL']['clock_skew_seconds'])
        self.assertEqual(rows['BTC/USD']['source_timestamp'],self.now-180)

    def test_receipt_time_cannot_make_old_source_fresh(self):
        self.quote('BTC/USD','crypto',source_age=500,receipt_age=0)
        row=self.snapshot()['resources']['quotes']['items'][0]
        self.assertEqual(row['state'],'stale')
        self.assertEqual(row['received_at'],self.now)
        self.assertEqual(row['source_timestamp'],self.now-500)

    def test_future_source_or_receipt_cannot_be_fresh(self):
        for source_age,receipt_age in [(-60,0),(0,-60)]:
            self.quote('AAPL','equity',source_age,receipt_age)
            self.assertEqual(self.snapshot()['resources']['quotes']['items'][0]['state'],'clock-invalid')

    def test_fx_has_independent_threshold_and_never_exposes_amounts(self):
        with self.connect() as c:
            c.execute('INSERT INTO demo_fx VALUES(?,?,?,?,?)',('INR',84,self.now-1800,self.now-1800,'public FX'))
        result=self.snapshot()
        self.assertEqual(result['resources']['fx']['items'][0]['state'],'fresh')
        self.assertNotIn('units_per_usd',json.dumps(result))

    def test_missing_schema_and_connection_failure_stay_unknown(self):
        with self.connect() as c:c.execute('DROP TABLE quotes')
        self.assertEqual(self.snapshot()['resources']['quotes']['state'],'unknown')
        def fail():raise sqlite3.OperationalError('private database path and secret')
        result=readiness(self.data,fail,'http://localhost',now=self.now)
        self.assertEqual(result['resources']['quotes']['state'],'unknown')
        self.assertNotIn('private database',json.dumps(result))

    def test_no_writes_and_original_controls_only(self):
        traced=[]
        def monitored():
            c=self.connect();c.set_trace_callback(traced.append);return c
        before=self.db.read_bytes()
        result=readiness(self.data,monitored,'http://localhost',now=self.now)
        self.assertEqual(result['controls']['original'],{'kill_switch':True,'autopilot':False})
        self.assertEqual(before,self.db.read_bytes())
        self.assertTrue(all(s.startswith(('SELECT','PRAGMA query_only')) for s in traced))
        self.assertNotIn('do-not-expose',json.dumps(result))
        self.assertEqual(result['resources']['executable_books']['state'],'unknown')
        self.assertEqual(result['resources']['models']['state'],'unverified')
        self.assertFalse(result['compatibility']['new_mutations_enabled'])

    def test_provider_attempt_is_not_synthetic_success(self):
        with self.connect() as c:c.execute('INSERT INTO providers VALUES(?,?,?)',('Yahoo','error',self.now-2))
        row=self.snapshot()['resources']['providers']['items'][0]
        self.assertEqual(row['last_attempt'],self.now-2)
        self.assertIsNone(row['last_success'])
        self.assertEqual(row['state'],'error')

    def test_exact_limit_does_not_falsely_claim_truncation(self):
        with self.connect() as c:
            c.executemany('INSERT INTO assets VALUES(?,?)',((str(i),'equity') for i in range(5001)))
            c.executemany('INSERT INTO quotes VALUES(?,?,?,?,?)',((str(i),1,self.now,self.now,'public') for i in range(5000)))
        self.assertFalse(self.snapshot()['resources']['quotes']['truncated'])
        with self.connect() as c:c.execute('INSERT INTO quotes VALUES(?,?,?,?,?)',('5000',1,self.now,self.now,'public'))
        result=self.snapshot()['resources']['quotes']
        self.assertTrue(result['truncated'])
        self.assertEqual(len(result['items']),5000)
        self.assertNotEqual(result['state'],'fresh')

    def test_nonfinite_quote_values_are_not_serialized_as_nan(self):
        self.quote('AAPL','equity',price=float('inf'))
        result=self.snapshot()
        self.assertEqual(result['resources']['quotes']['items'][0]['state'],'unknown')
        json.dumps(result,allow_nan=False)


if __name__=='__main__':unittest.main(verbosity=2)
