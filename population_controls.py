"""Owner controls and conserved reserve funding for the managed portfolio."""
import json
import math
import time
import uuid

# API values are in dollars, seconds and fractions. The UI uses display_scale
# only for percentages; nullable values are rendered as 0 = no owner cap.
FIELDS = [
 ('portfolio_capital_usd','Portfolio capital · USD',1000,1e9,1000000.,'Capital',False,1),
 ('codex_bots','Group A bots',0,200,4,'Launch plan',False,1),
 ('agy_bots','Group B bots',0,200,4,'Launch plan',False,1),
 ('bot_allocation_usd','Capital for each new bot · USD',10,1e7,5000.,'Launch plan',False,1),
 ('max_positions','Positions per bot · 0 = no cap',1,10000,None,'Trading limits',True,1),
 ('max_entry_usd','Entry budget · USD · 0 = no cap',1,1e8,None,'Trading limits',True,1),
 ('max_allocation_pct','Maximum model allocation · %',0,100,100.,'Trading limits',False,1),
 ('daily_entry_limit','Daily entries per bot · IST · 0 = no cap',1,1000000,None,'Trading limits',True,1),
 ('max_orders_per_second','Order / fill ceiling per second',1,1000,1000,'Trading limits',False,1),
 ('policy_batch_size','Maximum batch per bot',1,1000,1000,'Trading limits',False,1),
 ('policy_cooldown_seconds','Re-entry cooldown · seconds',0,86400,0,'Trading limits',False,1),
 ('exploration_cap','Maximum random exploration · %',0,.25,.25,'Trading limits',False,100),
 ('loss_streak_limit','Consecutive losing closes before entry brake',1,100,3,'Trading limits',False,1),
 ('advisor_interval','Strategy update interval · seconds',120,3600,180,'Timing and exits',False,1),
 ('reviewer_interval','Reviewer interval · seconds',120,3600,120,'Timing and exits',False,1),
 ('max_hold_seconds','Maximum position hold · seconds',120,86400,7200,'Timing and exits',False,1),
 ('stop_pct','Downside exit threshold · %',.1,100,20.,'Timing and exits',False,1),
 ('take_pct','Upside exit threshold · %',.1,1000,50.,'Timing and exits',False,1),
 ('min_delay_seconds','Minimum execution delay · seconds',3,60,3.,'Execution assumptions',False,1),
 ('order_timeout_seconds','Pending order timeout · seconds',30,86400,300,'Execution assumptions',False,1),
 ('fee_rate','Modeled fee per future fill · %',0,.05,.001,'Execution assumptions',False,100),
 ('participation','Observed depth participation · %',.001,.25,.05,'Execution assumptions',False,100),
 ('share_min_score','Lesson minimum reviewer score',0,100,60,'Reviewer and replacement',False,1),
 ('clone_min_gain_usd','Copy / share minimum net gain · USD',0,1e7,250.,'Reviewer and replacement',False,1),
 ('clone_min_wins','Copy / share minimum wins',1,10000,3,'Reviewer and replacement',False,1),
 ('clone_min_episodes','Copy / share minimum closed episodes',1,10000,5,'Reviewer and replacement',False,1),
]
BOOLEANS = [
 ('entries_enabled','Allow new entries',True,'Trading limits'),
 ('policy_enabled','Run strategy signals',True,'Trading limits'),
 ('learning_mode','Continue exploration through negative points',True,'Trading limits'),
 ('allow_additions','Allow model-selected additions to holdings',True,'Trading limits'),
 ('respect_loss_brakes','Block entries after repeated or same-context losses',False,'Trading limits'),
 ('cost_guard','Require observed coverage and movement above fees',False,'Trading limits'),
 ('point_scaled_allocation','Reduce model allocation using context points',False,'Trading limits'),
 ('pin_exit_rules','Keep new positions on their recorded entry exit rules',False,'Timing and exits'),
 ('auto_replace','Reviewer may replace depleted bots from reserve',True,'Reviewer and replacement'),
 ('clone_enabled','Reviewer may copy eligible strategies',True,'Reviewer and replacement'),
 ('share_lessons_enabled','Share passed strategy lessons across all models',True,'Reviewer and replacement'),
]
INTEGER = {'share_min_score','codex_bots','agy_bots','max_positions','daily_entry_limit','max_orders_per_second','policy_batch_size','policy_cooldown_seconds','advisor_interval','reviewer_interval','max_hold_seconds','order_timeout_seconds','clone_min_wins','clone_min_episodes'}
STOPPED_ONLY = {'portfolio_capital_usd','codex_bots','agy_bots','bot_allocation_usd'}
INTEGER.add('loss_streak_limit')
STRATEGY_CONTROLS = {'exploration_cap','respect_loss_brakes','cost_guard','point_scaled_allocation','pin_exit_rules','max_allocation_pct','allow_additions','loss_streak_limit'}


