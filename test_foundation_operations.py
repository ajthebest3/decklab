"""Origin/revision-bound Fable coordinator; enabled on disposable fixtures only."""
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from operations import OriginalStop,OperationError


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'test.db';self.lock=threading.Lock()
        self.op=OriginalStop(self.connect,self.lock,enabled=True)
        c=self.connect()
        try:
            with c:
                c.executescript('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);CREATE TABLE protected_ledger(id INTEGER PRIMARY KEY,amount REAL);INSERT INTO settings VALUES(\'kill_switch\',\'false\');INSERT INTO protected_ledger VALUES(1,123.45);')
                self.op.init(c)
        finally:c.close()
        self.origin='http://localhost:8790'

    def connect(self):return sqlite3.connect(self.path)

    def body(self):
        state=self.op.inspect(self.origin)
        return {'command_id':'command_test_001','origin':self.origin,'server_id':state['server_id'],'account':'original','settings_revision':state['settings_revision']}

    def query(self,sql):
        c=self.connect()
        try:return c.execute(sql).fetchall()
        finally:c.close()

    def assert_error(self,code,fn):
        with self.assertRaises(OperationError) as e:fn()
        self.assertEqual(e.exception.code,code)

    def test_default_off_never_changes_settings(self):
        off=OriginalStop(self.connect,self.lock)
        self.assert_error('feature_disabled',lambda:off.stop(self.body(),self.origin))
        self.assertEqual(self.query("SELECT value FROM settings WHERE key='kill_switch'"),[('false',)])

    def test_exact_duplicate_returns_original_before_revision_check(self):
        body=self.body();result=self.op.stop(body,self.origin)
        self.assertEqual(result,self.op.stop(body,self.origin))
        self.assertEqual(self.query('SELECT COUNT(*) FROM foundation_commands'),[(1,)])
        self.assertEqual(self.op.inspect(self.origin,body['command_id'])['result'],result)
        self.assertEqual(result['holdings'],'retained')
        self.assertEqual(self.query('SELECT * FROM protected_ledger'),[(1,123.45)])

    def test_changed_payload_under_same_id_conflicts(self):
        body=self.body();self.op.stop(body,self.origin)
        changed={**body,'settings_revision':'1'}
        self.assert_error('command_conflict',lambda:self.op.stop(changed,self.origin))

    def test_origin_and_server_rebinding_rejected(self):
        body=self.body()
        self.assert_error('origin_mismatch',lambda:self.op.stop(body,'http://localhost:9999'))
        self.assert_error('server_mismatch',lambda:self.op.stop({**body,'server_id':'f'*32},self.origin))
        self.assertEqual(self.query('SELECT COUNT(*) FROM foundation_commands'),[(0,)])

    def test_lost_ack_recovery_after_process_recreation(self):
        body=self.body();result=self.op.stop(body,self.origin)
        recreated=OriginalStop(self.connect,self.lock,enabled=True)
        self.assertEqual(recreated.inspect(self.origin,body['command_id'])['result'],result)
        self.assertEqual(recreated.stop(body,self.origin),result)

    def test_stale_monotonic_revision_prevents_aba(self):
        body=self.body();c=self.connect()
        try:
            with c:
                c.execute("UPDATE settings SET value='true' WHERE key='kill_switch'");self.op.bump(c)
                c.execute("UPDATE settings SET value='false' WHERE key='kill_switch'");self.op.bump(c)
        finally:c.close()
        self.assert_error('revision_conflict',lambda:self.op.stop(body,self.origin))

    def test_failure_before_commit_rolls_back_effect_revision_and_command(self):
        body=self.body()
        class BrokenConnection(sqlite3.Connection):
            def commit(self):raise sqlite3.OperationalError('private disk failure')
        broken=OriginalStop(lambda:sqlite3.connect(self.path,factory=BrokenConnection),self.lock,enabled=True)
        self.assert_error('command_uncertain',lambda:broken.stop(body,self.origin))
        self.assertEqual(self.query("SELECT value FROM settings WHERE key='kill_switch'"),[('false',)])
        self.assertEqual(self.op.inspect(self.origin)['settings_revision'],'0')
        self.assertEqual(self.query('SELECT COUNT(*) FROM foundation_commands'),[(0,)])

    def test_commit_succeeded_but_ack_failed_reconciles_same_id(self):
        body=self.body()
        class LostAck(sqlite3.Connection):
            def commit(self):
                super().commit();raise sqlite3.OperationalError('ack interrupted')
        lost=OriginalStop(lambda:sqlite3.connect(self.path,factory=LostAck),self.lock,enabled=True)
        self.assert_error('command_uncertain',lambda:lost.stop(body,self.origin))
        self.assertEqual(self.op.inspect(self.origin,body['command_id'])['result']['state'],'applied')
        self.assertEqual(self.op.stop(body,self.origin)['state'],'applied')
        self.assertEqual(self.query('SELECT COUNT(*) FROM foundation_commands'),[(1,)])

    def test_unknown_command_and_malformed_payload_fail_closed(self):
        self.assert_error('command_not_found',lambda:self.op.inspect(self.origin,'not_found_id'))
        for change in [{'extra':1},{'command_id':'invalid\n'},{'account':'managed'},{'settings_revision':'²'}]:
            body=self.body();body.update(change)
            self.assert_error('invalid_request',lambda:self.op.stop(body,self.origin))

    def test_interrupted_metadata_migration_rolls_back_and_retries(self):
        path=Path(self.tmp.name)/'migration.db';c=sqlite3.connect(path)
        try:
            c.execute('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT)')
            self.op.init(c);c.rollback()
            self.assertFalse(c.execute("SELECT 1 FROM sqlite_master WHERE name='foundation_commands'").fetchone())
            self.assertFalse(c.execute("SELECT 1 FROM settings WHERE key='foundation_server_identity'").fetchone())
            self.op.init(c);c.commit()
            identity=self.op.server_identity(c)
            self.op.init(c);c.commit()
            self.assertEqual(self.op.server_identity(c),identity)
        finally:c.close()


if __name__=='__main__':unittest.main(verbosity=2)
