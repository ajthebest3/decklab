#!/usr/bin/env python3
"""Read-only owner export of all retained DeckLab learning and strategy history.

No engine imports, model calls, orders, or production writes. Each live ledger is
copied with SQLite backup; older backups contribute deduplicated row versions.
The owner-only report includes evaluator results and must not be fed to bots.
"""
import argparse
import csv
import difflib
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ('demo_engine.py', 'demo_learning.py', 'demo_policy.py',
        'population_engine.py', 'population_controls.py', 'population_models.py',
        'fee_restatement.py', 'private_advisor.py', 'research_engine.py',
        'chat_engine.py', 'mirai_client.py', 'training/export_points.py',
        'training/collect_learning.py', 'server.py')
DOCS = ('AGENTS.md', 'SESSION_MEMORY.md', 'DEMO_PLAN.md', 'PLAN.md',
        'README.md', 'training/README.md')
# This allowlist excludes private authentication/signing/admin databases and files.
EXTRA = {'events', 'research_briefs', 'research_notes', 'jobs', 'chat_threads',
         'chat_messages', 'assets', 'quotes', 'history', 'candles', 'news',
         'instrument_facts', 'watchlist', 'orders', 'positions', 'settings'}
REDACT = re.compile(r'(?i)\bsk-[a-z0-9_-]{12,}\b|\b(?:Bearer\s+)[a-z0-9._~+/-]{20,}')


def utc(ts=None):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':'))


