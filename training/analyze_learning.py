#!/usr/bin/env python3
"""Owner analysis of frozen, exported DeckLab records. Never opens live ledgers."""
import argparse
import csv
import hashlib
import json
import math
import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse(value):
    return json.loads(value) if isinstance(value, str) and value else value or {}


def utc(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def csvout(path, records):
    fields = list(dict.fromkeys(k for row in records for k in row))
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in records:
            row = {k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v for k, v in row.items()}
            writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v
                             for k, v in row.items()})


def summarise(records):
    closed = [r for r in records if r['closed']]
    opened = [r for r in records if not r['closed']]
    wins = [r['net_usd'] for r in closed if r['net_usd'] > 1e-6]
    losses = [r['net_usd'] for r in closed if r['net_usd'] < -1e-6]
    n = len(closed)
    capital = sum(r['buy_usd'] + r['buy_fees'] for r in closed)
    net = sum(r['net_usd'] for r in closed)
    all_net = sum(r['economic_net_usd'] for r in records)
    return dict(episodes=n, wins=len(wins), losses=len(losses),
                points=sum(r.get('points',0) for r in closed),
                win_rate_pct=100 * len(wins) / n if n else None,
                closed_net_usd=net, gross_before_paid_fees_usd=sum(r['gross_usd'] for r in closed),
                paid_fees_closed_usd=sum(r['buy_fees'] + r['sell_fees'] for r in closed),
                original_fee_path_closed_net_usd=sum(r['original_fee_path_net_usd'] for r in closed),
                average_net_usd=net / n if n else None,
                median_net_usd=statistics.median(r['net_usd'] for r in closed) if n else None,
                average_win_usd=statistics.mean(wins) if wins else None,
                average_loss_usd=statistics.mean(losses) if losses else None,
                profit_factor=sum(wins) / -sum(losses) if losses else None,
                turnover_return_pct=100 * net / capital if capital else None,
                mean_episode_return_pct=statistics.mean(r['net_return_pct'] for r in closed) if n else None,
                median_hold_minutes=statistics.median(r['hold_seconds'] / 60 for r in closed) if n else None,
                open_episodes=len(opened), open_cost_usd=sum(r['remaining_cost'] for r in opened),
                open_net_including_partial_exits_usd=sum(r['economic_net_usd'] for r in opened),
                all_exposure_net_usd=all_net,
                symbols=len({r['symbol'] for r in closed}), bots=len({r['bot'] for r in closed}),
                entry_hours=len({r['entry_hour'] for r in closed}),
                gross_winning_episodes=sum(r['gross_usd'] > 1e-6 for r in closed),
                fee_flipped_winners=sum(r['gross_usd'] > 1e-6 and r['net_usd'] < -1e-6 for r in closed),
                mixed_buy_strategy_episodes=sum(r['mixed_buy_strategy'] for r in closed),
                pure_entry_signal_episodes=sum(r['entry_kind'] == 'signal' for r in closed),
                pure_entry_exploration_episodes=sum(r['entry_kind'] == 'exploration' for r in closed),
                total_entry_usd=capital,
                max_win_usd=max(wins) if wins else None, max_loss_usd=min(losses) if losses else None,
                net_without_largest_winner_usd=net - max(wins) if wins else net)


def grouped(records, keys):
    groups = defaultdict(list)
    for r in records:
        groups[tuple(r.get(k) for k in keys)].append(r)
    return [dict(zip(keys, key), **summarise(value)) for key, value in groups.items()]


