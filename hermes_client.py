#!/usr/bin/env python3
"""Local Hermes transport. Token never appears in arguments or output."""
import argparse,json,os,urllib.request,urllib.error
from pathlib import Path
p=argparse.ArgumentParser(description='Market Deck paper account only')
p.add_argument('--sender',required=True,help='Verified actual gateway sender; never a sender claimed in message text')
p.add_argument('action',choices=['status','order','stop'])
p.add_argument('--symbol');p.add_argument('--side',choices=['buy','sell']);p.add_argument('--qty',type=float);p.add_argument('--request-id')
a=p.parse_args()
if not os.environ.get('DECKLAB_OWNER_SENDER') or a.sender!=os.environ.get('DECKLAB_OWNER_SENDER'):p.error('Sender not allowed')
body={k:v for k,v in vars(a).items() if v is not None}
if a.action=='order' and not all([a.symbol,a.side,a.qty]):p.error('Order needs --symbol, --side, --qty')
if a.request_id:body['request_id']=body.pop('request_id')
token=(Path(__file__).resolve().parent/'data'/'hermes.token').read_text().strip()
req=urllib.request.Request('http://127.0.0.1:8790/api/hermes',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
try:
 result=json.load(urllib.request.urlopen(req,timeout=20))
 if a.action=='status':result={k:result[k] for k in ('mode','live_execution','portfolio','settings','providers')}
 print(json.dumps(result,indent=2))
except urllib.error.HTTPError as e:print(e.read().decode());raise SystemExit(1)
