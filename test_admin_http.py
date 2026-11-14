"""Admin HTTP authentication and origin restrictions with temporary private data."""
import json,os,tempfile,threading,unittest,urllib.request,urllib.error
TMP=tempfile.TemporaryDirectory(prefix='decklab-admin-http-');os.environ['MARKET_DECK_DATA']=TMP.name
import server as m
m.init();m.ADMIN.provision('11111111-1111-4111-8111-111111111111','isolated-http-admin-passkey')
http=m.ThreadingHTTPServer(('127.0.0.1',0),m.Handler);m.PORT=http.server_port;threading.Thread(target=http.serve_forever,daemon=True).start()
def request(path,body=None,headers=None):
 req=urllib.request.Request('http://127.0.0.1:'+str(m.PORT)+path,data=json.dumps(body).encode() if body is not None else None,headers=headers or {})
 try:
  with urllib.request.urlopen(req) as r:return r.status,json.load(r)
 except urllib.error.HTTPError as e:return e.code,json.load(e)
class HTTPTests(unittest.TestCase):
 def unlock(self):return request('/api/admin/unlock',{'passkey':'isolated-http-admin-passkey'})[1]['session']
 def test_info_reveals_no_thread_or_secret(self):
  _,info=request('/api/admin/info');self.assertEqual(set(info),{'configured','label'})
 def test_all_sensitive_routes_require_authentication(self):
  for route in ('status','command','cancel','resolve','lock','passkey'):
   self.assertEqual(request('/api/admin/'+route,{})[0],401,route)
 def test_wrong_origin_and_host_cannot_unlock(self):
  for headers in ({'Host':'evil.example'},{'Origin':'https://evil.example'}):
   self.assertEqual(request('/api/admin/unlock',{'passkey':'isolated-http-admin-passkey'},headers)[0],403)
 def test_unlock_queue_cancel_and_lock(self):
  token=self.unlock();_,queued=request('/api/admin/command',dict(session=token,command='Check status only',request_id='isolated-http-command'))
  self.assertEqual(queued['state'],'queued');self.assertEqual(request('/api/admin/cancel',dict(session=token,id=queued['id']))[0],200)
  self.assertEqual(request('/api/admin/lock',dict(session=token))[0],200);self.assertEqual(request('/api/admin/status',dict(session=token))[0],401)
 def test_arbitrary_thread_and_shell_routes_do_not_exist(self):
  for route in ('rpc','exec','thread','shell'):
   self.assertEqual(request('/api/admin/'+route,dict(session=self.unlock(),command='whoami'))[0],404)
 def test_private_files_and_get_status_are_not_served(self):
  for path in ('/data/admin.db','/data/admin-access.json','/admin_session.py','/api/admin/status'):
   self.assertEqual(request(path)[0],404)
if __name__=='__main__':
 try:unittest.main()
 finally:http.shutdown();http.server_close();m.STOP.set()