def analyse(archive, output):
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    all_episodes, all_orders, all_trades, verifications, diagnostics = [], [], [], [], {}
    manifests = json.loads((archive / 'manifest.json').read_text())
    verified_inputs=0
    for name,metadata in manifests['files'].items():
        if name.startswith('current/') or name=='derived/strategy-revisions.jsonl':
            if hashlib.sha256((archive/name).read_bytes()).hexdigest()!=metadata['sha256']:
                raise ValueError('Frozen input hash mismatch: '+name)
            verified_inputs+=1
    for ledger in ('market', 'population'):
        def load(table):
            path = archive / 'current' / ledger / (table + '.jsonl')
            return [json.loads(line) for line in path.open()] if path.exists() else []
        ds = {r['id']: r for r in load('demo_decisions')}
        orders = {r['id']: r for r in load('demo_orders')}
        rewards = {r['episode']: r for r in load('demo_rewards')}
        fills = load('demo_fills')
        dust = load('population_dust')
        positions = {(r['bot'], r['symbol']): r for r in load('demo_positions')}
        marks = {r['symbol']: r for r in load('demo_marks')}
        wallets = load('demo_wallets')
        current_bots = {r['bot']: r for r in load('population_bots')}
        cfg = {r['key']: parse(r['value']) for r in load('demo_settings')}
        fee_audit = {int(r['row_key']): parse(r['before_json']) for r in load('demo_fee_audit')
                     if r['table_name'] == 'demo_fills'}
        fee_change = load('demo_fee_restatements')
        fee_time = fee_change[0]['created'] if fee_change else None
        snapshot_meta=next(s for s in manifests['summary']['sources'] if s['ledger']==ledger and s['kind']=='live')
        snapshot_ts=datetime.fromisoformat(snapshot_meta['finished_utc']).timestamp()
        active_intervals=[]
        run_start=None
        for a in sorted(load('demo_activity'),key=lambda r:r['ts']):
            if a['bot']!='system':
                continue
            if a['kind'] in ('population_started','portfolio_started'):
                if run_start is None:
                    run_start=a['ts']
            elif a['kind']=='controls' and parse(a['details']).get('enabled') is False and run_start is not None:
                active_intervals.append((run_start,a['ts']))
                run_start=None
        if run_start is not None:
            active_intervals.append((run_start,datetime.fromisoformat(manifests['summary']['captured_utc']).timestamp()))
        last_fill = {}
        for f in fills:
            last_fill[f['order_id']] = f['id']
        closers = {last_fill[r['exit_order']]: r for r in rewards.values() if r['exit_order'] is not None}
        review_rows = load('demo_strategy_reviews')
        reviews = defaultdict(list)
        for review in review_rows:
            reviews[review['bot']].append(review)
        def attribution(order):
            decision = ds.get(order.get('decision_id'), {})
            result = parse(decision.get('result'))
            seed=ds.get(result.get('advisor_seed'),{})
            if seed and seed['bot']!=order['bot']:
                raise ValueError('Advisor seed belongs to another bot')
            seed_result=parse(seed.get('result'))
            recorded_model=result.get('model')
            model_source='entry_decision'
            if not recorded_model or recorded_model=='legacy-unrecorded':
                recorded_model=seed_result.get('model','legacy-unrecorded')
                model_source='linked_advisor_seed' if recorded_model!='legacy-unrecorded' else 'legacy-unrecorded'
            action = next((a for a in result.get('actions', []) if a.get('symbol') == order['symbol']), {})
            strategy = result.get('strategy') or result.get('policy') or {}
            kind = 'exploration' if 'exploration' in order['reason'].lower() else 'signal' if 'strategy signal' in order['reason'].lower() else 'advisor' if decision.get('source') == 'advisor' else 'other'
            inp = parse(decision.get('input_json'))
            market = next((a for a in inp.get('markets', []) if a['symbol'] == order['symbol']), {})
            fingerprint = hashlib.sha256(json.dumps(strategy, sort_keys=True).encode()).hexdigest()[:14]
            return dict(entry_style=strategy.get('style', 'original_point_policy' if ledger == 'market' else 'unknown'),
                        model=recorded_model, model_source=model_source,
                        provider=result.get('provider') or seed_result.get('provider','legacy-unrecorded'),
                        entry_kind=kind, source=decision.get('source', 'none'),
                        strategy=strategy, strategy_id=fingerprint, advisor_seed=result.get('advisor_seed'),
                        regime=result.get('regime', 'unknown'), features=market.get('features', {}),
                        action_exploration=action.get('exploration'), decision_id=order.get('decision_id'))
        active, episodes = {}, []
        def finish(ep, reward):
            ep['closed'] = True
            ep['closed_ts'] = reward['closed']
            ep['net_usd'] = ep['sell_usd'] - ep['sell_fees'] - ep['buy_usd'] - ep['buy_fees']
            ep['economic_net_usd'] = ep['net_usd']
            ep['remaining_qty'] = ep['remaining_cost'] = 0.
            ep['points'] = reward['points']
            error = abs(ep['net_usd'] - reward['net_usd'])
            if error > 1e-6:
                raise ValueError(f'Closed reconciliation {ledger}/{ep["episode"]}: {error}')
            ep['reward_error_usd'] = error
            episodes.append(ep)
        events = [(f['ts'], 0, f['id'], f) for f in fills] + [(d['ts'], 1, d['episode'], d) for d in dust]
        for _, event_type, _, r in sorted(events, key=lambda e: e[:3]):
            key = (r['bot'], r['symbol'])
            if event_type:
                ep = active.pop(key)
                if ep['episode'] != r['episode']:
                    raise ValueError('Dust episode mismatch')
                ep['dust_cost_usd'] = r['cost']
                finish(ep, rewards[r['episode']])
                continue
            order = orders[r['order_id']]
            if r['side'] == 'buy':
                attr = attribution(order)
                if key not in active:
                    ep = dict(ledger=ledger, bot=r['bot'], symbol=r['symbol'], episode=r['order_id'],
                              entry_ts=r['ts'], entry_utc=utc(r['ts']), entry_hour=utc(r['ts'])[:13],
                              entry_date=utc(r['ts'])[:10], buy_usd=0., sell_usd=0., buy_fees=0., sell_fees=0.,
                              original_fees=0., buy_qty=0., sell_qty=0., remaining_qty=0., remaining_cost=0.,
                              realized_parts=0., fills=0, buy_orders=[], sell_orders=[],
                              buy_strategy_ids=[], buy_styles=[], buy_kinds=[], buy_models=[],
                              entry_fee_phase='before_restatement' if fee_time and r['ts'] < fee_time else 'after_restatement',
                              entry_order_id=order['id'], dust_cost_usd=0., closed=False, **attr)
                    active[key] = ep
                ep = active[key]
                ep['buy_usd'] += r['usd_total']
                ep['buy_fees'] += r['fee']
                ep['buy_qty'] += r['qty']
                ep['remaining_qty'] += r['qty']
                ep['remaining_cost'] += r['usd_total'] + r['fee']
                for field, value in [('buy_orders', order['id']), ('buy_strategy_ids', attr['strategy_id']),
                                     ('buy_styles', attr['entry_style']), ('buy_kinds', attr['entry_kind']), ('buy_models', attr['model'])]:
                    if value not in ep[field]:
                        ep[field].append(value)
            else:
                ep = active[key]
                ep['sell_usd'] += r['usd_total']
                ep['sell_fees'] += r['fee']
                ep['sell_qty'] += r['qty']
                allocated = ep['remaining_cost'] * min(1, r['qty'] / ep['remaining_qty'])
                ep['remaining_cost'] -= allocated
                ep['remaining_qty'] -= r['qty']
                ep['realized_parts'] += r['usd_total'] - r['fee'] - allocated
                if order['id'] not in ep['sell_orders']:
                    ep['sell_orders'].append(order['id'])
                ep['last_sell_ts'] = r['ts']
                ep['last_exit_reason'] = order['reason']
            ep['fills'] += 1
            ep['original_fees'] += fee_audit.get(r['id'], {}).get('fee', r['fee'])
            all_trades.append(dict(ledger=ledger, episode=ep['episode'], **{k:v for k,v in r.items() if k != 'evidence'}))
            if r['side'] == 'sell' and r['id'] in closers:
                finish(active.pop(key), closers[r['id']])
        for key, ep in active.items():
            p = positions[key]
            for field, actual in [('remaining_qty', p['qty']), ('remaining_cost', p['cost']), ('realized_parts', p['realized_parts'])]:
                if not math.isclose(ep[field], actual, rel_tol=1e-9, abs_tol=1e-6):
                    raise ValueError(f'Position reconciliation {ledger}/{key}/{field}')
            mark = marks.get(ep['symbol'])
            if not mark:
                raise ValueError('Missing mark; cannot claim economic net')
            ep['mark_ts'] = mark['asof']
            ep['mark_source'] = mark['source']
            ep['mark_age_at_snapshot_seconds'] = snapshot_ts - mark['asof']
            ep['mark_gross_usd'] = p['qty'] * mark['bid'] * mark['fx_usd']
            ep['estimated_exit_fee_usd'] = ep['mark_gross_usd'] * cfg['fee_rate']
            ep['liquidation_mark_usd'] = ep['mark_gross_usd'] - ep['estimated_exit_fee_usd']
            ep['economic_net_usd'] = ep['sell_usd'] - ep['sell_fees'] - ep['buy_usd'] - ep['buy_fees'] + ep['liquidation_mark_usd']
            ep['unrealized_on_remaining_cost_usd'] = ep['liquidation_mark_usd'] - ep['remaining_cost']
            episodes.append(ep)
        for ep in episodes:
            ep['gross_usd'] = ep['sell_usd'] - ep['buy_usd']
            ep['original_fee_path_net_usd'] = ep['gross_usd'] - ep['original_fees'] if ep['closed'] else None
            ep['net_return_pct'] = 100 * ep['net_usd'] / (ep['buy_usd'] + ep['buy_fees']) if ep['closed'] else None
            ep['hold_seconds'] = ep.get('closed_ts', 0) - ep['entry_ts'] if ep['closed'] else None
            ep['time_to_last_sell_seconds'] = ep.get('last_sell_ts', ep['entry_ts']) - ep['entry_ts']
            ep['mixed_buy_strategy'] = len(ep['buy_strategy_ids']) > 1
            ep['mixed_buy_style'] = len(ep['buy_styles']) > 1
            ep['mixed_buy_model'] = len(ep['buy_models']) > 1
            ep['added_to_position'] = len(ep['buy_orders']) > 1
            ep['all_buys_exploration'] = ep['buy_kinds']==['exploration']
            ep['all_buys_signal'] = ep['buy_kinds']==['signal']
            ep['threshold_pct'] = ep['strategy'].get('threshold_pct')
            ep['planned_hold_seconds'] = ep['strategy'].get('hold_seconds')
            ep['allocation_pct'] = ep['strategy'].get('allocation_pct')
            ep['add_to_positions'] = ep['strategy'].get('add_to_positions')
            ep['strategy_revisions_during_episode'] = sum(ep['entry_ts'] < r['ts'] < ep.get('closed_ts', float('inf')) for r in reviews[ep['bot']])
            ep['exit_style'] = ep['entry_style']
            if ep.get('last_sell_ts'):
                preceding = [r for r in reviews[ep['bot']] if r['ts'] <= ep['last_sell_ts']]
                if preceding:
                    d = ds.get(preceding[-1]['decision_id'], {})
                    ep['exit_style'] = parse(d.get('result')).get('strategy', {}).get('style', ep['entry_style'])
            ep['exit_style_changed'] = ep['exit_style'] != ep['entry_style']
            ep['duration_bucket'] = 'open' if not ep['closed'] else '<5m' if ep['hold_seconds'] < 300 else '5-15m' if ep['hold_seconds'] < 900 else '15-30m' if ep['hold_seconds'] < 1800 else '30-60m' if ep['hold_seconds'] < 3600 else '>=60m'
            ep['signal_ready'] = ep['features'].get('ready')
            if ledger=='population':
                end=ep.get('closed_ts',datetime.fromisoformat(manifests['summary']['captured_utc']).timestamp())
                ep['active_hold_seconds']=sum(max(0,min(end,b)-max(ep['entry_ts'],a)) for a,b in active_intervals)
                ep['paused_hold_seconds']=max(0,end-ep['entry_ts']-ep['active_hold_seconds'])
                ep['crossed_pause']=ep['paused_hold_seconds']>1
                ep['entry_run']=next((i+1 for i,(a,b) in enumerate(active_intervals) if a<=ep['entry_ts']<=b),'unknown')
        if len([r for r in episodes if r['closed']]) != len(rewards) or set(active) != set(positions):
            raise ValueError('Episode set reconciliation')
        if len({r['episode'] for r in episodes}) != len(episodes):
            raise ValueError('Duplicate episode')
        actual_equity = sum(w['cash'] for w in wallets) + sum(r['liquidation_mark_usd'] for r in episodes if not r['closed'])
        reconstructed_net = sum(r['economic_net_usd'] for r in episodes)
        allocated = sum(w['initial'] for w in wallets)
        error = reconstructed_net - (actual_equity - allocated)
        if abs(error) > 1e-6:
            raise ValueError(f'Wallet equity reconciliation {ledger}: {error}')
        verifications.append(dict(ledger=ledger, closed_episodes=len(rewards), open_episodes=len(active),
                                  equity_error_usd=error, max_reward_error_usd=max(r['reward_error_usd'] for r in episodes if r['closed']), passed=True))
        policies = load('demo_policy')
        learning = load('demo_learning')
        diagnostics[ledger] = dict(first_fill_utc=utc(min(f['ts'] for f in fills)), last_fill_utc=utc(max(f['ts'] for f in fills)),
            decision_states={str(k):v for k,v in Counter((d['source'],d['state']) for d in ds.values()).items()},
            order_states={str(k):v for k,v in Counter((o['side'],o['state']) for o in orders.values()).items()},
            execution_notional_usd=sum(f['usd_total'] for f in fills), paid_fees_usd=sum(f['fee'] for f in fills),
            original_recorded_paid_fees_usd=sum(fee_audit.get(f['id'], {}).get('fee', f['fee']) for f in fills),
            open_mark_estimated_exit_fees_usd=sum(r.get('estimated_exit_fee_usd',0) for r in episodes),
            marked_equity_allocated_usd=actual_equity, allocated_initial_usd=allocated, marked_net_usd=actual_equity-allocated,
            remaining_unrealized_usd=sum(r.get('unrealized_on_remaining_cost_usd',0) for r in episodes),
            realized_parts_still_open_usd=sum(r['realized_parts'] for r in episodes if not r['closed']),
            policy_contexts=len(policies), context_visits=dict(Counter(r['visits'] for r in policies)),
            negative_q_contexts=sum(r['q']<0 for r in policies), positive_q_contexts=sum(r['q']>0 for r in policies),
            positive_q_min3visits=sum(r['q']>0 and r['visits']>=3 for r in policies),
            q_average=statistics.mean(r['q'] for r in policies) if policies else None,
            reward_updates=len(learning), cfg=cfg,
            stale_open_marks=sum(r.get('mark_age_at_snapshot_seconds',0)>20 for r in episodes if not r['closed']),
            max_open_mark_age_seconds=max(r.get('mark_age_at_snapshot_seconds',0) for r in episodes),
            buy_order_kinds=dict(Counter(attribution(o)['entry_kind'] for o in orders.values() if o['side']=='buy')),
            active_intervals_utc=[dict(start=utc(a),end=utc(b),seconds=b-a) for a,b in active_intervals],
            ledger_snapshot_utc=snapshot_meta['finished_utc'],
            total_active_seconds=sum(b-a for a,b in active_intervals),
            bot_rows=[{k:v for k,v in b.items() if k in ('bot','model','provider','score','score_reason','state')} for b in current_bots.values()])
        for o in orders.values():
            if o['side']=='buy':
                attr=attribution(o)
                all_orders.append({'ledger':ledger, **o, **attr})
        all_episodes.extend(episodes)
    pop = [r for r in all_episodes if r['ledger']=='population']
    closed_pop = sorted([r for r in pop if r['closed']], key=lambda r:r['entry_ts'])
    cutoffs = [closed_pop[len(closed_pop)//3]['entry_ts'], closed_pop[2*len(closed_pop)//3]['entry_ts']]
    for ep in all_episodes:
        ep['entry_third']='early' if ep['entry_ts']<cutoffs[0] else 'middle' if ep['entry_ts']<cutoffs[1] else 'late'
    tables = {
        'by-ledger': grouped(all_episodes,['ledger']),
        'by-entry-style':grouped(pop,['entry_style']),
        'by-entry-style-and-kind':grouped(pop,['entry_style','entry_kind']),
        'by-entry-kind':grouped(pop,['entry_kind']),
        'by-bot':grouped(all_episodes,['ledger','bot']),
        'by-entry-model':grouped(pop,['model']),
        'by-entry-model-and-style':grouped(pop,['model','entry_style']),
        'by-entry-strategy':grouped(pop,['strategy_id','entry_style']),
        'by-entry-revision':grouped(pop,['bot','advisor_seed','strategy_id','entry_style','model']),
        'by-symbol':grouped(pop,['symbol']),
        'by-style-symbol':grouped(pop,['entry_style','symbol']),
        'by-style-kind-symbol':grouped(pop,['entry_style','entry_kind','symbol']),
        'by-entry-hour':grouped(pop,['entry_hour']),
        'by-entry-third':grouped(pop,['entry_third']),
        'by-entry-run':grouped(pop,['entry_run']),
        'by-pause-crossing':grouped(pop,['crossed_pause']),
        'by-style-and-pause-crossing':grouped(pop,['entry_style','crossed_pause']),
        'by-style-and-third':grouped(pop,['entry_style','entry_third']),
        'by-style-kind-and-third':grouped(pop,['entry_style','entry_kind','entry_third']),
        'by-entry-fee-phase':grouped(pop,['entry_fee_phase']),
        'by-style-fee-phase':grouped(pop,['entry_style','entry_fee_phase']),
        'by-additions':grouped(pop,['added_to_position']),
        'by-allocation':grouped(pop,['allocation_pct']),
        'by-duration':grouped(pop,['duration_bucket']),
        'by-planned-hold':grouped(pop,['planned_hold_seconds']),
        'by-threshold':grouped(pop,['threshold_pct']),
        'pure-buy-strategy-by-style':grouped([r for r in pop if not r['mixed_buy_strategy']],['entry_style']),
        'pure-all-buys-by-kind':grouped([r for r in pop if len(r['buy_kinds'])==1],['entry_kind']),
        'pure-style-same-exit-by-style':grouped([r for r in pop if not r['mixed_buy_style'] and not r['exit_style_changed']],['entry_style']),
    }
    tables['no-pause-by-exact-strategy']=grouped([r for r in pop if not r['crossed_pause']],['strategy_id','entry_style'])
    for name, table in tables.items():
        table.sort(key=lambda r:r['closed_net_usd'],reverse=True)
        csvout(output/(name+'.csv'),table)
    strategies={r['strategy_id']:r['strategy'] for r in all_episodes}
    dump(output/'strategy-definitions.json',strategies)
    dump(output/'episodes.json',all_episodes)
    csvout(output/'episodes.csv',all_episodes)
    csvout(output/'entry-orders.csv',all_orders)
    csvout(output/'episode-fills.csv',all_trades)
    revisions=[json.loads(line) for line in (archive/'derived/strategy-revisions.jsonl').open()]
    revision_diag=dict(accepted=len(revisions),with_changes=sum(r['changed'] and not r['initial_saved_revision'] for r in revisions),
                       parameter_change_counts=dict(Counter(k for r in revisions if not r['initial_saved_revision'] for k in r['changes'])),
                       positive_revisions=sum(r['closed_net_usd']>1e-6 for r in tables['by-entry-revision'] if r['episodes']),
                       revisions_with_closed_samples=sum(bool(r['episodes']) for r in tables['by-entry-revision']),
                       positive_exact_strategies=sum(r['closed_net_usd']>1e-6 for r in tables['by-entry-strategy'] if r['episodes']),
                       exact_strategies_with_closed_samples=sum(bool(r['episodes']) for r in tables['by-entry-strategy']),
                       mixed_buy_strategy_closed=sum(r['mixed_buy_strategy'] for r in closed_pop),
                       mixed_buy_style_closed=sum(r['mixed_buy_style'] for r in closed_pop),
                       mixed_buy_model_closed=sum(r['mixed_buy_model'] for r in closed_pop),
                       exit_style_changed_closed=sum(r['exit_style_changed'] for r in closed_pop),
                       any_revisions_while_open=sum(r['strategy_revisions_during_episode']>0 for r in closed_pop))
    revision_diag['model_attribution_sources']=dict(Counter(r['model_source'] for r in closed_pop))
    revision_diag['profitable_exact_no_pause']=sum(
        summarise([e for e in closed_pop if e['strategy_id']==r['strategy_id'] and not e['crossed_pause']])['closed_net_usd']>1e-6
        for r in tables['by-entry-strategy'])
    result=dict(archive=str(archive),snapshot_utc=manifests['summary']['captured_utc'],
                verified_input_files=verified_inputs,
                entry_third_cutoffs_utc=[utc(t) for t in cutoffs],verification=verifications,
                diagnostics=diagnostics,revision_diagnostics=revision_diag,tables=tables,
                overall=summarise(all_episodes),population=summarise(pop))
    dump(output/'analysis.json',result)
    print(json.dumps({k:result[k] for k in ['snapshot_utc','verification','revision_diagnostics','overall','population']},indent=2))
    print('Output:',output)
    return result


if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    archive=args.archive or Path(json.loads((ROOT/'data/learning-archives/latest.json').read_text())['directory'])
    output=args.output or ROOT/'data/strategy-analysis'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    analyse(archive.resolve(),output.resolve())
