"""Fast point-only candidate selection. No balances, entry prices or monetary rewards."""
import random
from demo_learning import context_key

DEFAULT_REVIEW={'exploration_rate':.1,'min_change':-5.,'batch_size':8,'hold_seconds':120}
def validate_review(value):
 if not isinstance(value,dict) or set(value)-set(DEFAULT_REVIEW):raise ValueError('Unsupported strategy review fields')
 limits={'exploration_rate':(.01,.25),'min_change':(-5,5),'batch_size':(1,16),'hold_seconds':(60,1800)}
 result=dict(DEFAULT_REVIEW)
 for key,number in value.items():
  if isinstance(number,bool) or not isinstance(number,(int,float)) or not limits[key][0]<=number<=limits[key][1]:raise ValueError('Strategy review is outside bounded limits')
  if key in ('batch_size','hold_seconds') and number!=int(number):raise ValueError('Expected an integer strategy setting')
  result[key]=number
 return result

def select(observation,review,regime,learning_mode=False):
 review=validate_review(review);feedback={p['context']:p for p in observation['point_feedback']['contexts']}
 pending=set(observation.get('pending_symbols',[]));held=set(observation['held_symbols']);candidates=[]
 for a in observation['markets']:
  if a['symbol'] in held|pending or a.get('provider')!='Kraken' or not a.get('quote_fresh') or a.get('currency')!='USD' or (a.get('turnover_estimate') or 0)<1000000:continue
  filter_met=(a.get('change') or 0)>=review['min_change']
  if not filter_met and not learning_mode:continue
  context=context_key(a,regime);prior=feedback.get(context,{});q=prior.get('q',0);visits=prior.get('visits',0)
  exploration=learning_mode or visits>=3 and q<-.5
  if exploration and not learning_mode and random.random()>=review['exploration_rate']:continue
  candidates.append({'symbol':a['symbol'],'context':context,'quote_fetched':a['fetched'],'score':q+.01*(a.get('change') or 0)+(.1 if filter_met else 0),'exploration':exploration,'review_filter_met':filter_met,'action':'buy','size':'policy'})
 candidates.sort(key=lambda a:(-a['score'],a['symbol']))
 return candidates