def schema():
    return [dict(key=k,label=label,min=lo,max=hi,default=default,section=section,nullable=nullable,display_scale=scale,type='integer' if k in INTEGER else 'number',stopped_only=k in STOPPED_ONLY) for k,label,lo,hi,default,section,nullable,scale in FIELDS] + [dict(key=k,label=label,default=default,section=section,type='boolean',stopped_only=False) for k,label,default,section in BOOLEANS]


def number(value,lo,hi):
    if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:
        raise ValueError('Expected a finite value between '+str(lo)+' and '+str(hi))
    return value


class PortfolioControls:
    def __init__(self,engine):
        self.e=engine

    def init(self,c):
        c.executescript('''
        CREATE TABLE IF NOT EXISTS population_treasury(id INTEGER PRIMARY KEY CHECK(id=1),initial REAL,cash REAL,created REAL);
        CREATE TABLE IF NOT EXISTS population_treasury_ledger(id INTEGER PRIMARY KEY,ts REAL,kind TEXT,amount REAL,ref TEXT UNIQUE,bot TEXT);
        CREATE TABLE IF NOT EXISTS population_capital_changes(id INTEGER PRIMARY KEY,ts REAL,bot TEXT,amount REAL,reason TEXT,ref TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS population_control_history(id INTEGER PRIMARY KEY,ts REAL,body TEXT);
        CREATE TABLE IF NOT EXISTS population_portfolio_equity(ts INTEGER PRIMARY KEY,usd REAL,inr REAL,fx_asof REAL);
        ''')
        for field in schema():
            c.execute('INSERT OR IGNORE INTO demo_settings VALUES(?,?)',(field['key'],json.dumps(field['default'])))
        c.execute("INSERT OR IGNORE INTO population_config VALUES('execution_epoch','0')")
        if not c.execute('SELECT 1 FROM population_treasury').fetchone():
            allocated=c.execute('SELECT COALESCE(SUM(initial),0) FROM demo_wallets').fetchone()[0]
            capital=max(1000000.,allocated)
            c.execute('INSERT INTO population_treasury VALUES(1,?,?,?)',(capital,capital-allocated,time.time()))
            c.execute("INSERT INTO population_treasury_ledger(ts,kind,amount,ref) VALUES(?,'Opening portfolio capital',?,'portfolio-opening')",(time.time(),capital))
            if allocated:
                c.execute("INSERT INTO population_treasury_ledger(ts,kind,amount,ref) VALUES(?,'Recognize existing bot allocations',?,'portfolio-existing-bots')",(time.time(),-allocated))
            c.execute('UPDATE demo_settings SET value=? WHERE key=\'portfolio_capital_usd\'',(json.dumps(capital),))

    def epoch(self,c):
        return int(c.execute("SELECT value FROM population_config WHERE key='execution_epoch'").fetchone()[0])

    def advance(self,c):
        value=self.epoch(c)+1
        c.execute("UPDATE population_config SET value=? WHERE key='execution_epoch'",(str(value),))
        return value

    def reserve(self,c,amount,kind,ref,bot=None):
        treasury=c.execute('SELECT * FROM population_treasury').fetchone()
        if treasury['cash']+amount < -1e-7:
            raise ValueError('Insufficient unallocated reserve for this launch or capital change')
        c.execute('UPDATE population_treasury SET cash=cash+? WHERE id=1',(amount,))
        c.execute('INSERT INTO population_treasury_ledger(ts,kind,amount,ref,bot) VALUES(?,?,?,?,?)',(time.time(),kind,amount,ref,bot))

    def allocate_bot(self,c,bot,target):
        wallet=c.execute('SELECT * FROM demo_wallets WHERE bot=?',(bot,)).fetchone()
        if not wallet:
            raise ValueError('Unknown bot allocation target')
        delta=target-wallet['initial']
        if abs(delta)<1e-8:
            return
        if wallet['cash']+delta < -1e-7:
            raise ValueError(bot+': invested funds cannot be withdrawn without an actual exit')
        ref='owner-allocation-'+uuid.uuid4().hex
        self.reserve(c,-delta,'Owner bot allocation transfer',ref,bot)
        c.execute('UPDATE demo_wallets SET cash=cash+?,initial=initial+? WHERE bot=?',(delta,delta,bot))
        c.execute("INSERT INTO demo_cash_ledger(bot,ts,kind,amount,ref) VALUES(?,?,'Owner reserve transfer',?,?)",(bot,time.time(),delta,ref))
        c.execute('INSERT INTO population_capital_changes(ts,bot,amount,reason,ref) VALUES(?,?,?,?,?)',(time.time(),bot,delta,'Owner allocation target; prior P&L preserved',ref))

    def configure(self,body):
        if not isinstance(body,dict):
            raise ValueError('Expected portfolio controls object')
        fields={f['key']:f for f in schema()};values={};allocations=body.get('bot_allocations',{})
        for key,value in body.items():
            if key=='bot_allocations':
                continue
            if key=='enabled':
                if type(value) is not bool:raise ValueError('Expected enabled boolean')
            elif key not in fields:
                raise ValueError('Unknown portfolio control: '+key)
            else:
                f=fields[key]
                if f['type']=='boolean':
                    if type(value) is not bool:raise ValueError('Expected boolean for '+key)
                elif value is None and f.get('nullable'):
                    pass
                else:
                    number(value,f['min'],f['max'])
                    if f['type']=='integer' and int(value)!=value:raise ValueError('Expected whole number for '+key)
            values[key]=value
        if not isinstance(allocations,dict) or len(allocations)>200:
            raise ValueError('Invalid bot allocation targets')
        for value in allocations.values():number(value,0,1e9)
        with self.e.db() as c:
            c.execute('BEGIN IMMEDIATE');old=self.e.settings(c);merged={**old,**values}
            if old['enabled'] and (any(k in STOPPED_ONLY and values[k]!=old[k] for k in values) or allocations):
                raise ValueError('Stop bots before changing launch counts or capital allocations')
            if merged['codex_bots']+merged['agy_bots']>200:
                raise ValueError('Maximum 200 launched bots across both providers')
            if merged['order_timeout_seconds']<=merged['min_delay_seconds']:
                raise ValueError('Order timeout must exceed the execution delay')
            if values.get('enabled') is True:
                raise ValueError('Use Start bots to apply the launch plan')
            if 'portfolio_capital_usd' in values:
                treasury=c.execute('SELECT * FROM population_treasury').fetchone();delta=values['portfolio_capital_usd']-treasury['initial']
                if abs(delta)>1e-8:
                    self.reserve(c,delta,'Owner portfolio capital change','portfolio-capital-'+uuid.uuid4().hex)
                    c.execute('UPDATE population_treasury SET initial=? WHERE id=1',(values['portfolio_capital_usd'],))
            for bot,target in allocations.items():self.allocate_bot(c,bot,target)
            if 'fee_rate' in values and values['fee_rate']!=old['fee_rate']:
                from fee_restatement import LABEL,SOURCE
                for key,value in dict(fee_model=LABEL if values['fee_rate']==.001 else 'Custom fee assumption',fee_source=SOURCE).items():c.execute('INSERT OR REPLACE INTO demo_settings VALUES(?,?)',(key,json.dumps(value)))
            for key,value in values.items():c.execute('UPDATE demo_settings SET value=? WHERE key=?',(json.dumps(value),key))
            strategy_changed=any(key in STRATEGY_CONTROLS and value!=old[key] for key,value in values.items())
            if strategy_changed:
                self.advance(c)
                c.execute("INSERT OR REPLACE INTO population_config VALUES('strategy_controls_since',?)",(str(time.time()),))
                c.execute("UPDATE demo_orders SET state='cancelled',finished=?,reason=reason||' · strategy controls changed' WHERE side='buy' AND state IN ('queued','partial','awaiting_data')",(time.time(),))
            if values.get('enabled') is False:
                self.advance(c)
                c.execute("UPDATE demo_orders SET state='cancelled',finished=?,reason=reason||' · stopped by owner' WHERE state IN ('queued','partial','awaiting_data')",(time.time(),))
            elif values.get('entries_enabled') is False:
                c.execute("UPDATE demo_orders SET state='cancelled',finished=? WHERE side='buy' AND state IN ('queued','partial','awaiting_data')",(time.time(),))
            c.execute('INSERT INTO population_control_history(ts,body) VALUES(?,?)',(time.time(),json.dumps(body)))
            self.e.log(c,'system','controls','Owner portfolio controls updated',body)
        if values.get('enabled') is False or strategy_changed:self.e.cancel_jobs()
        return {'ok':True}

    def start(self):
        with self.e.db() as c:
            c.execute('BEGIN IMMEDIATE');cfg=self.e.settings(c)
            roster=json.loads(c.execute("SELECT value FROM population_config WHERE key='model_roster_enabled'").fetchone()[0])
            if cfg['enabled']:return {'ok':True,'already_running':True}
            if roster:return self.e.model_roster.start(c,cfg)
            if cfg['codex_bots']+cfg['agy_bots']<1:
                raise ValueError('Choose at least one bot before starting')
            if cfg['enabled']:
                return {'ok':True,'already_running':True}
            plans={};needed=0
            for provider,key in [('Codex','codex_bots'),('AGY','agy_bots')]:
                existing=self.e.rows(c,"SELECT * FROM population_bots WHERE provider=? AND state IN ('active','parked') ORDER BY state='active' DESC,slot",(provider,))
                selected=existing[:cfg[key]];new_count=cfg[key]-len(selected);needed+=new_count*cfg['bot_allocation_usd'];plans[provider]=(selected,new_count)
            reserve=c.execute('SELECT cash FROM population_treasury').fetchone()[0]
            if needed>reserve+1e-7:raise ValueError('Launch plan needs more unallocated reserve; lower bot count/allocation or change capital')
            c.execute("UPDATE population_bots SET state='parked' WHERE state='active'")
            for provider,(selected,new_count) in plans.items():
                for agent in selected:c.execute("UPDATE population_bots SET state='active' WHERE bot=?",(agent['bot'],))
                for _ in range(new_count):
                    slot=c.execute('SELECT COALESCE(MAX(slot),0)+1 FROM population_bots').fetchone()[0]
                    self.e._spawn(c,slot,provider)
            self.advance(c)
            c.execute("UPDATE demo_settings SET value='true' WHERE key='enabled'")
            self.e.log(c,'system','portfolio_started','Owner started the configured bot launch plan',{'codex':cfg['codex_bots'],'agy':cfg['agy_bots'],'new_allocation_usd':needed})
        return {'ok':True,'slots':cfg['codex_bots']+cfg['agy_bots'],'allocation_per_bot':cfg['bot_allocation_usd']}
