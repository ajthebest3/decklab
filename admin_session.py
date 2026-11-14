"""Passkey-gated commands to one existing local Codex session.

No new agent/thread is created, no shell endpoint, and no model output is executed.
Only the configured thread and an explicit RPC method allowlist can be reached.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import sqlite3
import struct
import tempfile
import threading
import time
from pathlib import Path

class AdminAuthError(ValueError):pass


def safe_text(value):
    value=re.sub(r'\bsk-[A-Za-z0-9_-]{8,}', '[redacted API key]',str(value))
    return re.sub(r'\bDeckLab-[A-Za-z0-9_-]{16,}', '[redacted admin passkey]',value)


class CodexSession:
    METHODS={'thread/read','thread/turns/list','thread/resume','turn/start','turn/steer','turn/interrupt'}
    def __init__(self,thread_id,socket_path=None):
        self.thread_id=thread_id
        self.path=Path(socket_path or Path.home()/'.codex/app-server-control/app-server-control.sock')

    def rpc(self,method,params=None):
        if method not in self.METHODS:raise ValueError('Unsupported session operation')
        params={**(params or {}),'threadId':self.thread_id}
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as conn:
            conn.settimeout(8);conn.connect(str(self.path))
            key=base64.b64encode(os.urandom(16)).decode()
            conn.sendall(('GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: '+key+'\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
            header=b''
            while not header.endswith(b'\r\n\r\n'):
                part=conn.recv(1)
                if not part:raise ConnectionError('Session connection closed')
                header+=part
                if len(header)>16384:raise ConnectionError('Invalid session handshake')
            accept=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            fields=dict(line.split(':',1) for line in header.decode().split('\r\n')[1:] if ':' in line)
            accepted=next((value.strip() for name,value in fields.items() if name.lower()=='sec-websocket-accept'),'')
            if not header.startswith(b'HTTP/1.1 101 ') or accepted!=accept:raise ConnectionError('Session handshake failed')
            self.send(conn,dict(id=1,method='initialize',params=dict(clientInfo=dict(name='decklab_admin',version='1.0.0'),capabilities=dict(experimentalApi=True))))
            self.response(conn,1)
            self.send(conn,dict(method='initialized',params={}))
            self.send(conn,dict(id=2,method=method,params=params))
            return self.response(conn,2)

    @staticmethod
    def send(conn,value,opcode=1):
        data=json.dumps(value,separators=(',',':')).encode() if opcode==1 else value
        mask=os.urandom(4);length=len(data)
        header=bytes([128|opcode,128|length]) if length<126 else bytes([128|opcode,254])+struct.pack('!H',length) if length<65536 else bytes([128|opcode,255])+struct.pack('!Q',length)
        conn.sendall(header+mask+bytes(v^mask[i%4] for i,v in enumerate(data)))

    @staticmethod
    def exact(conn,length):
        out=bytearray()
        while len(out)<length:
            part=conn.recv(length-len(out))
            if not part:raise ConnectionError('Session disconnected')
            out.extend(part)
        return bytes(out)

    def response(self,conn,rid):
        fragments=bytearray();deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            first,second=self.exact(conn,2);opcode=first&15;length=second&127
            if length==126:length=struct.unpack('!H',self.exact(conn,2))[0]
            elif length==127:length=struct.unpack('!Q',self.exact(conn,8))[0]
            if length>8_000_000:raise ConnectionError('Session response exceeds limit')
            mask=self.exact(conn,4) if second&128 else None;data=self.exact(conn,length)
            if mask:data=bytes(v^mask[i%4] for i,v in enumerate(data))
            if opcode==8:raise ConnectionError('Session closed')
            if opcode==9:self.send(conn,data,10);continue
            if opcode==10:continue
            if opcode not in (0,1):raise ConnectionError('Unsupported session frame')
            fragments.extend(data)
            if len(fragments)>8_000_000:raise ConnectionError('Session message exceeds limit')
            if not first&128:continue
            message=json.loads(fragments);fragments.clear()
            # Ignore notifications and tool requests; this client grants no approvals.
            if message.get('id')!=rid:continue
            if 'error' in message:raise ValueError('Codex session request failed ('+str(message['error'].get('code','unknown'))+')')
            return message.get('result',{})
        raise TimeoutError('Session response timed out')


class Connection(sqlite3.Connection):
    def __exit__(self,*args):
        try:return super().__exit__(*args)
        finally:self.close()


class AdminSession:
    def __init__(self,data,stop,client_factory=CodexSession):
        self.data=Path(data);self.path=self.data/'admin-access.json';self.db_path=self.data/'admin.db'
        self.stop=stop;self.client_factory=client_factory;self.auth_lock=threading.RLock();self.worker_lock=threading.Lock();self.failures=[]
        self.cache_lock=threading.Lock();self.snapshot=None;self.last_read=0;self.connection_error='';self.cycle_lock=threading.Lock()

    def db(self):
        c=sqlite3.connect(self.db_path,timeout=10,factory=Connection);c.row_factory=sqlite3.Row;return c

    def init(self):
        self.data.mkdir(mode=0o700,parents=True,exist_ok=True)
        with self.db() as c:
            c.executescript('''PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS admin_sessions(token_hash TEXT PRIMARY KEY,created REAL,expires REAL);
            CREATE TABLE IF NOT EXISTS admin_commands(id INTEGER PRIMARY KEY,request_id TEXT UNIQUE,created REAL,updated REAL,body TEXT,state TEXT,turn_id TEXT,error TEXT);
            CREATE TABLE IF NOT EXISTS admin_audit(id INTEGER PRIMARY KEY,ts REAL,action TEXT,command_id INTEGER);
            ''')
            columns={r[1] for r in c.execute('PRAGMA table_info(admin_commands)')}
            if 'mode' not in columns:c.execute("ALTER TABLE admin_commands ADD COLUMN mode TEXT NOT NULL DEFAULT 'queue'")
            c.execute("UPDATE admin_commands SET state='uncertain',updated=?,error='Service restarted during delivery. Inspect session before resending.' WHERE state='sending'",(time.time(),))
        self.db_path.chmod(0o600)

    def config(self):
        try:return json.loads(self.path.read_text())
        except (OSError,ValueError):return {}

    def provision(self,thread_id,passkey):
        if not re.fullmatch(r'[a-f0-9-]{36}',thread_id):raise ValueError('Invalid Codex session ID')
        if not isinstance(passkey,str) or not 12<=len(passkey)<=200:raise ValueError('Use a passkey with 12–200 characters')
        with self.auth_lock:
            self.failures=[]
            salt=secrets.token_hex(16)
            digest=hashlib.scrypt(passkey.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
            fd,name=tempfile.mkstemp(prefix='.admin-access-',dir=self.data)
            with os.fdopen(fd,'w') as out:json.dump(dict(thread_id=thread_id,label='DeckLab',salt=salt,passkey_hash=digest),out)
            os.replace(name,self.path)
            with self.db() as c:c.execute('DELETE FROM admin_sessions');c.execute('INSERT INTO admin_audit(ts,action) VALUES(?,?)',(time.time(),'passkey_configured'))
        return {'ok':True}

    def unlock(self,passkey):
        with self.auth_lock:
            now=time.time();self.failures=[t for t in self.failures if now-t<300]
            if len(self.failures)>=5:raise AdminAuthError('Too many unlock attempts. Try again in five minutes.')
            cfg=self.config()
            if not cfg:raise AdminAuthError('Admin access has not been configured on this server')
            if not isinstance(passkey,str) or len(passkey)>200:raise AdminAuthError('Incorrect admin passkey')
            digest=hashlib.scrypt(passkey.encode(),salt=bytes.fromhex(cfg['salt']),n=16384,r=8,p=1).hex()
            if not hmac.compare_digest(digest,cfg['passkey_hash']):
                self.failures.append(now)
                with self.db() as c:c.execute('INSERT INTO admin_audit(ts,action) VALUES(?,?)',(now,'unlock_failed'))
                raise AdminAuthError('Incorrect admin passkey')
            self.failures=[];token=secrets.token_urlsafe(32)
            with self.db() as c:
                c.execute('DELETE FROM admin_sessions WHERE expires<? OR created<?',(now,now-28800))
                c.execute('INSERT INTO admin_sessions VALUES(?,?,?)',(self.token_hash(token),now,now+3600))
                c.execute('INSERT INTO admin_audit(ts,action) VALUES(?,?)',(now,'unlocked'))
            return dict(session=token,expires=now+3600,label=cfg['label'])

    @staticmethod
    def token_hash(token):return hashlib.sha256(token.encode()).hexdigest()

    def authorize(self,token):
        if not isinstance(token,str) or not 20<=len(token)<=100:raise AdminAuthError('Unlock DeckLab Admin first')
        now=time.time()
        with self.db() as c:
            row=c.execute('SELECT * FROM admin_sessions WHERE token_hash=?',(self.token_hash(token),)).fetchone()
            if not row or now>row['expires'] or now-row['created']>28800:raise AdminAuthError('Admin session expired. Unlock again.')
            expires=min(now+3600,row['created']+28800)
            c.execute('UPDATE admin_sessions SET expires=? WHERE token_hash=?',(expires,self.token_hash(token)))
        return expires

    def logout(self,token):
        self.authorize(token)
        with self.db() as c:
            c.execute('DELETE FROM admin_sessions WHERE token_hash=?',(self.token_hash(token),))
            c.execute('INSERT INTO admin_audit(ts,action) VALUES(?,?)',(time.time(),'locked'))
        return {'ok':True}

    def submit(self,body):
        self.authorize(body.get('session'));text=body.get('command');rid=body.get('request_id');mode=body.get('mode','queue')
        if mode not in ('queue','reply'):raise ValueError('Choose queue or reply delivery')
        if not isinstance(text,str) or not 1<=len(text.strip())<=8000:raise ValueError('Write a command between 1 and 8,000 characters')
        text=text.strip()
        if not isinstance(rid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}',rid):raise ValueError('A valid command request ID is required')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM admin_commands WHERE request_id=?',(rid,)).fetchone()
            if old:
                if old['body']!=text or old['mode']!=mode:raise ValueError('This request ID belongs to a different command')
                return dict(id=old['id'],state=old['state'],reused=True)
            if c.execute("SELECT COUNT(*) FROM admin_commands WHERE state IN ('queued','sending','sent')").fetchone()[0]>=20:raise ValueError('Command queue is full. Wait or cancel a queued command.')
            now=time.time();cid=c.execute("INSERT INTO admin_commands(request_id,created,updated,body,state,mode) VALUES(?,?,?,?,'queued',?)",(rid,now,now,text,mode)).lastrowid
            c.execute('INSERT INTO admin_audit(ts,action,command_id) VALUES(?,?,?)',(now,'command_queued',cid))
        return dict(id=cid,state='queued',reused=False)

    def cancel(self,body):
        self.authorize(body.get('session'));cid=body.get('id')
        if type(cid) is not int:raise ValueError('Invalid command ID')
        with self.db() as c:
            changed=c.execute("UPDATE admin_commands SET state='cancelled',updated=? WHERE id=? AND state='queued'",(time.time(),cid)).rowcount
            if not changed:raise ValueError('Only queued commands can be cancelled')
            c.execute('INSERT INTO admin_audit(ts,action,command_id) VALUES(?,?,?)',(time.time(),'command_cancelled',cid))
        return {'ok':True}

    def resolve(self,body):
        self.authorize(body.get('session'));cid=body.get('id');action=body.get('action')
        if type(cid) is not int or action not in ('retry','dismiss'):raise ValueError('Choose retry or dismiss for an unconfirmed command')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute("SELECT 1 FROM admin_commands WHERE id=? AND state='uncertain'",(cid,)).fetchone():raise ValueError('This command does not need delivery review')
            c.execute('UPDATE admin_commands SET state=?,error=NULL,updated=? WHERE id=?',('queued' if action=='retry' else 'dismissed',time.time(),cid))
            c.execute('INSERT INTO admin_audit(ts,action,command_id) VALUES(?,?,?)',(time.time(),'owner_'+action,cid))
        return {'ok':True}

    def client(self):
        cfg=self.config()
        if not cfg:raise ValueError('Admin session is not configured')
        return self.client_factory(cfg['thread_id'])

    @staticmethod
    def messages(turns):
        messages=[]
        for turn in reversed(turns):
            for item in turn.get('items',[]):
                kind=item.get('type')
                if kind not in ('userMessage','agentMessage'):continue
                if kind=='userMessage':text='\n'.join(x.get('text','') for x in item.get('content',[]) if x.get('type')=='text')
                else:text=item.get('text','')
                if text:messages.append(dict(id=item.get('id'),turn_id=turn['id'],role='user' if kind=='userMessage' else 'assistant',text=safe_text(text)[-12000:],status=turn.get('status'),phase=item.get('phase')))
        return messages[-40:]

    def refresh(self):
        client=self.client();thread=client.rpc('thread/read')['thread']
        turns=client.rpc('thread/turns/list',dict(limit=8,sortDirection='desc',itemsView='full')).get('data',[])
        value=dict(label='DeckLab',thread_id=thread['id'],status=thread.get('status',{}).get('type','unknown'),messages=self.messages(turns),active_turn=next((t['id'] for t in turns if t.get('status')=='inProgress'),None),updated=time.time())
        with self.cache_lock:self.snapshot=value;self.last_read=time.time();self.connection_error=''
        with self.db() as c:
            for turn in turns:
                state=turn.get('status')
                if state in ('completed','failed','interrupted'):
                    c.execute("UPDATE admin_commands SET state=?,updated=? WHERE turn_id=? AND state='sent'",('completed' if state=='completed' else state,time.time(),turn['id']))
                # Reconcile a lost acknowledgement without ever resending it.
                inputs='\n'.join(x.get('text','') for i in turn.get('items',[]) if i.get('type')=='userMessage' for x in i.get('content',[]) if x.get('type')=='text')
                for command in c.execute("SELECT id,request_id FROM admin_commands WHERE state IN ('uncertain','queued')").fetchall():
                    if '[DeckLab Admin '+command['request_id']+']' in inputs:
                        c.execute('UPDATE admin_commands SET state=?,turn_id=?,error=NULL,updated=? WHERE id=?',('completed' if state=='completed' else 'sent',turn['id'],time.time(),command['id']))
        return value

    def status(self,token):
        expires=self.authorize(token)
        with self.cache_lock:value=dict(self.snapshot) if self.snapshot else None;error=self.connection_error
        with self.db() as c:commands=[dict(r) for r in c.execute('SELECT id,created,updated,body,state,turn_id,error,mode FROM admin_commands ORDER BY id DESC LIMIT 30')]
        for command in commands:command['body']=safe_text(command['body'])
        return dict(session=value,commands=commands,error=error,connected=bool(value and time.time()-value['updated']<15),expires=expires)

    def cycle(self):
        if not self.cycle_lock.acquire(blocking=False):return
        try:
            if not self.config():return
            with self.db() as c:
                interested=c.execute("SELECT 1 FROM admin_sessions WHERE expires>? LIMIT 1",(time.time(),)).fetchone() or c.execute("SELECT 1 FROM admin_commands WHERE state IN ('queued','sending','sent','uncertain') LIMIT 1").fetchone()
            if not interested:return
            value=self.refresh()
            active=value['status']=='active' and value.get('active_turn')
            if value['status'] not in ('idle','notLoaded') and not active:return
            with self.db() as c:
                c.execute('BEGIN IMMEDIATE')
                if active:
                    if c.execute("SELECT 1 FROM admin_commands WHERE state IN ('sending','uncertain')").fetchone():return
                    command=c.execute("SELECT * FROM admin_commands WHERE state='queued' AND mode='reply' ORDER BY id LIMIT 1").fetchone()
                else:
                    if c.execute("SELECT 1 FROM admin_commands WHERE state IN ('sending','sent','uncertain')").fetchone():return
                    command=c.execute("SELECT * FROM admin_commands WHERE state='queued' ORDER BY id LIMIT 1").fetchone()
                if not command:return
                c.execute("UPDATE admin_commands SET state='sending',updated=? WHERE id=?",(time.time(),command['id']))
            try:
                client=self.client()
                if value['status']=='notLoaded':client.rpc('thread/resume',dict(excludeTurns=True))
                prompt='[DeckLab Admin '+command['request_id']+']\nThis command was submitted by the owner through the passkey-authenticated DeckLab Admin channel. Continue the existing DeckLab session using the project AGENTS.md instructions and project instructions.\n\n'+command['body']
                if active:
                    result=client.rpc('turn/steer',dict(input=[dict(type='text',text=prompt)],expectedTurnId=value['active_turn']));turn_id=result['turnId']
                else:
                    result=client.rpc('turn/start',dict(input=[dict(type='text',text=prompt)]));turn_id=result['turn']['id']
                with self.db() as c:
                    c.execute("UPDATE admin_commands SET state='sent',turn_id=?,updated=?,error=NULL WHERE id=?",(turn_id,time.time(),command['id']))
                    c.execute('INSERT INTO admin_audit(ts,action,command_id) VALUES(?,?,?)',(time.time(),'command_sent',command['id']))
            except Exception:
                with self.db() as c:c.execute("UPDATE admin_commands SET state='uncertain',updated=?,error='Delivery could not be confirmed. Check session replies before resending.' WHERE id=?",(time.time(),command['id']))
        except Exception:
            with self.cache_lock:self.connection_error='Codex session is unavailable. Commands remain saved; reconnect the local Codex app server.'
        finally:self.cycle_lock.release()

    def loop(self):
        while not self.stop.is_set():self.cycle();self.stop.wait(2)
