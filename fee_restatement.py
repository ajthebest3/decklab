"""Owner-authorized fee-scenario restatement of fixed historical executions.

No prices, quantities, timestamps, depth evidence, funding or agent decisions are
invented or replayed. Original amounts remain in the audit and private backups.
"""
import argparse
import json
import math
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

RATE=.001
SOURCE='https://www.binance.com/en/fee/trading'
LABEL='Binance standard spot fee scenario'


def rows(c,sql,args=()):return [dict(r) for r in c.execute(sql,args)]
def exists(c,table):return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone())
def points(net):return 1 if net>1e-6 else -5 if net< -1e-6 else 0
def close(a,b,label,tol=1e-6):
    if not math.isclose(a,b,rel_tol=1e-9,abs_tol=tol):raise ValueError(label+' does not reconcile: '+str(a)+' versus '+str(b))


def init(c):
    c.execute('CREATE TABLE IF NOT EXISTS demo_fee_restatements(id INTEGER PRIMARY KEY,request_id TEXT UNIQUE,created REAL,rate REAL,label TEXT,source TEXT,summary TEXT,chart_from INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS demo_fee_audit(batch INTEGER,table_name TEXT,row_key TEXT,before_json TEXT,after_json TEXT,PRIMARY KEY(batch,table_name,row_key))')


def replay(c,rate=None):
    fills=rows(c,'SELECT * FROM demo_fills ORDER BY id');orders={r['id']:r for r in rows(c,'SELECT * FROM demo_orders')}
    rewards={r['episode']:r for r in rows(c,'SELECT * FROM demo_rewards')}
    final_fill={}
    for fill in fills:final_fill[fill['order_id']]=fill['id']
    closers={final_fill[r['exit_order']]:r for r in rewards.values() if r['exit_order'] is not None}
    dust=rows(c,'SELECT * FROM population_dust') if exists(c,'population_dust') else []
    events=[(f['ts'],0,f['id'],f) for f in fills]+[(d['ts'],1,d['episode'],d) for d in dust]
    positions={};result=dict(fills={},rewards={},dust={},positions=positions)
    for _,kind,_,record in sorted(events,key=lambda event:event[:3]):
        key=(record['bot'],record['symbol']);position=positions.get(key)
        if kind==1:
            if not position or position['episode']!=record['episode']:raise ValueError('Dust episode cannot be reconciled')
            net=position['realized_parts']-position['cost'];result['dust'][record['episode']]=position['cost']
            result['rewards'][record['episode']]=dict(net_usd=net,points=points(net));del positions[key];continue
        fill=record;fee=fill['fee'] if rate is None else fill['usd_total']*rate;realized=0.
        if fill['side']=='buy':
            if not position:
                position=positions[key]=dict(qty=0.,cost=0.,realized_parts=0.,episode=fill['order_id'])
            position['qty']+=fill['qty'];position['cost']+=fill['usd_total']+fee
        else:
            if not position or fill['qty']>position['qty']+1e-9:raise ValueError('Sell quantity cannot be reconciled')
            allocated=position['cost']*min(1,fill['qty']/position['qty'])
            realized=fill['usd_total']-fee-allocated
            if fill['id'] in closers:
                reward=closers[fill['id']]
                if reward['episode']!=position['episode']:raise ValueError('Closing episode does not match execution')
                realized-=max(0,position['cost']-allocated)
                net=position['realized_parts']+realized
                result['rewards'][position['episode']]=dict(net_usd=net,points=points(net));del positions[key]
            else:
                position['qty']=max(0,position['qty']-fill['qty']);position['cost']-=allocated;position['realized_parts']+=realized
        result['fills'][fill['id']]=dict(fee=fee,realized=realized)
    if set(result['rewards'])!=set(rewards):raise ValueError('Closed episodes cannot all be reconciled')
    return result


