"""Mirai launch roster and evaluator-gated, point-only strategy lessons."""
import json
import time

class ModelRoster:
    def __init__(self,engine):self.e=engine

    def init(self,c):
        c.executescript('''
        CREATE TABLE IF NOT EXISTS population_model_plan(model TEXT PRIMARY KEY,count INTEGER,effort TEXT);
        CREATE TABLE IF NOT EXISTS population_lessons(id INTEGER PRIMARY KEY,created REAL,donor TEXT,model TEXT,review_id INTEGER,through_episode INTEGER,strategy TEXT,feedback TEXT,UNIQUE(donor,through_episode));
        ''')
        c.execute("INSERT OR IGNORE INTO population_config VALUES('model_roster_enabled','false')")

    def status(self,include_lessons=True):
        with self.e.db() as c:
            enabled=json.loads(c.execute("SELECT value FROM population_config WHERE key='model_roster_enabled'").fetchone()[0])
            return dict(enabled=enabled,models=self.e.rows(c,'SELECT * FROM population_model_plan ORDER BY model'),lessons=self.e.rows(c,'SELECT * FROM population_lessons ORDER BY id DESC LIMIT 20') if include_lessons else [],lesson_count=c.execute('SELECT COUNT(*) FROM population_lessons').fetchone()[0])

    def configure(self,body):
        if not isinstance(body,dict) or set(body)!={'models'} or not isinstance(body['models'],list) or not 1<=len(body['models'])<=200:raise ValueError('Expected a model roster')
        if not self.e.mirai:raise ValueError('Mirai is unavailable')
        catalog=self.e.mirai.models()
        if catalog.get('error'):raise ValueError(catalog['error'])
        valid={m['id'] for m in catalog['models'] if m.get('chat_supported') and m.get('active',True)}
        seen=set();total=0
        for row in body['models']:
            if not isinstance(row,dict) or set(row)!={'model','count','effort'}:raise ValueError('Invalid model roster row')
            if row['model'] not in valid or row['model'] in seen:raise ValueError('Unknown or repeated Mirai model')
            if type(row['count']) is not int or not 0<=row['count']<=200:raise ValueError('Bot count must be 0..200')
            if row['effort'] not in (None,'low','medium','high'):raise ValueError('Invalid reasoning effort')
            total+=row['count'];seen.add(row['model'])
        if not 1<=total<=200:raise ValueError('Choose between 1 and 200 bots across models')
        with self.e.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if self.e.settings(c)['enabled']:raise ValueError('Stop bots before changing the model roster')
            c.execute('DELETE FROM population_model_plan')
            c.executemany('INSERT INTO population_model_plan VALUES(?,?,?)',[(r['model'],r['count'],r['effort']) for r in body['models']])
            c.execute("UPDATE population_config SET value='true' WHERE key='model_roster_enabled'")
            self.e.controls.advance(c)
            self.e.log(c,'system','model_roster','Owner configured Mirai bot counts; capital is allocated only on Start',body)
        return dict(ok=True,bots=total)

    def start(self,c,cfg):
        plan=self.e.rows(c,'SELECT * FROM population_model_plan WHERE count>0 ORDER BY model')
        existing=self.e.rows(c,"SELECT * FROM population_bots WHERE state IN ('active','parked') ORDER BY state='active' DESC,slot")
        selected=set();launch=[];needed=0
        for row in plan:
            route=dict(provider='Mirai',model=row['model'],effort=row['effort'])
            eligible=[a for a in existing if a['bot'] not in selected and self.e.ai_route(c,a['bot'],a['provider'])['provider']=='Mirai' and self.e.ai_route(c,a['bot'],a['provider'])['model']==row['model']]
            keep=eligible[:row['count']];selected.update(a['bot'] for a in keep)
            new=row['count']-len(keep);needed+=new*cfg['bot_allocation_usd'];launch.append((route,keep,new))
        reserve=c.execute('SELECT cash FROM population_treasury').fetchone()[0]
        if needed>reserve+1e-7:raise ValueError('Model roster exceeds available reserve; reduce new bot counts or allocations')
        c.execute("UPDATE population_bots SET state='parked' WHERE state='active'")
        for route,keep,new in launch:
            for agent in keep:
                if self.e.ai_route(c,agent['bot'],agent['provider'])!=route:
                    c.execute('INSERT OR REPLACE INTO population_config VALUES(?,?)',('ai_since_'+agent['bot'],str(time.time())))
                c.execute("UPDATE population_bots SET state='active',model=?,effort=? WHERE bot=?",(route['model'],route['effort'],agent['bot']))
                c.execute('INSERT OR REPLACE INTO population_ai VALUES(?,?,?)',(agent['bot'],json.dumps(route),time.time()))
            for _ in range(new):
                slot=c.execute('SELECT COALESCE(MAX(slot),0)+1 FROM population_bots').fetchone()[0]
                self.e._spawn(c,slot,'Mirai',route=route)
        self.e.controls.advance(c)
        c.execute("UPDATE demo_settings SET value='true' WHERE key='enabled'")
        self.e.log(c,'system','portfolio_started','Owner started the Mirai model roster',dict(bots=sum(r['count'] for r in plan),new_allocation_usd=needed))
        return dict(ok=True,slots=sum(r['count'] for r in plan),allocation_per_bot=cfg['bot_allocation_usd'])

    def publish_lessons(self,c,review_id,result):
        cfg=self.e.settings(c)
        if not cfg['share_lessons_enabled']:return
        for rating in result['ratings']:
            if rating['score']<cfg['share_min_score']:continue
            donor=next((b for b in self.e.review_observation(c)['bots'] if b['bot']==rating['bot']),None)
            if not donor or not donor['marks_fresh'] or donor['net_usd']<cfg['clone_min_gain_usd'] or donor['closed_net_usd']<cfg['clone_min_gain_usd']:continue
            agent=c.execute('SELECT * FROM population_bots WHERE bot=?',(rating['bot'],)).fetchone()
            current=json.loads(agent['strategy'])
            route=self.e.ai_route(c,agent['bot'],agent['provider'])
            evidence=self.e.rows(c,'SELECT r.episode,r.net_usd,r.points,d.result FROM demo_rewards r JOIN demo_orders o ON o.id=r.episode JOIN demo_decisions d ON d.id=o.decision_id WHERE r.bot=?',(agent['bot'],))
            matched=[]
            for record in evidence:
                try:decision=json.loads(record['result'])
                except (ValueError,TypeError):continue
                if decision.get('strategy')==current and decision.get('model')==route['model']:matched.append(record)
            if len(matched)<cfg['clone_min_episodes'] or sum(r['points']>0 for r in matched)<cfg['clone_min_wins'] or sum(r['net_usd'] for r in matched)<cfg['clone_min_gain_usd']:continue
            through=c.execute('SELECT COALESCE(MAX(episode),0) FROM demo_rewards WHERE bot=?',(rating['bot'],)).fetchone()[0]
            route=self.e.ai_route(c,agent['bot'],agent['provider'])
            feedback=dict(points=sum(r['points'] for r in matched),wins=sum(r['points']>0 for r in matched),losses=sum(r['points']<0 for r in matched),closed_episodes=len(matched),reviewer_score=rating['score'],status='Passed owner in-sample sharing gates; future results unvalidated')
            inserted=c.execute('INSERT OR IGNORE INTO population_lessons(created,donor,model,review_id,through_episode,strategy,feedback) VALUES(?,?,?,?,?,?,?)',(time.time(),agent['bot'],route['model'],review_id,through,agent['strategy'],json.dumps(feedback)))
            if inserted.rowcount:self.e.log(c,agent['bot'],'lesson_shared','Evaluator-gated point-only strategy lesson shared across models',dict(review_id=review_id,through_episode=through))

    def observations(self,c):
        lessons=self.e.rows(c,'SELECT id,created,donor,model,strategy,feedback FROM population_lessons ORDER BY id DESC LIMIT 12')
        for lesson in lessons:
            lesson['strategy']=json.loads(lesson['strategy']);lesson['feedback']=json.loads(lesson['feedback'])
        # No evaluator dollars or reviewer free-text reasons are exposed.
        feedback=self.e.rows(c,"SELECT COALESCE(json_extract(d.result,'$.model'),'legacy-unrecorded') model,l.context,COUNT(*) episodes,SUM(l.points) points,AVG(l.points) mean_points FROM demo_learning l JOIN demo_orders o ON o.id=l.episode LEFT JOIN demo_decisions d ON d.id=o.decision_id GROUP BY model,l.context ORDER BY MAX(l.ts) DESC LIMIT 24")
        return lessons,feedback
