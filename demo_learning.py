"""Terminal-action value learning. Inputs/outputs contain points, never dollar accounting."""
import math, random, time

def context_key(asset,regime):
 change=asset.get('change') or 0
 trend='up' if change>1 else 'down' if change< -1 else 'flat'
 volatility='large_move' if abs(change)>5 else 'normal_move'
 return '|'.join([asset.get('kind','other'),trend,volatility,regime])

def init(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS demo_policy(bot TEXT,context TEXT,q REAL,visits INTEGER,updated REAL,PRIMARY KEY(bot,context));
 CREATE TABLE IF NOT EXISTS demo_learning(id INTEGER PRIMARY KEY,ts REAL,bot TEXT,episode INTEGER UNIQUE,context TEXT,points INTEGER,old_q REAL,new_q REAL,alpha REAL);
 ''')

def feedback(c,bot):
 return {'points':c.execute('SELECT COALESCE(SUM(points),0) FROM demo_learning WHERE bot=?',(bot,)).fetchone()[0],
  'updates':c.execute('SELECT COUNT(*) FROM demo_learning WHERE bot=?',(bot,)).fetchone()[0],
  'contexts':[dict(r) for r in c.execute('SELECT context,q,visits FROM demo_policy WHERE bot=? ORDER BY updated DESC LIMIT 20',(bot,))],
  'recent':[dict(r) for r in c.execute('SELECT context,points,new_q FROM demo_learning WHERE bot=? ORDER BY id DESC LIMIT 12',(bot,))]}

def learn(c,bot,episode,context,points):
 if points not in (-5,0,1):raise ValueError('Learning accepts only -5, 0 or +1 points')
 if c.execute('SELECT 1 FROM demo_learning WHERE episode=?',(episode,)).fetchone():return False
 row=c.execute('SELECT q,visits FROM demo_policy WHERE bot=? AND context=?',(bot,context)).fetchone()
 old=row['q'] if row else 0.;visits=row['visits'] if row else 0;alpha=.2
 # A fully closed position is a terminal episode: no future-value bootstrap.
 new=old+alpha*(points-old)
 c.execute('INSERT OR REPLACE INTO demo_policy VALUES(?,?,?,?,?)',(bot,context,new,visits+1,time.time()))
 c.execute('INSERT INTO demo_learning(ts,bot,episode,context,points,old_q,new_q,alpha) VALUES(?,?,?,?,?,?,?,?)',(time.time(),bot,episode,context,points,old,new,alpha))
 return True

def gate(c,bot,context,allow_exploration=False):
 row=c.execute('SELECT q,visits FROM demo_policy WHERE bot=? AND context=?',(bot,context)).fetchone()
 count=c.execute('SELECT COUNT(*) FROM demo_learning WHERE bot=?',(bot,)).fetchone()[0]
 epsilon=max(.03,.2/math.sqrt(1+count/20))
 q=row['q'] if row else 0;visits=row['visits'] if row else 0
 explore=bool(allow_exploration or visits>=3 and q<-.5 and random.random()<epsilon)
 # Authorized simulation learning may revisit failed contexts. Its bounded
 # size still responds to points: negative values progressively shrink trials.
 scale=max(.1,min(.5,.5+q*.08)) if allow_exploration else .25 if explore else max(.25,min(1,.75+q*.15))
 return {'allowed':visits<3 or q>=-.5 or explore,'scale':scale,
  'q':q,'visits':visits,'epsilon':epsilon,'explore':explore}
