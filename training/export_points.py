#!/usr/bin/env python3
"""Export closed executions and point rewards, labelling fee-restated scenarios."""
import argparse,json,os,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
def export(database,destination):
 with sqlite3.connect('file:'+str(Path(database).resolve())+'?mode=ro',uri=True) as c:
  c.row_factory=sqlite3.Row
  rows=c.execute('SELECT r.episode,r.bot,r.closed,r.points,o.symbol,o.context,o.reason,d.input_json,d.context_ts FROM demo_rewards r JOIN demo_orders o ON o.id=r.episode LEFT JOIN demo_decisions d ON d.id=o.decision_id ORDER BY r.closed,r.episode').fetchall()
  fee_basis={r['key']:json.loads(r['value']) for r in c.execute("SELECT key,value FROM demo_settings WHERE key IN ('fee_rate','fee_model','fee_history_from')")}
  samples=[]
  for row in rows:
   if not row['input_json']:continue
   observation=json.loads(row['input_json'])
   behavior='initial_rl_exploration' if row['reason'].startswith('Initial bounded RL exploration') else 'point_policy_exploration' if row['reason'].startswith('Continuous point-policy') else 'advisor'
   samples.append({'reward_basis':fee_basis,'historical_fee_restatement':bool(fee_basis.get('fee_history_from')),'episode':row['episode'],'agent':row['bot'],'behavior_policy':behavior,'observation':observation,'action':{'type':'buy','symbol':row['symbol'],'context':row['context']},'reward':row['points'],'terminal':True,'observation_time':row['context_ts'],'closed_time':row['closed']})
 path=Path(destination);path.parent.mkdir(parents=True,exist_ok=True)
 with open(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as stream:
  for sample in samples:stream.write(json.dumps(sample,allow_nan=False)+'\n')
 return len(samples)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--database',default=ROOT/'data/market.db');parser.add_argument('--output',default=ROOT/'data/training-points.jsonl');args=parser.parse_args()
 print('Exported',export(args.database,args.output),'closed execution episodes. Fee-restated rewards are labelled; no dollar P&L exported.')
