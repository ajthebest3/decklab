"""Pinned Day Trader tools integrated as bounded research jobs; no execution authority."""
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / 'vendor/day-trader-skill'
TOOLS = {'analyze': 'Entry → exit → replay → sizing → risk → ticket → alerts',
         'scan': 'Daily chart scanner (up to 12 US tickers)', 'news': 'Headlines',
         'analyst': 'SEC earnings facts', 'pelosi': 'Congress disclosure index',
         'clock': 'NYSE session clock'}
NOTICE = ('US stocks, long side, New York sessions. Yahoo data is unofficial and may be delayed. '
          'Replay outcomes are simulations, not forecasts. Sizing/risk/tickets use the displayed planning budget, '
          'not a funded account. DeckLab execution, loss brakes and owner controls remain authoritative.')

class DayTrader:
    def __init__(self, data, db, rows, stop):
        self.root = Path(data) / 'day-trader'
        self.db, self.rows, self.stop = db, rows, stop
        self.lock = threading.Lock()

    def init(self, c):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        c.execute('''CREATE TABLE IF NOT EXISTS day_trader_jobs(
            id INTEGER PRIMARY KEY,request_id TEXT UNIQUE,created REAL,finished REAL,
            state TEXT,tool TEXT,symbols TEXT,request_json TEXT,result_json TEXT,error TEXT)''')
        c.execute("UPDATE day_trader_jobs SET state='interrupted',finished=?,error='Service restarted; submit a new request to run again' WHERE state='running'", (time.time(),))

    def validate(self, body):
        allowed = {'tool', 'symbols', 'request_id', 'budget', 'max_loss', 'sec_user_agent'}
        if not isinstance(body, dict) or set(body) - allowed:
            raise ValueError('Unsupported Day Trader parameters')
        tool = body.get('tool', 'analyze')
        if tool not in TOOLS: raise ValueError('Choose a supported Day Trader tool')
        symbols = body.get('symbols', [])
        if isinstance(symbols, str): symbols = symbols.upper().replace(',', ' ').split()
        if not isinstance(symbols, list) or len(symbols) > 12 or any(not isinstance(s,str) or not re.fullmatch(r'[A-Z]{1,6}(?:[.-][A-Z])?',s) for s in symbols):
            raise ValueError('Use up to 12 US stock tickers, e.g. AAPL, MSFT, TSLA; NSE, crypto and tokenized symbols use other market rules')
        symbols = list(dict.fromkeys(symbols))
        if tool not in ('clock', 'pelosi') and not symbols: raise ValueError('Enter a US ticker')
        if tool in ('analyze', 'analyst') and len(symbols) != 1: raise ValueError('This tool takes one US ticker')
        rid = body.get('request_id')
        if not isinstance(rid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}',rid): raise ValueError('A valid request ID is required')
        def number(key,default,lo,hi):
            v=body.get(key,default)
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not lo<=v<=hi:raise ValueError(f'{key} must be between {lo} and {hi}')
            return float(v)
        budget=number('budget',250,1,250); loss=number('max_loss',5,.01,25)
        if loss>budget:raise ValueError('Max loss cannot exceed the planning budget')
        ua=body.get('sec_user_agent','')
        if not isinstance(ua,str) or len(ua)>180 or any(ord(ch)<32 for ch in ua):raise ValueError('Invalid SEC contact')
        if ua and not re.fullmatch(r'.+ [^ @]+@[^ @]+\.[^ @]+',ua):raise ValueError('SEC contact needs your name and email')
        if tool=='analyst' and not ua:raise ValueError('SEC earnings needs your name and email as the SEC User-Agent')
        return dict(tool=tool,symbols=symbols,request_id=rid,budget=budget,max_loss=loss,sec_user_agent=ua)

    def status(self, params=None):
        params=params or {}
        with self.db() as c:
            if params.get('id'):
                try: jid=int(params['id'][0])
                except (TypeError,ValueError):raise ValueError('Invalid job ID')
                row=c.execute('SELECT * FROM day_trader_jobs WHERE id=?',(jid,)).fetchone()
                if not row:raise ValueError('Day Trader job not found')
                d=dict(row);d.pop('request_json');d['result']=json.loads(d.pop('result_json') or '{}');d['symbols']=json.loads(d['symbols'])
                return d
            jobs=self.rows(c,'SELECT id,created,finished,state,tool,symbols,error FROM day_trader_jobs ORDER BY id DESC LIMIT 30')
        for j in jobs:j['symbols']=json.loads(j['symbols'])
        provenance=json.loads((VENDOR/'UPSTREAM.json').read_text())
        return dict(tools=TOOLS,jobs=jobs,notice=NOTICE,repository=provenance['repository'],commit=provenance['commit'],planning_only=True)

    def submit(self, body):
        req=self.validate(body); encoded=json.dumps(req,sort_keys=True)
        with self.db() as c:
            old=c.execute('SELECT id,request_json FROM day_trader_jobs WHERE request_id=?',(req['request_id'],)).fetchone()
            if old:
                if old['request_json']!=encoded:raise ValueError('Request ID belongs to different parameters')
                return dict(id=old['id'],reused=True)
        if not self.lock.acquire(blocking=False):raise ValueError('A Day Trader job is already running')
        try:
            with self.db() as c:
                c.execute('BEGIN IMMEDIATE')
                last=c.execute('SELECT MAX(created) FROM day_trader_jobs').fetchone()[0]
                if last and time.time()-last<10:raise ValueError('Wait 10 seconds between Day Trader jobs')
                jid=c.execute("INSERT INTO day_trader_jobs(request_id,created,state,tool,symbols,request_json,result_json,error) VALUES(?,?,'running',?,?,?,'{}','')",(req['request_id'],time.time(),req['tool'],json.dumps(req['symbols']),encoded)).lastrowid
        except Exception:self.lock.release();raise
        threading.Thread(target=self.run,args=(jid,req),daemon=True).start()
        return dict(id=jid,reused=False)

    def command(self, work, folder, script, args):
        """Only internally composed argv; isolated files and environment, finite lifetime."""
        env={'PATH':os.defpath,'HOME':str(work),'LANG':'C.UTF-8','PYTHONIOENCODING':'utf-8'}
        started=time.time()
        with (work/'stdout.tmp').open('w+') as out, (work/'stderr.tmp').open('w+') as err:
            try:
                proc=subprocess.Popen([sys.executable,'-I',str(VENDOR/folder/script),*args],cwd=work,env=env,stdout=out,stderr=err)
                deadline=time.monotonic()+100
                while proc.poll() is None:
                    if self.stop.wait(.1) or time.monotonic()>deadline:
                        proc.kill();proc.wait()
                        return dict(state='interrupted' if self.stop.is_set() else 'timeout',started=started,finished=time.time(),error='Tool stopped before completion')
                out.seek(0);raw=out.read(400000);err.seek(0);error=err.read(2000)
            finally:
                if 'proc' in locals() and proc.poll() is None:proc.kill();proc.wait()
        try:value=json.loads(raw)
        except ValueError:value={'text':raw}
        valid_entry = isinstance(value,dict) and ((folder=='trader-entry' and value.get('status') in ('waiting','expired','no-data')) or (folder=='trader-budget' and 'sizing' in value) or (folder=='trader-risk' and 'block' in value))
        return dict(state='completed' if proc.returncode==0 or valid_entry else 'unavailable',exit_code=proc.returncode,started=started,finished=time.time(),data=value,error=error[:1000])

    def evaluate(self, req, work):
        trader=work/'trader';trader.mkdir(parents=True,exist_ok=True,mode=0o700)
        config=dict(budget=req['budget'],max_loss_per_trade_usd=req['max_loss'],max_order_usd=req['budget'],
            max_position_pct=100,cash_buffer_pct=0,min_order_usd=1,fractional=False,paper=True,
            allow_options=False,allow_margin=False,allow_short=False,require_stop=True,min_reward_risk=1)
        if req['sec_user_agent']:config['sec_user_agent']=req['sec_user_agent']
        (trader/'config.json').write_text(json.dumps(config))
        results={};tool=req['tool'];syms=req['symbols']
        def step(name,folder,script,args):
            if self.stop.is_set():return {'state':'interrupted'}
            result=self.command(work,folder,script,args);results[name]=result;return result
        if tool=='scan':step('scanner','trader-scanner','scan.py',['daily','--symbols',','.join(syms),'--json','--no-write'])
        elif tool=='news':step('news','trader-news','news.py',['--tickers',*syms,'--hours','24','--no-sec','--dry-run','--json'])
        elif tool=='analyst':step('analyst','trader-analyst','facts.py',[syms[0],'--json'])
        elif tool=='pelosi':step('disclosures','trader-pelosi','ptr.py',['index','--member','pelosi','--limit','20','--json'])
        elif tool=='clock':step('clock','trader-alerts','alerts.py',['clock','--json'])
        else:
            step('news','trader-news','news.py',['--tickers',syms[0],'--hours','24','--no-sec','--dry-run','--json'])
            entry=step('entry','trader-entry','entry.py',['check',syms[0],'--json','--write'])
            if entry.get('data',{}).get('status')=='triggered' and (trader/'entry.json').exists():
                plan=step('exit','trader-exit','exit.py',['plan','--stop','or-mid','--target','2R','--json','--write'])
                if plan.get('state')=='completed' and (trader/'plan.json').exists():
                    step('replay','trader-timemachine','timemachine.py',['run','--replays','10000','--seed','19','--json','--write'])
                    step('budget','trader-budget','size.py',['--json','--write'])
                    if (trader/'orders.json').exists():
                        step('risk','trader-risk','check.py',['--json'])
                        step('ticket','trader-broker','ticket.py',['show','--json'])
                    step('alerts','trader-alerts','alerts.py',['add','--from-plan'])
            else:results['planning']={'state':'skipped','reason':'No current confirmed opening-range entry; no exit plan, replay or ticket invented.'}
        return dict(steps=results,planning_budget_usd=req['budget'],max_planned_loss_usd=req['max_loss'],notice=NOTICE)

    def run(self,jid,req):
        result={};state='completed';error=''
        try:
            work=self.root/str(jid);work.mkdir(mode=0o700)
            result=self.evaluate(req,work)
            states=[s.get('state') for s in result['steps'].values()]
            if self.stop.is_set():state='interrupted'
            elif any(s in ('timeout','unavailable') for s in states):state='partial'
        except Exception:
            state='failed';error='Day Trader analysis could not finish; inspect tool availability and retry with a new request'
        finally:
            try:
                with self.db() as c:c.execute('UPDATE day_trader_jobs SET state=?,finished=?,result_json=?,error=? WHERE id=?',(state,time.time(),json.dumps(result),error,jid))
            finally:self.lock.release()

    def public_context(self, symbols):
        """Public evidence only; never share budgets, risk, tickets or account data with advisors."""
        now=time.time();result=[]
        with self.db() as c:
            jobs=self.rows(c,"SELECT id,created,symbols,result_json FROM day_trader_jobs WHERE state IN ('completed','partial') AND created BETWEEN ? AND ? ORDER BY id DESC LIMIT 20",(now-900,now))
        for job in jobs:
            matched=[s for s in json.loads(job['symbols']) if s in symbols]
            if not matched:continue
            steps=json.loads(job['result_json']).get('steps',{})
            def compact(value,depth=0):
                if depth>8:return 'Omitted nested detail; open the saved job'
                if isinstance(value,dict):return {k:compact(v,depth+1) for k,v in list(value.items())[:40] if k not in ('bands','sample_paths','hist','trades')}
                if isinstance(value,list):return [compact(v,depth+1) for v in value[:6]]
                if isinstance(value,str):return value[:800]
                return value
            public={k:compact(v) for k,v in steps.items() if k in ('scanner','news','entry','exit','replay')}
            if public:result.append(dict(job_id=job['id'],created=job['created'],symbols=matched,steps=public))
            if len(result)>=3:break
        # Cap public prompt size; replay output contains large simulated path arrays.
        return [dict(job_id=r['job_id'],created=r['created'],symbols=r['symbols'],evidence=r['steps'],note='US underlying research only. Not execution evidence; preserve each source timestamp and ignore stale data.') for r in result]
