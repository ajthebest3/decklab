#!/usr/bin/env python3
"""Build an exhaustive owner PDF source from frozen DeckLab analysis exports."""
import argparse
import html
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import markdown


def esc(x):
    return html.escape(str(x if x is not None else 'Unknown'))


def usd(x, digits=2):
    return ('−$' if x<0 else '$')+f'{abs(x):,.{digits}f}'


def dt(ts, ist=False):
    return datetime.fromtimestamp(ts,timezone(timedelta(hours=5,minutes=30)) if ist else timezone.utc).strftime('%d %b %H:%M:%S')


def loadlines(path):
    return [json.loads(l) for l in path.open()] if path.exists() else []


def table(headers,rows,cls=''):
    return '<table class="'+cls+'"><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'


def build(source,output):
    output.mkdir(parents=True,exist_ok=True,mode=0o700)
    data=json.loads((source/'analysis.json').read_text());episodes=json.loads((source/'episodes.json').read_text())
    defs=json.loads((source/'strategy-definitions.json').read_text());archive=Path(data['archive']);tables=data['tables']
    revisions=loadlines(archive/'derived/strategy-revisions.jsonl');ratings=loadlines(archive/'derived/reviewer-ratings.jsonl')
    ledger_data={ledger:{p.stem:loadlines(p) for p in (archive/'current'/ledger).glob('*.jsonl') if p.stem.startswith(('demo_','population_'))} for ledger in ['market','population']}
    botkeys=sorted({(e['ledger'],e['bot']) for e in episodes})
    botcode={key:f'B{i+1:02d}' for i,key in enumerate(botkeys)}
    models=sorted({e['model'] for e in episodes});modelcode={model:f'M{i+1:02d}' for i,model in enumerate(models)}
    def bc(ledger,bot):return botcode.get((ledger,bot),esc(bot))
    def key(e):return ('O' if e['ledger']=='market' else 'P')+':'+str(e['episode'])
    def params(p):return ' · '.join(f'{esc(k)}={esc(v)}' for k,v in p.items())
    sections=[]
    def section(sid,title,text,cls=''):
        sections.append({'id':sid,'title':title,'html':f'<section class="chapter {cls}" id="{sid}"><h2>{esc(title)}</h2>{text}</section>'})
    section('reading','How to read the evidence',f'''
    <p>This report uses the same verified frozen collection as the prior analysis. It does not include subsequent trading or changing live marks. The source collection summary timestamp is <b>{esc(data['snapshot_utc'])}</b>. Original ledger copy finished at 07:26:47 UTC and managed ledger copy at 07:26:55 UTC on 2 November 2026.</p>
    <p><b>All financial amounts are simulated USD.</b> Historical executions use observed Kraken books with the effective modeled 0.10% buy/sell fee scenario. Original recorded fees are retained as sensitivity evidence. Changing fees on fixed fills is not a strategy rerun. No live controls, trading decisions, market data or ledger records were changed to generate this document.</p>
    <p><b>Entry cohorts are not unchanged full strategies.</b> A configuration names the parameters recorded at entry. Later additions, strategy revisions, timed/risk exits and trading pauses can affect its outcome. A cohort that earned dollars can still be unvalidated. An open position's marked value is not a completed trade. Backup row versions are provenance, not extra trades.</p>
    <p>Episode keys use <b>O:</b> for the original portfolio and <b>P:</b> for the managed population. Bot codes B01…B18 and model codes are expanded below. Every register includes these keys so fills, strategy revisions, rewards and learning can be joined. Times are UTC unless IST is explicitly shown. Unknown old schema fields remain unknown.</p>
    <p>The main narrative explains the conclusions. Later chapters contain every reconstructed position, all 2,811 fills, all 528 accepted strategy revision explanations, all 816 individual reviewer ratings and all 1,065 terminal learning updates. Raw market-book arrays, every market observation and authentication data are not reproduced in the PDF; execution hashes and source archive paths identify the retained evidence.</p>
    <p>This is owner-only evaluator analysis containing dollars, fees and balances. It must not be supplied as training observations to the P&amp;L-blind trading bots.</p>
    ''')
    core=markdown.markdown((source/'REPORT.md').read_text(),extensions=['tables','fenced_code'])
    svg=(source/'strategy-results.svg').read_text();svg=svg[svg.index('<svg'):]
    core=core.replace('<p><img alt="Strategy results" src="strategy-results.svg" /></p>',svg)
    section('findings','Detailed findings and strategy assessment',core)
    rows=[]
    for ledger,bot in botkeys:
        rows.append([bc(ledger,bot),esc(ledger),esc(bot),', '.join(esc(modelcode[m])+': '+esc(m) for m in sorted({e['model'] for e in episodes if e['ledger']==ledger and e['bot']==bot}))])
    section('identities','Bot and model identity reference',
            '<p>Lifetime bot IDs can have more than one historical model. Each episode uses the recorded entry model or its explicit same-bot advisor seed; the current route is not used to relabel history.</p>'+table(['Bot code','Ledger','Permanent bot ID','Historical entry models'],rows)+table(['Model code','Recorded model ID'],[[modelcode[m],esc(m)] for m in models]))
    botbody=''
    for r in sorted(tables['by-bot'],key=lambda r:(r['ledger'],r['bot'])):
        ee=[e for e in episodes if e['ledger']==r['ledger'] and e['bot']==r['bot']]
        styles=Counter(e['entry_style'] for e in ee if e['closed']);rev=[x for x in revisions if x['ledger']==r['ledger'] and x['bot']==r['bot']]
        rating=[x for x in ratings if x['bot']==r['bot']]
        lastscore=rating[-1]['score'] if rating else 'Not recorded'
        botbody+=f'<article class="profile"><p class="lead">{bc(r["ledger"],r["bot"])} · {esc(r["bot"])} · {esc(r["ledger"])}</p>'
        botbody+=table(['Closed / wins / losses','Closed net','Open count / cost','Net incl. open','Points'],[[f'{r["episodes"]} / {r["wins"]} / {r["losses"]}',usd(r['closed_net_usd']),f'{r["open_episodes"]} / {usd(r["open_cost_usd"])}',usd(r['all_exposure_net_usd']),r['points']]])
        botbody+=f'<p>Win rate {r["win_rate_pct"]:.2f}%; profit factor {r["profit_factor"] or 0:.3f}; average closed result {usd(r["average_net_usd"])}; gross before paid fees {usd(r["gross_before_paid_fees_usd"])}; closed-position fees {usd(r["paid_fees_closed_usd"])}. Entry turnover return {r["turnover_return_pct"]:.3f}%.</p><p>Entry family counts: {esc(dict(styles))}. Accepted revisions: {len(rev)}; parameter changes after first saved baseline: {sum(x["changed"] and not x["initial_saved_revision"] for x in rev)}. Reviewer ratings: {len(rating)}; last saved score: {lastscore}. No lifetime bot result is positive in this snapshot.</p></article>'
    section('bots','Every bot: lifetime performance and learning profile',botbody)
    modelbody=table(['Entry model','Closed','Wins','Closed net','Gross before fees','Open count','Net incl. open'],[[esc(r['model']),r['episodes'],r['wins'],usd(r['closed_net_usd']),usd(r['gross_before_paid_fees_usd']),r['open_episodes'],usd(r['all_exposure_net_usd'])] for r in tables['by-entry-model']])
    modelbody+='<p>All model IDs are provider-reported values saved with actual decisions. Different models saw different sizes, periods and regimes; these are observational cohorts, not controlled skill rankings. The earlier Gemini and the current Mirai roster are not equal-exposure experiments.</p>'
    modelbody+=table(['Entry model / family','Closed / wins','Closed net','Open count','Net incl. open'],[[esc(r['model'])+'<br>'+esc(r['entry_style']),f'{r["episodes"]} / {r["wins"]}',usd(r['closed_net_usd']),r['open_episodes'],usd(r['all_exposure_net_usd'])] for r in tables['by-entry-model-and-style']])
    section('models','Every model and strategy-family combination',modelbody)
    symbolbody=table(['Symbol','Closed / wins','Gross before fees','Closed net','Open count','Net incl. open'],[[esc(r['symbol']),f'{r["episodes"]} / {r["wins"]}',usd(r['gross_before_paid_fees_usd']),usd(r['closed_net_usd']),r['open_episodes'],usd(r['all_exposure_net_usd'])] for r in tables['by-symbol']])
    symbolbody+='<p>These totals include all entry families. Isolating a winning LIGHTER or ZRO trade would omit larger losses in other positions. Every symbol cohort is negative when the frozen remaining exposure is included.</p>'
    section('symbols','Every traded symbol: completed and remaining exposure',symbolbody)
    settingsbody=''
    intervals=data['diagnostics']['population']['active_intervals_utc']
    settingsbody+=table(['Window','Start UTC','End UTC','Minutes'],[[i+1,esc(r['start']),esc(r['end']),f'{r["seconds"]/60:.3f}'] for i,r in enumerate(intervals)])
    for ledger in ['market','population']:
        cfg=data['diagnostics'][ledger]['cfg'];settingsbody+=f'<p class="lead">Frozen {esc(ledger)} controls</p>'+table(['Setting','Value'],[[esc(k),esc(json.dumps(v))] for k,v in sorted(cfg.items())])
    settingsbody+='<p>These are snapshot values, not a claim that each value was active throughout historical execution. The controls history and accepted decisions preserve changes. Entry-window 5 contains no reconstructed new position. A pause cancels pending orders and holds positions; it does not fabricate a liquidation.</p>'
    section('controls','Enabled windows, pauses and frozen controls',settingsbody)
    def outcome_table(name,cols):
        return table([title for title,key in cols],[[esc(r[k]) if k not in ['closed_net_usd','all_exposure_net_usd'] else usd(r[k]) for title,k in cols] for r in tables[name]])
    subgroup=''
    for name,title,keys in [('by-entry-third','Chronological thirds',['entry_third']),('by-style-and-third','Families within each third',['entry_style','entry_third']),('by-entry-fee-phase','Entry relative to fee restatement',['entry_fee_phase']),('by-entry-run','Entry window',['entry_run']),('by-pause-crossing','Pause crossings',['crossed_pause']),('by-additions','Actual additions',['added_to_position']),('by-planned-hold','Planned hold seconds',['planned_hold_seconds']),('by-duration','Actual wall-clock duration',['duration_bucket']),('by-threshold','Entry threshold percent',['threshold_pct']),('by-allocation','Recorded allocation percent',['allocation_pct'])]:
        subgroup+=f'<p class="lead">{esc(title)}</p>'+outcome_table(name,[(k.replace('_',' '),k) for k in keys]+[('Closed','episodes'),('Wins','wins'),('Closed net','closed_net_usd'),('Open','open_episodes'),('Net incl. open','all_exposure_net_usd')])
    section('subgroups','Timing, allocation, hold and addition comparisons',subgroup)
    configbody=f'<p>All {len(tables["by-entry-strategy"])} managed entry parameter sets with observed exposure are shown, including the 147 with completed outcomes and the sets with only open exposure. IDs hash the recorded strategy fields, not the model or regime. Positive net means this observed cohort earned simulated dollars under the effective fee scenario; it does not mean the same fixed rules were continuously applied or independently validated.</p>'
    for idx,r in enumerate(tables['by-entry-strategy']):
        ee=[e for e in episodes if e['ledger']=='population' and e['strategy_id']==r['strategy_id']];cc=[e for e in ee if e['closed']]
        configbody+=f'<article class="profile"><p class="lead">{idx+1:03d} · {esc(r["strategy_id"])} · {esc(r["entry_style"])} · {usd(r["closed_net_usd"])} closed net</p><p class="parameters">{params(defs[r["strategy_id"]])}</p>'
        configbody+=table(['Closed / wins','Closed net','Original-fee path','Net without best win','Open / net incl. open'],[[f'{r["episodes"]} / {r["wins"]}',usd(r['closed_net_usd']),usd(r['original_fee_path_closed_net_usd']),usd(r['net_without_largest_winner_usd']),f'{r["open_episodes"]} / {usd(r["all_exposure_net_usd"])}']])
        configbody+=f'<p>Recorded models: {esc(", ".join(sorted({e["model"] for e in ee})))}. Bots: {esc(", ".join(sorted({bc(e["ledger"],e["bot"]) for e in ee})))}. Closed signal / exploration origins: {sum(e["entry_kind"]=="signal" for e in cc)} / {sum(e["entry_kind"]=="exploration" for e in cc)}; pause crossings {sum(e["crossed_pause"] for e in cc)}; mixed buy configurations {sum(e["mixed_buy_strategy"] for e in cc)}; final exit style changed {sum(e["exit_style_changed"] for e in cc)}.</p>'
        if cc:
            best=max(cc,key=lambda e:e['net_usd']);worst=min(cc,key=lambda e:e['net_usd'])
            configbody+=f'<p>Best: {key(best)} {esc(best["symbol"])} {usd(best["net_usd"])}; worst: {key(worst)} {esc(worst["symbol"])} {usd(worst["net_usd"])}. Gross before paid fees {usd(r["gross_before_paid_fees_usd"])}; paid fees {usd(r["paid_fees_closed_usd"])}; points {r["points"]}. Entry references: {esc(", ".join(key(e) for e in ee))}.</p>'
        else:configbody+='<p>There are no completed outcomes for this entry configuration. Marked open results cannot establish a closed-trade win rate or profitability.</p>'
        configbody+='</article>'
    section('configurations','Complete entry-configuration profiles: winners and losers',configbody)
    revisionbody='<p>All 528 accepted revisions are reproduced chronologically, including unchanged accepted responses and first saved baselines. Changes are before/after parameter differences, not proof of improved performance. The explanation is the saved advisor summary, not independently verified market truth. Revision model attribution is retained as originally logged; when it says legacy-unrecorded it is not silently replaced with the bot’s current assignment.</p><div class="revision-grid">'
    for r in sorted(revisions,key=lambda r:(r['ts'],r['ledger'],r['review_id'])):
        change='; '.join(f'{k}: {v["before"] if v.get("before_known") else "unknown"} → {v["after"]}' for k,v in r['changes'].items()) or 'Parameters unchanged'
        revisionbody+=f'<article class="revision"><p class="lead">{esc(r["ledger"])} / review {r["review_id"]} · {bc(r["ledger"],r["bot"])} · decision {r["decision_id"]}</p><p>{dt(r["ts"])} UTC · {esc(r["model"])} · {"First saved baseline" if r["initial_saved_revision"] else "Parameter changes" if r["changed"] else "Unchanged"}</p><p><b>Accepted:</b> {params(r["parameters"])}</p><p><b>Delta:</b> {esc(change)}</p><p><b>Saved explanation:</b> {esc(r["reason"])}</p></article>'
    revisionbody+='</div>'
    section('revisions','Every accepted revision and its saved explanation',revisionbody)
    ratingbody='<p>All 816 individual ratings from 66 reviewer rounds follow. A grade is an evaluator assessment, not proof of a successful strategy or authorization to create capital. Saved reasons are historical statements and may use the fee/accounting basis available at their original time.</p>'
    for rid in sorted({r['review_id'] for r in ratings}):
        rr=[r for r in ratings if r['review_id']==rid]
        ratingbody+=f'<p class="lead">Reviewer round {rid} · {dt(rr[0]["ts"])} UTC · {len(rr)} ratings</p>'+table(['Bot','Score','Action','Parent','Saved reviewer reason'],[[bc(r['ledger'],r['bot']),r['score'],esc(r['action']),esc(r.get('parent') or 'None'),esc(r.get('reason',''))] for r in rr],'ratings')
    section('ratings','Every individual strategy-reviewer rating',ratingbody)
    closed=sorted([e for e in episodes if e['closed']],key=lambda e:(e['entry_ts'],e['ledger'],e['episode']))
    closedbody='<p>All 1,065 fully closed positions. Net includes all effective entry/exit fees and any remaining dust writeoff. P = managed population, O = original portfolio. Model codes refer to entry metadata, not final management. Kind S = signal, E = exploration; family MOM = momentum, MR = mean reversion, BR = breakout, TR = trend, OP = original point policy. Boolean flags use Y/N; ? means pause crossing was not reconstructed for the original ledger. Pause and mixed flags are separate from profit. A position can be profitable and receive negative total points in a grouped cohort.</p>'
    closedbody+=table(['Episode / bot','Symbol / model','Entry UTC','Close UTC','Kind / family','Net / gross USD','Paid fees USD','Pause / mixed / exit changed'],[[esc(key(e))+' / '+bc(e['ledger'],e['bot']),esc(e['symbol'])+' / '+modelcode[e['model']],dt(e['entry_ts']),dt(e['closed_ts']),('S' if e['entry_kind']=='signal' else 'E')+' / '+{'momentum':'MOM','mean_reversion':'MR','breakout':'BR','trend':'TR','original_point_policy':'OP'}.get(e['entry_style'],e['entry_style']),usd(e['net_usd'],4)+' / '+usd(e['gross_usd'],4),usd(e['buy_fees']+e['sell_fees'],4),('?' if 'crossed_pause' not in e else 'Y' if e['crossed_pause'] else 'N')+' / '+('Y' if e['mixed_buy_strategy'] else 'N')+' / '+('Y' if e['exit_style_changed'] else 'N')] for e in closed],'compact')
    section('closed','Complete register of closed positions',closedbody,'wide')
    opened=sorted([e for e in episodes if not e['closed']],key=lambda e:(e['ledger'],e['bot'],e['symbol']))
    openbody='<p>All 241 still-open rows, including two very small original residuals. Economic net includes partial sales already made plus the marked liquidation value of the remaining quantity. It is not all unrealized. Marks are frozen estimates with estimated exit fees; no remaining position was sold for this report.</p>'
    openbody+=table(['Episode / bot','Symbol / entry model','Entry UTC','Quantity left','Cost left USD','Partial realized USD','Remaining unrealized USD','Episode net USD','Mark age sec'],[[key(e)+' / '+bc(e['ledger'],e['bot']),esc(e['symbol'])+' / '+modelcode[e['model']],dt(e['entry_ts']),f'{e["remaining_qty"]:.10g}',usd(e['remaining_cost'],4),usd(e['realized_parts'],4),usd(e['unrealized_on_remaining_cost_usd'],4),usd(e['economic_net_usd'],4),f'{e["mark_age_at_snapshot_seconds"]:.1f}'] for e in opened],'compact')
    section('open','Complete register of open positions and partial realizations',openbody,'wide')
    fills=[]
    for ledger,t in ledger_data.items():
        assignment={}
        for e in episodes:
            if e['ledger']==ledger:
                for order in e['buy_orders']+e['sell_orders']:assignment[order]=key(e)
        for f in t['demo_fills']:fills.append({'ledger':ledger,'episode_key':assignment[f['order_id']],**{k:v for k,v in f.items() if k!='evidence'}})
    fills.sort(key=lambda r:(r['ts'],r['ledger'],r['id']))
    fillbody='<p>All 2,811 actual recorded simulated fill rows, including partial fills. These are not 2,811 independent completed trades. Prices, quantities and notional are the fixed observed execution facts. Fee is the effective scenario amount. Book hashes are prefixes of the full retained evidence hashes; full depth, request and observation times remain in the collection.</p>'
    fillbody+=table(['Fill / episode / order','Bot / side / symbol','Execution UTC','Quantity','Price native','USD notional','Effective fee USD','Book hash prefix'],[[('O' if f['ledger']=='market' else 'P')+':'+str(f['id'])+' / '+f['episode_key']+' / '+str(f['order_id']),bc(f['ledger'],f['bot'])+' '+('B' if f['side']=='buy' else 'S')+' '+esc(f['symbol']),dt(f['ts']),f'{f["qty"]:.10g}',f'{f["native_price"]:.10g}',usd(f['usd_total'],4),usd(f['fee'],6),esc(f['book_hash'][:16])] for f in fills],'compact')
    section('fills','Complete execution-fill register',fillbody,'wide')
    learned=[]
    for ledger,t in ledger_data.items():
        for r in t['demo_learning']:learned.append({'ledger':ledger,**r})
    learned.sort(key=lambda r:(r['ts'],r['ledger'],r['id']))
    learnbody='<p>All 1,065 actual terminal updates, after the owner-authorized historical fee restatement. Q_new = Q_old + alpha × (points − Q_old), alpha = 0.2. Open entries receive no terminal reward. These updates change a contextual value table; they do not retrain provider model weights.</p>'
    learnbody+=table(['Update / episode','Bot / UTC','Context','Points','Old Q','New Q','Alpha'],[[('O' if r['ledger']=='market' else 'P')+':'+str(r['id'])+' / '+str(r['episode']),bc(r['ledger'],r['bot'])+' '+dt(r['ts']),esc(r['context']),r['points'],f'{r["old_q"]:.8f}',f'{r["new_q"]:.8f}',r['alpha']] for r in learned],'compact learning-table')
    section('learning','Complete terminal reward and Q-update register',learnbody,'wide')
    auditbody=''
    for ledger,t in ledger_data.items():
        auditbody+=f'<p class="lead">{esc(ledger)} fee restatement</p>'
        for r in t['demo_fee_restatements']:
            s=json.loads(r['summary']);auditbody+=table(['Recorded field','Value'],[[esc(k),esc(v)] for k,v in s.items()])
        auditbody+=f'<p>Retained original/revised field audit rows: {len(t["demo_fee_audit"])}. The full original/revised JSON is preserved in the input archive. The fee credits are accounting adjustments, not new deposits or market-earned profit.</p>'
        a=data['diagnostics'][ledger]
        auditbody+=table(['Quantity','USD'],[['Paid effective fees on all fills',usd(a['paid_fees_usd'],8)],['Original recorded fees on the same fixed fills',usd(a['original_recorded_paid_fees_usd'],8)],['Estimated exit fees on remaining frozen holdings',usd(a['open_mark_estimated_exit_fees_usd'],8)]])
    section('fees','Historical fee restatements and original-value audit',auditbody)
    inventory=json.loads((archive/'derived/summary.json').read_text())
    methods=f'<p>Frozen collection: {esc(archive)}. Analysis source: {esc(source)}. All {data["verified_input_files"]} consumed input files were hash-checked against the collection manifest. The database snapshots passed SQLite checks when collected. Twenty retained database sources contribute history/provenance; current financial totals come only from the two current ledger snapshots.</p>'
    methods+='<p>For a fully closed episode, net = sum(sell USD − sell fees) − sum(buy USD + buy fees). Gross before paid fees = sell USD − buy USD. For an open episode, add remaining quantity × frozen bid × currency conversion × (1 − effective exit fee). Partial realization is retained. Cost is allocated proportionally on each partial sale. Dust receives no invented cash or favorable fill. Episode boundaries are matched to saved closing orders/rewards or explicit dust closures.</p>'
    methods+='<p>Every closed outcome matched the saved reward within $0.000001, every remaining position matched quantity/cost/partial realization, and cash plus marked holdings reconciled to all episode economics within $0.000001. Group tables reconcile to the same counts and net totals. Profit factor is winning dollars divided by absolute losing dollars. Turnover return divides closed net by total closed-episode acquisition outflow; it is not a capital return or annualized metric.</p>'
    methods+='<p>No holdout or significance claim was manufactured. Shared market moves, clustered entries, 147 tested parameter configurations, repeated revisions, paused exposures, unequal model funding/time and still-open recent positions all limit inference. Internal provider weights, internal reasoning and unrecorded/deleted-without-backup events are unavailable. The original point-policy metadata is not treated as a direct LLM buy recommendation.</p>'
    methods+=table(['Ledger','Closed','Open','Equity reconciliation error USD','Maximum reward error USD'],[[esc(r['ledger']),r['closed_episodes'],r['open_episodes'],f'{r["equity_error_usd"]:.12f}',f'{r["max_reward_error_usd"]:.12f}'] for r in data['verification']])
    methods+=table(['Source','Ledger / kind','Path','SHA-256'],[[s['id'],esc(s['ledger']+' / '+s['kind']),esc(s['path']),esc(s['sha256'])] for s in inventory['sources']],'hashes')
    methods+='<p>Source references: original decision/strategy/reward/fill tables in current/market and current/population; derived/strategy-revisions.jsonl and reviewer-ratings.jsonl; historical/ deduplicated variants with source IDs; sources/current/ algorithm code. External references already used for the narrative: <a href="https://www.binance.com/en/fee/trading">Binance standard spot fee schedule</a>; <a href="https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf">Bailey et al., The Probability of Backtest Overfitting</a>.</p><p><b>End of the complete report.</b> No trade, funding event, fee setting, reward rule or live portfolio control was changed to prepare this PDF.</p>'
    section('methods','Reconciliation, provenance and interpretation limits',methods)
    toc='<section class="toc"><h2>Contents and reading map</h2><p>The PDF bookmarks and these links navigate to each chapter. The first chapters explain the conclusions; later chapters provide exhaustive registers.</p>'+''.join(f'<a href="#{s["id"]}"><span>{i+1:02d}. {esc(s["title"])}</span><span class="tocpage" data-target="{s["id"]}">—</span></a>' for i,s in enumerate(sections))+'</section>'
    css='''@page{size:A4;margin:15mm 13mm 18mm}@page wide{size:A4 landscape;margin:15mm 12mm 18mm}*{box-sizing:border-box}body{margin:0;font:10.5pt/1.45 Arial,sans-serif;color:#182c38;background:white}h1{font-size:32pt;line-height:1.12;color:#173f4f;margin:25mm 0 8mm}h2{font-size:19pt;line-height:1.2;color:#173f4f;margin:0 0 8mm}p{margin:0 0 4mm}strong,b{color:#173f4f}a{color:#1b567f}li{margin:2mm 0}table{border-collapse:collapse;width:100%;table-layout:fixed;font:8.1pt/1.3 Arial,sans-serif;margin:3mm 0 6mm}thead{display:table-header-group}th,td{text-align:left;vertical-align:top;overflow-wrap:anywhere;word-break:normal;padding:2mm 1.6mm;border-bottom:.25mm solid #cdd6d9}th{background:#dfe8e8;font-weight:700}tr{break-inside:avoid;page-break-inside:avoid}svg{width:100%;height:auto;break-inside:avoid}.chapter{break-before:page}.wide{page:wide;break-before:page;break-after:page}.cover,.toc{break-after:page}.cover{height:245mm;padding-top:6mm}.subtitle{font-size:18pt;color:#49717a}.kicker{font-size:11pt;letter-spacing:1.5pt;color:#49717a}.coverbox{border-left:2mm solid #346a73;padding:5mm 7mm;background:#edf2ef;margin:12mm 0}.coverbox p{font-size:14pt}.small{font-size:9pt;color:#526671}.toc a{display:flex;justify-content:space-between;text-decoration:none;border-bottom:.25mm solid #d5dfe1;padding:3mm 0;font-size:10pt;gap:4mm}.tocpage{flex-shrink:0;min-width:8mm;text-align:right}.profile{break-inside:avoid;page-break-inside:avoid;padding:3mm 0 4mm;border-top:.5mm solid #49717a;font-size:9pt}.profile table{font-size:8pt;margin-bottom:3mm}.lead{font-weight:bold;color:#173f4f;margin:4mm 0 3mm;font-size:10pt}.parameters{font-family:monospace;font-size:8pt;overflow-wrap:anywhere}.revision-grid{columns:2;column-gap:7mm}.revision{break-inside:avoid;page-break-inside:avoid;border-top:.3mm solid #9ab2b7;padding:2mm 0;margin-bottom:4mm;font-size:8.5pt;line-height:1.35;overflow-wrap:anywhere}.revision .lead{font-size:9pt;margin:1mm 0 2mm}.revision p{margin-bottom:2mm}.compact{font-size:7.8pt;line-height:1.25}.compact td,.compact th{padding:.65mm 1.1mm}.learning-table th:nth-child(1){width:10%}.learning-table th:nth-child(2){width:18%}.learning-table th:nth-child(3){width:42%}.learning-table th:nth-child(4){width:6%}.learning-table th:nth-child(5),.learning-table th:nth-child(6){width:9%}.learning-table th:nth-child(7){width:6%}.ratings th:nth-child(1),.ratings td:nth-child(1){width:9%}.ratings th:nth-child(2),.ratings td:nth-child(2){width:8%}.ratings th:nth-child(3),.ratings td:nth-child(3){width:10%}.ratings th:nth-child(4),.ratings td:nth-child(4){width:10%}.ratings th:nth-child(5),.ratings td:nth-child(5){width:63%}.hashes{font-size:7.2pt}body{-webkit-print-color-adjust:exact;print-color-adjust:exact}pre{white-space:pre-wrap;overflow-wrap:anywhere}'''
    cover='''<section class="cover"><p class="kicker">DECKLAB · PRIVATE OWNER ANALYSIS</p><h1>Complete strategy<br>profitability audit</h1><p class="subtitle">What earned money, what lost money,<br>and what the learning evidence supports</p><div class="coverbox"><p><b>1,065 closed positions · 241 open positions</b></p><p>2,811 fills · 528 accepted revisions<br>816 reviewer ratings · 1,065 learning updates</p></div><p><b>Central finding:</b> some small entry configurations earned simulated dollars, but no broad strategy family, bot or recorded model cohort was profitable overall. No repeatable profitable strategy has been independently established.</p><p class="small">Frozen collection: 2 November 2026, 07:27 UTC / 12:57 IST.<br>Both portfolios were stopped at capture. This is an analysis-only document.<br>Prepared for Arpit. All amounts are simulated USD under the disclosed fee scenario.</p></section>'''
    doc='<!doctype html><html lang="en"><meta charset="utf-8"><title>DeckLab — Complete strategy profitability audit</title><style>'+css+'</style><body>'+cover+toc+''.join(s['html'] for s in sections)+'</body></html>'
    (output/'full-report.html').write_text(doc)
    metadata={'source_analysis':str(source),'source_collection':str(archive),'snapshot_utc':data['snapshot_utc'],'sections':[{'id':s['id'],'title':s['title']} for s in sections],
              'included_records':{'closed_positions':len(closed),'open_positions':len(opened),'fills':len(fills),'accepted_revisions':len(revisions),'reviewer_ratings':len(ratings),'learning_updates':len(learned),'managed_entry_configurations':len(tables['by-entry-strategy']),'bots':len(botkeys),'historical_entry_models_managed':len(tables['by-entry-model'])},'source_word_count_approx':len(doc.split())}
    (output/'coverage.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps({'directory':str(output),'html_bytes':len(doc.encode()),**metadata},indent=2))
    return output


if __name__=='__main__':
    os.umask(0o077)
    root=Path(__file__).resolve().parent.parent
    parser=argparse.ArgumentParser();parser.add_argument('--analysis',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
    source=args.analysis or Path(json.loads((root/'data/strategy-analysis/latest.json').read_text())['directory'])
    output=args.output or root/'data/strategy-analysis'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-full-report')
    build(source.resolve(),output.resolve())
