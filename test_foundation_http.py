"""Phase1 HTTP/legacy scope tests against a disposable initialized backend."""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import http.client
import subprocess
from pathlib import Path
from unittest.mock import patch

TMP=tempfile.TemporaryDirectory(prefix='decklab-foundation-http-')
os.environ['MARKET_DECK_DATA']=TMP.name
import server as m
m.init()


class FoundationHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http=m.ThreadingHTTPServer(('127.0.0.1',0),m.Handler)
        m.PORT=cls.http.server_port
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()

    @classmethod
    def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();TMP.cleanup()

    def request(self,path,body=None,headers=None):
        req=urllib.request.Request('http://127.0.0.1:'+str(m.PORT)+path,
            data=json.dumps(body).encode() if body is not None else None,headers=headers or {})
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.load(r),r.headers
        except urllib.error.HTTPError as e:return e.code,json.load(e),e.headers

    def test_readiness_is_versioned_and_liveness_unchanged(self):
        _,health,_=self.request('/api/health')
        self.assertEqual(set(health),{'ok','mode','uptime'})
        code,result,headers=self.request('/api/v2/readiness')
        self.assertEqual(code,200);self.assertEqual(result['contract_version'],'2.0')
        self.assertTrue(result['compatibility']['schema_compatible'])
        self.assertEqual(len(result['compatibility']['backend_build']),64)
        self.assertEqual(len(headers['X-Request-ID']),24)
        self.assertFalse(result['compatibility']['new_mutations_enabled'])

    def test_host_query_and_post_origin_restrictions(self):
        self.assertEqual(self.request('/api/v2/readiness',headers={'Host':'evil.example'})[0],403)
        for host in ['localhost:bad','localhost:99999','localhost:8790.evil.example','127.0.0.1:0']:
            self.assertEqual(self.request('/api/v2/readiness',headers={'Host':host})[0],403)
        result=self.request('/api/v2/readiness',headers={'Host':'LOCALHOST:08790'})[1]
        self.assertEqual(result['origin'],'http://localhost:8790')
        conn=http.client.HTTPConnection('127.0.0.1',m.PORT)
        try:
            conn.putrequest('GET','/api/v2/readiness',skip_host=True)
            conn.putheader('Host','localhost');conn.putheader('Host','evil.example');conn.endheaders()
            self.assertEqual(conn.getresponse().status,403)
        finally:conn.close()
        self.assertEqual(self.request('/api/v2/readiness?extra=1')[0],400)
        self.assertEqual(self.request('/api/settings',{},headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/api/settings',[])[0],400)

    def test_readiness_cannot_dispatch_models_or_provider_work(self):
        with patch.object(m.MIRAI,'request',side_effect=AssertionError('No API calls')) as call,patch.object(m.ARENA,'status',side_effect=AssertionError('No engine work')) as engine:
            self.assertEqual(self.request('/api/v2/readiness')[0],200)
            call.assert_not_called();engine.assert_not_called()

    def test_owner_pause_has_priority_and_marker_contents_private(self):
        marker=Path(TMP.name)/'owner-research-paused-until-asked'
        marker.write_text('private owner text')
        try:
            result=self.request('/api/v2/readiness')[1]
            self.assertEqual(result['health_state'],'paused')
            self.assertNotIn('private owner text',json.dumps(result))
        finally:marker.unlink()

    def test_legacy_original_stop_does_not_change_other_accounts(self):
        with m.db() as c:archive_before=m.DEMO.settings(c)
        with m.ARENA.db() as c:managed_before=m.ARENA.settings(c)
        self.assertEqual(self.request('/api/settings',{'kill_switch':True})[0],200)
        with m.db() as c:self.assertEqual(archive_before,m.DEMO.settings(c))
        with m.ARENA.db() as c:self.assertEqual(managed_before,m.ARENA.settings(c))
        self.assertTrue(self.request('/api/v2/readiness')[1]['controls']['original']['kill_switch'])
        self.assertEqual(self.request('/api/v2/operations/stop',{'command_id':'not-enabled'})[0],404)

    def test_unexpected_get_exception_does_not_expose_private_data(self):
        with patch.object(m.COVERAGE,'instrument',side_effect=RuntimeError('private filesystem/token material')):
            code,result,headers=self.request('/api/instrument?symbol=AAPL')
        self.assertEqual(code,400)
        self.assertEqual(result['error_code'],'resource_unavailable')
        self.assertEqual(result['request_id'],headers['X-Request-ID'])
        self.assertNotIn('private filesystem',json.dumps(result))

    def test_new_operation_stays_disabled_and_legacy_changes_advance_revision(self):
        code,before,_=self.request('/api/v2/operations/original-stop')
        self.assertEqual(code,200);self.assertFalse(before['enabled'])
        body={'command_id':'http_command_001','origin':before['origin'],'server_id':before['server_id'],
              'account':'original','settings_revision':before['settings_revision']}
        code,result,_=self.request('/api/v2/operations/original-stop',body)
        self.assertEqual(code,409);self.assertEqual(result['error_code'],'feature_disabled')
        self.request('/api/settings',{'kill_switch':True})
        after=self.request('/api/v2/operations/original-stop')[1]
        self.assertGreater(int(after['settings_revision']),int(before['settings_revision']))
        self.assertEqual(self.request('/api/v2/operations/original-stop?command_id=unknown_id')[0],404)
        self.assertEqual(self.request('/api/v2/operations/original-stop?extra=1')[0],400)
        self.assertEqual(self.request('/api/v2/operations/original-stop?extra=')[0],400)
        self.assertEqual(self.request('/api/v2/operations/original-stop?command_id=')[0],400)

    def test_direct_server_start_refuses_owner_marker_before_database_init(self):
        with tempfile.TemporaryDirectory(prefix='decklab-paused-main-') as folder:
            (Path(folder)/'owner-research-paused-until-asked').write_text('private fixture')
            env=dict(os.environ,MARKET_DECK_DATA=folder,MARKET_DECK_PORT='0')
            result=subprocess.run(['python3',str(m.ROOT/'server.py')],env=env,capture_output=True,text=True,timeout=10)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Owner pause active',result.stderr)
            self.assertFalse((Path(folder)/'market.db').exists())
            self.assertFalse((Path(folder)/'population.db').exists())


if __name__=='__main__':unittest.main(verbosity=2)