def parse(value):
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def clean(value):
    if isinstance(value, str):
        return REDACT.sub('[REDACTED CREDENTIAL]', value)
    if isinstance(value, dict):
        return {k: ('[REDACTED CREDENTIAL]' if k.lower() in
                    {'api_key', 'api_keys', 'authorization', 'access_token', 'refresh_token', 'passkey', 'password'}
                    else clean(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def write_lines(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w') as f:
        for row in rows:
            f.write(canonical(clean(row)) + '\n')


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            values = {k: canonical(clean(v)) if isinstance(v, (dict, list)) else clean(v) for k, v in row.items()}
            # Keep spreadsheets from interpreting model-generated text as formulas.
            writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v
                             for k, v in values.items()})


def connect(path):
    c = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    return c


def selected_tables(c, historical=False):
    all_tables = c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [r[0] for r in all_tables if r[0].startswith(('demo_', 'population_')) or r[0] in
            ({'research_briefs', 'research_notes', 'jobs', 'events', 'chat_threads', 'chat_messages', 'settings'}
             if historical else EXTRA)]


def table_rows(c, table):
    # Names come only from sqlite_master and the explicit allowlist above.
    return [dict(r) for r in c.execute('SELECT * FROM "' + table.replace('"', '""') + '" ORDER BY rowid')]


def snapshot(source, destination):
    begin = utc()
    with connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst, pages=512)
    return {'started_utc': begin, 'finished_utc': utc(),
            'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}


def model_for(decision):
    result = parse(decision.get('result')) or {}
    return {'provider': result.get('provider', 'legacy-unrecorded'),
            'model': result.get('model', 'legacy-unrecorded')}


def summarize(ledger, tables):
    decisions = {r['id']: r for r in tables.get('demo_decisions', [])}
    orders = {r['id']: r for r in tables.get('demo_orders', [])}
    agents = {r['bot']: r for r in tables.get('population_bots', [])}
    routes = {r['target']: parse(r['config']) for r in tables.get('population_ai', [])}
    names = sorted({r['bot'] for t, rows in tables.items() if t.startswith(('demo_', 'population_'))
                    for r in rows if r.get('bot') and r['bot'] != 'system'})
    revisions = []
    previous = {}
    for r in sorted(tables.get('demo_strategy_reviews', []), key=lambda x: (x['ts'], x['id'])):
        decision = decisions.get(r['decision_id'], {})
        result = parse(decision.get('result')) or {}
        parameters = result.get('strategy') or parse(r['parameters']) or {}
        before = previous.get(r['bot'])
        changes = {k: {'before': before.get(k) if before else None, 'after': parameters.get(k),
                       'before_known': before is not None and k in before}
                   for k in sorted(set(parameters) | set(before or {}))
                   if before is None or parameters.get(k) != before.get(k)}
        revisions.append(dict(ledger=ledger, bot=r['bot'], review_id=r['id'], decision_id=r['decision_id'],
                              ts=r['ts'], time_utc=utc(r['ts']), parameters=parameters, changes=changes,
                              initial_saved_revision=before is None, changed=bool(changes), reason=r['reason'],
                              **model_for(decision)))
        previous[r['bot']] = parameters
    feedback = []
    for review in tables.get('population_reviews', []):
        result = parse(review.get('result')) or {}
        for rating in result.get('ratings', []):
            feedback.append(dict(ledger=ledger, review_id=review['id'], ts=review['finished'] or review['created'],
                                 time_utc=utc(review['finished'] or review['created']),
                                 reviewer=result.get('advisor', {}), **rating))
    summaries = []
    for bot in names:
        learning = [r for r in tables.get('demo_learning', []) if r['bot'] == bot]
        rewards = [r for r in tables.get('demo_rewards', []) if r['bot'] == bot]
        ds = [r for r in decisions.values() if r['bot'] == bot]
        rs = [r for r in revisions if r['bot'] == bot]
        origin_models = Counter()
        for reward in rewards:
            order = orders.get(reward['episode'], {})
            model = model_for(decisions.get(order.get('decision_id'), {}))['model']
            origin_models[model] += 1
        summaries.append(dict(ledger=ledger, bot=bot, lineage=agents.get(bot, {}),
                              current_route=routes.get(bot, {}),
                              decisions=len(ds), decision_states=dict(Counter(r['state'] for r in ds)),
                              accepted_strategy_revisions=len(rs),
                              revisions_with_parameter_changes=sum(r['changed'] and not r['initial_saved_revision'] for r in rs),
                              first_strategy=rs[0]['parameters'] if rs else None,
                              latest_strategy=rs[-1]['parameters'] if rs else parse(agents.get(bot, {}).get('strategy')),
                              learning_updates=len(learning), closed_episodes=len(rewards),
                              points=sum(r['points'] for r in rewards), wins=sum(r['points'] == 1 for r in rewards),
                              losses=sum(r['points'] == -5 for r in rewards), breakeven=sum(r['points'] == 0 for r in rewards),
                              closed_net_usd=sum(r['net_usd'] for r in rewards),
                              episode_model_attribution=dict(origin_models),
                              reviewer_ratings=sum(r['bot'] == bot for r in feedback)))
    return summaries, revisions, feedback


def validate(tables, revisions):
    errors = []
    rewards = {r['episode']: r for r in tables.get('demo_rewards', [])}
    learning = tables.get('demo_learning', [])
    states = {}
    for row in sorted(learning, key=lambda r: r['id']):
        reward = rewards.get(row['episode'])
        if not reward or reward['points'] != row['points']:
            errors.append(f"Reward mismatch for learning {row['id']}")
        expected = row['old_q'] + row['alpha'] * (row['points'] - row['old_q'])
        if abs(row['new_q'] - expected) > 1e-9:
            errors.append(f"Q equation mismatch for learning {row['id']}")
        key = row['bot'], row['context']
        if abs(row['old_q'] - states.get(key, (0, 0))[0]) > 1e-9:
            errors.append(f"Q chain mismatch for learning {row['id']}")
        states[key] = row['new_q'], states.get(key, (0, 0))[1] + 1
    for row in tables.get('demo_policy', []):
        expected = states.get((row['bot'], row['context']), (0, 0))
        if abs(row['q'] - expected[0]) > 1e-9 or row['visits'] != expected[1]:
            errors.append('Current policy mismatch: ' + row['bot'] + '/' + row['context'])
    decisions = {r['id']: r for r in tables.get('demo_decisions', [])}
    for row in revisions:
        if decisions.get(row['decision_id'], {}).get('state') != 'completed':
            errors.append('Accepted revision without completed decision: ' + str(row['review_id']))
    return dict(learning_rows=len(learning), rewards=len(rewards),
                accepted_revisions=len(revisions), errors=errors, passed=not errors)


def render_report(output, summary, agents, revisions, ratings, learning, policies):
    fields = ('ledger', 'bot', 'closed_episodes', 'wins', 'losses', 'points', 'learning_updates',
              'accepted_strategy_revisions', 'revisions_with_parameter_changes')
    lines = ['# DeckLab — complete retained learning archive', '',
             'Captured: ' + summary['captured_utc'], '',
             'Contains both production ledgers, every retained agent/generation, all stored observations and advisor responses, '
             'strategy revisions, Q updates, reviewer feedback, controls, trades and evidence. Older backup row versions '
             'retain provenance. This is an owner analysis export; evaluator dollars are not bot training input.', '',
             '## Coverage', '',
             f"- {len(agents)} ledger/agent identities; {sum(a['learning_updates'] for a in agents)} terminal learning updates.",
             f"- {len(revisions)} accepted strategy revisions; {sum(a['revisions_with_parameter_changes'] for a in agents)} subsequent parameter-changing revisions.",
             f"- {len(ratings)} per-agent reviewer ratings; {summary['shared_lessons']} published shared lessons.",
             f"- {len(summary['sources'])} live/backup database sources. Each live ledger was captured consistently, sequentially.", '',
             '## Agents', '', '| ' + ' | '.join(fields) + ' |', '| ' + ' | '.join('---' for _ in fields) + ' |']
    lines += ['| ' + ' | '.join(str(a[k]) for k in fields) + ' |' for a in agents]
    lines += ['', '## How the algorithm changes', '',
              'Terminal learning uses Q_new = Q_old + 0.2 × (points − Q_old), with +1 / −5 / 0 on fully closed episodes. '
              'Saved Q-values influence entry admission, ranking, exploration and size. Advisors revise bounded strategy parameters; '
              'the reviewer scores strategies and may authorize lifecycle changes within owner controls. These records do not establish '
              'model-weight training, autonomous source-code rewriting or validated future profitability.', '',
              'The November 1 fee restatement replayed historical outcomes and Q values at the revised fee assumption. '
              'Current exports use that fee basis. Historical versions and demo_fee_audit preserve original values; do not add '
              'different historical versions together as new episodes.', '',
              '## Files', '',
              '- report.html: standalone searchable agent report with full revision and reviewer timelines.',
              '- current/: every allowlisted production table as JSONL, plus schema and capture metadata.',
              '- historical/: deduplicated complete row versions across all retained backups, with source IDs.',
              '- derived/: agent summary, exact before/after strategy changes, reviewer ratings, learning CSV and checks.',
              '- sources/: present algorithm source, available Git versions/diffs, backed-up source and project chronology.',
              '- manifest.json: file hashes and source inventory.', '',
              '## Limits', '',
              'Complete for records retained in the captured databases and discovered local backups. Unlogged internal reasoning, '
              'deleted data with no backup, unavailable intermediate source versions and remote model training history cannot be recovered. '
              'Initial saved strategy values do not establish what preceded them. Historical decisions lacking model metadata remain '
              'legacy-unrecorded. A bot name or current route must not relabel its earlier model assignments. Failed/cancelled/in-flight '
              'jobs remain included with their recorded states. Capture does not run new research or change runtime controls.', '',
              'Credential-shaped strings and explicit secret fields are redacted. Authentication/signing files and admin messages are excluded.']
    (output / 'README.md').write_text('\n'.join(lines) + '\n')
    payload = clean(dict(summary=summary, agents=agents, revisions=revisions, ratings=ratings,
                         learning=learning, policies=policies))
    encoded = canonical(payload).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DeckLab learning archive</title><style>
body{font:15px system-ui;background:#0d1420;color:#e4edf8;margin:0;padding:24px;max-width:1400px;margin:auto}h1,h2{color:#a9d8ff}p{line-height:1.6}.muted{color:#a5b5c7}input,select{font:inherit;padding:10px;background:#1c2a3b;color:#fff;border:1px solid #58728a;border-radius:7px;margin:4px;max-width:95%}table{border-collapse:collapse;width:100%;font-size:13px}td,th{text-align:left;padding:9px;border-bottom:1px solid #344457;vertical-align:top}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#172334;padding:12px;border-radius:8px}details{border-bottom:1px solid #344457;padding:12px 0}summary{cursor:pointer;line-height:1.7}.scroll{overflow:auto}.pill{display:inline-block;background:#1c3546;padding:7px;border-radius:7px;margin:4px}a{color:#9ad7ff}
</style><h1>DeckLab · retained learning archive</h1><p id="meta" class="muted"></p>
<p>Owner analysis: includes evaluator results. Terminal points and bounded strategy revisions are recorded learning; model weights were not retrained. Older fee-scenario versions remain in the archive.</p>
<div id="counts"></div><label>Agent <select id="agent"><option value="">All agents</option></select></label>
<label>Search <input id="search" type="search" placeholder="Model, parameter, reason, symbol…"></label>
<h2>Agent summaries</h2><div class="scroll"><table><thead><tr><th>Ledger / agent</th><th>Current route</th><th>Closed · wins / losses</th><th>Points</th><th>Q updates</th><th>Accepted revisions / changes</th></tr></thead><tbody id="agents"></tbody></table></div>
<h2>Accepted strategy timeline</h2><p class="muted">Each entry includes its accepted values, exact changes and the saved advisor explanation. Unchanged responses remain visible. The first saved revision has an unknown prior baseline.</p><div id="revisions"></div>
<h2>Reviewer feedback</h2><div id="ratings"></div>
<h2>Every terminal point update</h2><p class="muted">Recorded closed episodes, context, reward and exact old/new Q values. Search and agent filters apply to all sections.</p><div class="scroll"><table><thead><tr><th>UTC / agent</th><th>Episode · context</th><th>Points</th><th>Old Q → new Q</th></tr></thead><tbody id="learning"></tbody></table></div>
<h2>Current learned context values</h2><div class="scroll"><table><thead><tr><th>Ledger / agent</th><th>Context</th><th>Q</th><th>Updates</th></tr></thead><tbody id="policies"></tbody></table></div>
<h2>Coverage and evidence</h2><p>Raw observations, responses, failures, Q updates, outcomes, controls and execution evidence are in current/. Deduplicated backup versions are in historical/, with source IDs in manifest.json. Current source and available historical code are in sources/. No live setting was changed by this export.</p><p>Records never stored, deleted without a surviving backup, and providers’ internal model training cannot be recovered. Older model identities without recorded attribution remain legacy-unrecorded. Published strategy lessons: <span id="lessons"></span>.</p>
<script id="data" type="application/json">__DATA__</script><script>
const D=JSON.parse(document.getElementById('data').textContent), E=s=>document.getElementById(s), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
E('meta').textContent='Captured '+D.summary.captured_utc+' · UTC times · offline report';
E('counts').innerHTML=[D.agents.length+' agents',D.agents.reduce((a,b)=>a+b.learning_updates,0)+' Q updates',D.revisions.length+' accepted revisions',D.ratings.length+' reviewer ratings',D.summary.sources.length+' database sources'].map(s=>'<span class="pill">'+esc(s)+'</span>').join('');
for(const a of D.agents){const o=document.createElement('option');o.value=a.ledger+'/'+a.bot;o.textContent=o.value;E('agent').append(o)}
E('lessons').textContent=D.summary.shared_lessons;
function render(){const chosen=E('agent').value,q=E('search').value.toLowerCase(),match=r=>(!chosen||r.ledger+'/'+r.bot===chosen)&&(!q||JSON.stringify(r).toLowerCase().includes(q));
E('agents').innerHTML=D.agents.filter(match).map(a=>'<tr><td>'+esc(a.ledger+'/'+a.bot)+'</td><td>'+esc(JSON.stringify(a.current_route))+'</td><td>'+a.closed_episodes+' · '+a.wins+' / '+a.losses+'</td><td>'+a.points+'</td><td>'+a.learning_updates+'</td><td>'+a.accepted_strategy_revisions+' / '+a.revisions_with_parameter_changes+'</td></tr>').join('');
E('revisions').innerHTML=D.revisions.filter(match).map(r=>'<details><summary>'+esc(r.time_utc+' · '+r.ledger+'/'+r.bot+' · '+r.model+' · '+(r.initial_saved_revision?'First saved revision':r.changed?'Changed: '+Object.keys(r.changes).join(', '):'Parameters unchanged'))+'</summary><p>'+esc(r.reason)+'</p><pre>'+esc(JSON.stringify({decision_id:r.decision_id,changes:r.changes,accepted_parameters:r.parameters},null,2))+'</pre></details>').join('');
E('ratings').innerHTML=D.ratings.filter(match).map(r=>'<details><summary>'+esc(r.time_utc+' · '+r.bot+' · score '+r.score+' · '+r.action)+'</summary><pre>'+esc(JSON.stringify(r,null,2))+'</pre></details>').join('');
E('learning').innerHTML=D.learning.filter(match).map(r=>'<tr><td>'+esc(r.time_utc+' · '+r.ledger+'/'+r.bot)+'</td><td>'+esc(r.episode+' · '+r.context)+'</td><td>'+r.points+'</td><td>'+r.old_q+' → '+r.new_q+'</td></tr>').join('');
E('policies').innerHTML=D.policies.filter(match).map(r=>'<tr><td>'+esc(r.ledger+'/'+r.bot)+'</td><td>'+esc(r.context)+'</td><td>'+r.q+'</td><td>'+r.visits+'</td></tr>').join('')}
E('agent').addEventListener('change',render);E('search').addEventListener('input',render);render();
</script></html>'''.replace('__DATA__', encoded)
    (output / 'report.html').write_text(page)


def collect(output):
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    source_inventory, schemas, historical = [], {}, defaultdict(dict)
    current, agents, revisions, ratings, checks = {}, [], [], [], {}
    data = ROOT / 'data'
    sources = [(ledger, 'live', data / (ledger + '.db')) for ledger in ('market', 'population')]
    backups = sorted(p for p in data.rglob('*') if p.is_file() and
                     (p.suffix == '.sqlite' or p.name in ('market.db', 'population.db')) and
                     p not in (data / 'market.db', data / 'population.db') and output not in p.parents)
    sources += [('population' if 'population' in p.name else 'market', 'backup', p) for p in backups]
    with tempfile.TemporaryDirectory(prefix='decklab-learning-', dir=data) as temp:
        for index, (ledger, kind, path) in enumerate(sources):
            source_id = f's{index:03d}'
            meta = dict(id=source_id, ledger=ledger, kind=kind, path=str(path.relative_to(ROOT)))
            captured = path
            if kind == 'live':
                captured = Path(temp) / (ledger + '.db')
                meta.update(snapshot(path, captured))
            else:
                meta.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
            print('Reading', source_id, ledger, kind, flush=True)
            with connect(captured) as c:
                meta['integrity_check'] = c.execute('PRAGMA quick_check').fetchone()[0]
                if meta['integrity_check'] != 'ok':
                    raise ValueError('SQLite check failed: ' + str(path))
                schemas[source_id] = [dict(r) for r in c.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")]
                tables = {t: table_rows(c, t) for t in selected_tables(c, historical=kind == 'backup')}
            meta['counts'] = {t: len(rows) for t, rows in tables.items()}
            source_inventory.append(meta)
            if kind == 'live':
                current[ledger] = tables
                for t, rows in tables.items():
                    write_lines(output / 'current' / ledger / (t + '.jsonl'), rows)
                aa, rr, ff = summarize(ledger, tables)
                agents.extend(aa); revisions.extend(rr); ratings.extend(ff)
                checks[ledger] = validate(tables, rr)
            for table, rows in tables.items():
                if not (table.startswith(('demo_', 'population_')) or table in
                        {'research_briefs', 'research_notes', 'jobs', 'events', 'chat_threads', 'chat_messages', 'settings'}):
                    continue
                bucket = historical[ledger + '/' + table]
                for row in rows:
                    digest = hashlib.sha256(canonical(row).encode()).hexdigest()
                    if digest not in bucket:
                        bucket[digest] = {'row_sha256': digest, 'sources': [], 'row': row}
                    bucket[digest]['sources'].append(source_id)
    for key, variants in historical.items():
        write_lines(output / 'historical' / (key + '.jsonl'), variants.values())
    for path in (*CORE, *DOCS):
        p = ROOT / path
        if p.is_file():
            dest = output / 'sources' / 'current' / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(clean(p.read_text()))
    for folder in sorted(data.glob('pre-*')):
        if folder.is_dir():
            for p in folder.rglob('*'):
                if p.is_file() and (p.suffix == '.py' or p.name in ('demo.js', 'demo.css')):
                    dest = output / 'sources' / 'backups' / folder.name / p.relative_to(folder)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(clean(p.read_text()))
    prior_exports = [*data.glob('*training-points.jsonl'), *data.glob('pre-*/*training-points.jsonl')]
    for p in sorted(prior_exports):
        dest = output / 'sources' / 'prior-point-exports' / p.relative_to(data)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(clean(p.read_text()))
    run = lambda args: subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True, check=True).stdout
    log = run(['log', '--all', '--format=%H %aI %s', '--', *CORE])
    (output / 'sources' / 'git-history.txt').write_text(clean(log))
    (output / 'sources' / 'working-tree.patch').write_text(clean(run(['diff', 'HEAD', '--', *CORE])))
    for line in log.splitlines():
        commit = line.split()[0]
        for path in CORE:
            result = subprocess.run(['git', '-C', str(ROOT), 'show', commit + ':' + path], capture_output=True, text=True)
            if result.returncode == 0:
                dest = output / 'sources' / 'git' / commit / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(clean(result.stdout))
    before_sources = list((output / 'sources' / 'backups').rglob('*.py')) if (output / 'sources' / 'backups').exists() else []
    for before in before_sources:
        rel = before.relative_to(output / 'sources' / 'backups')
        after = output / 'sources' / 'current' / Path(*rel.parts[1:])
        if after.exists():
            diff = ''.join(difflib.unified_diff(before.read_text().splitlines(True), after.read_text().splitlines(True),
                                               fromfile=str(rel), tofile='current/' + '/'.join(rel.parts[1:])))
            dest = output / 'sources' / 'diffs' / (str(rel) + '.patch')
            dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text(diff)
    summary = dict(captured_utc=utc(), sources=source_inventory,
                   shared_lessons=sum(len(t.get('population_lessons', [])) for t in current.values()),
                   counts={ledger: {t: len(rows) for t, rows in tables.items()} for ledger, tables in current.items()},
                   historical_unique_versions={k: len(v) for k, v in historical.items()},
                   checks=checks,
                   runtime={ledger: {r['key']: parse(r['value']) for r in tables.get('demo_settings', [])
                                     if r['key'] in ('enabled', 'policy_enabled', 'entries_enabled', 'fee_rate')}
                            for ledger, tables in current.items()})
    write_json(output / 'derived' / 'summary.json', summary)
    write_json(output / 'derived' / 'agents.json', agents)
    write_json(output / 'derived' / 'verification.json', checks)
    write_json(output / 'current' / 'schemas.json', schemas)
    write_lines(output / 'derived' / 'strategy-revisions.jsonl', revisions)
    write_lines(output / 'derived' / 'reviewer-ratings.jsonl', ratings)
    write_csv(output / 'derived' / 'strategy-changes.csv', revisions,
              ('ledger', 'bot', 'review_id', 'decision_id', 'time_utc', 'provider', 'model', 'changed', 'parameters', 'changes', 'reason'))
    write_csv(output / 'derived' / 'agents.csv', agents,
              ('ledger', 'bot', 'closed_episodes', 'wins', 'losses', 'points', 'learning_updates',
               'accepted_strategy_revisions', 'revisions_with_parameter_changes', 'closed_net_usd', 'current_route'))
    all_learning = [dict(ledger=ledger, time_utc=utc(r['ts']), **r) for ledger, t in current.items() for r in t.get('demo_learning', [])]
    all_policies = [dict(ledger=ledger, **r) for ledger, t in current.items() for r in t.get('demo_policy', [])]
    received = []
    feedback_keys = ('point_feedback', 'lineage_point_feedback', 'provider_point_feedback', 'reviewer_score',
                     'shared_strategy_lessons', 'cross_model_point_feedback', 'policy_parameters', 'strategy',
                     'entry_protection', 'execution_assumptions', 'owner_limits')
    for ledger, tables in current.items():
        for row in tables.get('demo_decisions', []):
            observation = parse(row.get('input_json'))
            if isinstance(observation, dict):
                received.append(dict(ledger=ledger, bot=row['bot'], decision_id=row['id'],
                                     state=row['state'], context_ts=row['context_ts'], source=row['source'],
                                     feedback={k: observation[k] for k in feedback_keys if k in observation},
                                     interpretation='Saved model input; failed/cancelled jobs do not prove completed delivery'))
    write_lines(output / 'derived' / 'received-feedback.jsonl', received)
    write_csv(output / 'derived' / 'learning-updates.csv', all_learning,
              ('ledger', 'bot', 'id', 'episode', 'time_utc', 'context', 'points', 'old_q', 'new_q', 'alpha'))
    render_report(output, summary, agents, revisions, ratings, all_learning, all_policies)
    manifest = dict(summary=summary, files={})
    for p in sorted(output.rglob('*')):
        if p.is_file():
            os.chmod(p, 0o600)
            manifest['files'][str(p.relative_to(output))] = dict(bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
        elif p.is_dir():
            os.chmod(p, 0o700)
    write_json(output / 'manifest.json', manifest)
    os.chmod(output / 'manifest.json', 0o600)
    archive = output.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(output.rglob('*')):
            if p.is_file():
                z.write(p, arcname=output.name + '/' + str(p.relative_to(output)))
    os.chmod(archive, 0o600)
    print(json.dumps(dict(output=str(output), archive=str(archive), agents=len(agents), learning_updates=len(all_learning),
                          revisions=len(revisions), ratings=len(ratings), checks=checks), indent=2))
    if any(not v['passed'] for v in checks.values()):
        raise SystemExit('Export completed with data consistency findings; inspect verification.json')
    return output


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'data' / 'learning-archives' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    args = parser.parse_args()
    collect(args.output.resolve())