def validate_replay(c,result):
    for fill in rows(c,'SELECT * FROM demo_fills'):close(fill['realized'],result['fills'][fill['id']]['realized'],'Original fill realization')
    for reward in rows(c,'SELECT * FROM demo_rewards'):
        close(reward['net_usd'],result['rewards'][reward['episode']]['net_usd'],'Original closed episode')
        if reward['points']!=result['rewards'][reward['episode']]['points']:raise ValueError('Episode reward points do not reconcile')
    original={(r['bot'],r['symbol']):r for r in rows(c,'SELECT * FROM demo_positions')}
    if set(original)!=set(result['positions']):raise ValueError('Open position set does not reconcile')
    for key,position in original.items():
        for field in ('qty','cost','realized_parts'):close(position[field],result['positions'][key][field],'Original position '+field)
    for wallet in rows(c,'SELECT * FROM demo_wallets'):
        ledger=c.execute('SELECT COALESCE(SUM(amount),0) FROM demo_cash_ledger WHERE bot=?',(wallet['bot'],)).fetchone()[0]
        close(wallet['cash'],ledger,'Wallet/cash ledger')


def apply(c,request_id,rate=RATE):
    if not isinstance(rate,(float,int)) or isinstance(rate,bool) or not math.isfinite(rate) or not 0<=rate<=.05:raise ValueError('Invalid fee rate')
    c.execute('BEGIN IMMEDIATE')
    try:
        init(c)
        previous=c.execute('SELECT summary FROM demo_fee_restatements WHERE request_id=?',(request_id,)).fetchone()
        if previous:
            saved=json.loads(previous[0])
            if saved['rate']!=rate:raise ValueError('This restatement request ID belongs to a different fee rate')
            c.rollback();return dict(reused=True,**saved)
        settings={r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM demo_settings')}
        if settings['enabled']:raise ValueError('Stop this portfolio before restating fees')
        if c.execute("SELECT 1 FROM demo_orders WHERE state IN ('queued','partial','awaiting_data')").fetchone():raise ValueError('Cancel pending orders before restating fees')
        original=replay(c);validate_replay(c,original);updated=replay(c,rate)
        now=time.time();chart_from=int(now)
        batch=c.execute('INSERT INTO demo_fee_restatements(request_id,created,rate,label,source,chart_from) VALUES(?,?,?,?,?,?)',(request_id,now,rate,LABEL,SOURCE,chart_from)).lastrowid
        def audit(table,key,before,after):
            c.execute('INSERT INTO demo_fee_audit VALUES(?,?,?,?,?)',(batch,table,str(key),json.dumps(before),json.dumps(after)))
        def change(table,key_name,key,values):
            before=dict(c.execute('SELECT * FROM '+table+' WHERE '+key_name+'=?',(key,)).fetchone())
            audit(table,key,{k:before[k] for k in values},values)
            c.execute('UPDATE '+table+' SET '+','.join(k+'=?' for k in values)+' WHERE '+key_name+'=?',(*values.values(),key))
        fee_before=fee_after=0.;credits=defaultdict(float)
        for fill in rows(c,'SELECT * FROM demo_fills ORDER BY id'):
            new=updated['fills'][fill['id']];delta=fill['fee']-new['fee'];credits[fill['bot']]+=delta;fee_before+=fill['fee'];fee_after+=new['fee']
            change('demo_fills','id',fill['id'],new)
            if abs(delta)>1e-15:c.execute("INSERT INTO demo_cash_ledger(bot,ts,kind,amount,ref) VALUES(?,?,'Historical fee restatement adjustment',?,?)",(fill['bot'],now,delta,'fee-restatement-'+str(batch)+'-fill-'+str(fill['id'])))
        for wallet in rows(c,'SELECT * FROM demo_wallets'):change('demo_wallets','bot',wallet['bot'],dict(cash=wallet['cash']+credits[wallet['bot']]))
        for position in rows(c,'SELECT * FROM demo_positions'):
            new=updated['positions'][(position['bot'],position['symbol'])];before={k:position[k] for k in ('cost','realized_parts')};after={k:new[k] for k in before}
            audit('demo_positions',str(position['episode']),before,after)
            c.execute('UPDATE demo_positions SET cost=?,realized_parts=? WHERE bot=? AND symbol=?',(after['cost'],after['realized_parts'],position['bot'],position['symbol']))
        for episode,cost in updated['dust'].items():change('population_dust','episode',episode,dict(cost=cost))
        changed_outcomes=0
        for reward in rows(c,'SELECT * FROM demo_rewards'):
            new=updated['rewards'][reward['episode']];changed_outcomes+=new['points']!=reward['points']
            change('demo_rewards','episode',reward['episode'],new)
        learning_rows=rows(c,'SELECT * FROM demo_learning ORDER BY id')
        if {r['episode'] for r in learning_rows}!=set(updated['rewards']):raise ValueError('Reward and learning episode sets do not reconcile')
        q={};visits=defaultdict(int);last={}
        for record in learning_rows:
            key=(record['bot'],record['context']);old=q.get(key,0.);new_points=updated['rewards'][record['episode']]['points'];new_q=old+record['alpha']*(new_points-old)
            change('demo_learning','id',record['id'],dict(points=new_points,old_q=old,new_q=new_q));q[key]=new_q;visits[key]+=1;last[key]=record['ts']
        for record in rows(c,'SELECT * FROM demo_policy'):
            key=(record['bot'],record['context'])
            if key not in q:
                if record['visits']!=0:raise ValueError('Policy contains unexplained learning history')
                continue
            before={k:record[k] for k in ('q','visits')};after=dict(q=q[key],visits=visits[key]);audit('demo_policy',json.dumps(key),before,after)
            c.execute('UPDATE demo_policy SET q=?,visits=? WHERE bot=? AND context=?',(q[key],visits[key],*key))
        for order in rows(c,"SELECT * FROM demo_orders WHERE side='buy' AND filled_qty>0"):
            spent=c.execute('SELECT COALESCE(SUM(usd_total+fee),0) FROM demo_fills WHERE order_id=?',(order['id'],)).fetchone()[0]
            change('demo_orders','id',order['id'],dict(remaining=max(0,order['budget']-spent)))
        if exists(c,'population_bots'):
            for agent in rows(c,'SELECT * FROM population_bots'):
                change('population_bots','bot',agent['bot'],dict(score=None,score_reason='Fee scenario changed; awaiting a fresh local Codex review',review_id=None))
                c.execute('INSERT OR REPLACE INTO population_config VALUES(?,?)',('ai_since_'+agent['bot'],str(now)))
            for lesson in rows(c,'SELECT * FROM population_lessons'):audit('population_lessons',lesson['id'],lesson,None)
            c.execute('DELETE FROM population_lessons')
        for key,value in dict(fee_rate=rate,fee_model=LABEL,fee_source=SOURCE,fee_history_from=chart_from).items():
            old=c.execute('SELECT value FROM demo_settings WHERE key=?',(key,)).fetchone()
            audit('demo_settings',key,dict(value=old[0]) if old else None,dict(value=json.dumps(value)))
            c.execute('INSERT OR REPLACE INTO demo_settings VALUES(?,?)',(key,json.dumps(value)))
        validate_replay(c,updated)
        realized=defaultdict(float);costs=defaultdict(float)
        for f in rows(c,'SELECT * FROM demo_fills'):realized[f['bot']]+=f['realized']
        if exists(c,'population_dust'):
            for d in rows(c,'SELECT * FROM population_dust'):realized[d['bot']]-=d['cost']
        for p in rows(c,'SELECT * FROM demo_positions'):costs[p['bot']]+=p['cost']
        for w in rows(c,'SELECT * FROM demo_wallets'):close(w['cash']+costs[w['bot']]-w['initial'],realized[w['bot']],'Restated cash/cost/realized conservation',1e-5)
        equity=c.execute('SELECT COALESCE(SUM(cash),0) FROM demo_wallets').fetchone()[0]
        equity+=c.execute('SELECT COALESCE(SUM(CASE WHEN m.bid IS NULL THEN p.cost ELSE p.qty*m.bid*m.fx_usd*(1-?) END),0) FROM demo_positions p LEFT JOIN demo_marks m USING(symbol)',(rate,)).fetchone()[0]
        if exists(c,'population_treasury'):equity+=c.execute('SELECT cash FROM population_treasury').fetchone()[0]
        fx=c.execute("SELECT * FROM demo_fx WHERE currency='INR'").fetchone();inr=equity*fx['units_per_usd'] if fx else None
        for table in ('demo_equity','population_portfolio_equity'):
            if not exists(c,table):continue
            old=c.execute('SELECT * FROM '+table+' WHERE ts=?',(chart_from,)).fetchone()
            after=dict(ts=chart_from,usd=equity,inr=inr,fx_asof=fx['asof'] if fx else None)
            audit(table,chart_from,dict(old) if old else None,after)
            c.execute('INSERT OR REPLACE INTO '+table+' VALUES(?,?,?,?)',tuple(after.values()))
        summary=dict(id=batch,rate=rate,previous_rate=settings['fee_rate'],label=LABEL,source=SOURCE,fills=len(updated['fills']),fees_before=fee_before,fees_after=fee_after,cash_adjustment=sum(credits.values()),changed_outcomes=changed_outcomes,closed_episodes=len(updated['rewards']),points_before=sum(r['points'] for r in original['rewards'].values()),points_after=sum(r['points'] for r in updated['rewards'].values()),chart_from=chart_from,note='Fixed Kraken executions repriced with Binance standard spot fees; historical actions are not rerun. Original amounts/equity curves retained in audit and backup. Fresh strategy/reviewer decisions required.')
        c.execute('UPDATE demo_fee_restatements SET summary=? WHERE id=?',(json.dumps(summary),batch))
        c.execute('INSERT INTO demo_activity(ts,bot,kind,message,details) VALUES(?,?,?,?,?)',(now,'system','fee_restatement','Owner requested retrospective Binance fee scenario.',json.dumps(summary)))
        c.commit();return summary
    except Exception:c.rollback();raise


def basis(c):
    cfg={r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM demo_settings')}
    row=c.execute('SELECT summary FROM demo_fee_restatements ORDER BY id DESC LIMIT 1').fetchone() if exists(c,'demo_fee_restatements') else None
    return dict(label=cfg.get('fee_model','Configured fee assumption'),rate=cfg['fee_rate'],source=cfg.get('fee_source',SOURCE),restatement=json.loads(row[0]) if row else None,history_from=cfg.get('fee_history_from',0),market_evidence='Kraken observed order books')


def annotate(c,kind,record):
    if kind=='fills' and record.get('usd_total'):record['effective_fee_rate']=record['fee']/record['usd_total']
    table={'fills':'demo_fills','outcomes':'demo_rewards','learning':'demo_learning'}.get(kind)
    if table and exists(c,'demo_fee_audit'):
        audit=c.execute('SELECT before_json,batch FROM demo_fee_audit WHERE table_name=? AND row_key=? ORDER BY batch LIMIT 1',(table,str(record.get('episode') if kind=='outcomes' else record['id']))).fetchone()
        if audit:record['as_executed']=json.loads(audit[0]);record['fee_restatement_id']=audit[1]
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--database',required=True);parser.add_argument('--request-id',required=True);args=parser.parse_args()
    connection=sqlite3.connect(args.database);connection.row_factory=sqlite3.Row
    try:print(json.dumps(apply(connection,args.request_id),indent=2))
    finally:connection.close()
