"""Durable virtual strategy runs. Session rollover never silently replenishes cash.

Call mutation helpers inside the engine's SQLite transaction (BEGIN IMMEDIATE for
concurrent admission/funding). This module never opens the production database,
commits its caller's transaction, runs an advisor, or changes the original paper
account. Monetary session status is owner/evaluator data, not advisor input.
"""
import json
import math
import time
from contextlib import contextmanager

from demo_policy import validate_review

EPSILON = 1e-8
OPEN_STATES = ('active', 'awaiting_review', 'ready_for_virtual_funding')


def _one(c, sql, args=()):
    cursor = c.execute(sql, args)
    row = cursor.fetchone()
    return dict(zip((column[0] for column in cursor.description), row)) if row is not None else None


def _all(c, sql, args=()):
    cursor = c.execute(sql, args)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Expected finite ' + name)
    return float(value)


def _wallet(c, bot):
    row = _one(c, 'SELECT * FROM demo_wallets WHERE bot=?', (bot,))
    if not row:
        raise ValueError('Unknown simulation bot')
    return row


@contextmanager
def _atomic(c):
    # SAVEPOINT works both inside the engine transaction and with a standalone
    # test connection, and keeps failed funding/review writes all-or-nothing.
    name = 'decklab_session_change'
    c.execute('SAVEPOINT ' + name)
    try:
        yield
    except Exception:
        c.execute('ROLLBACK TO ' + name)
        c.execute('RELEASE ' + name)
        raise
    else:
        c.execute('RELEASE ' + name)


def _next_ids(c, bot):
    return {
        'start_order_id': (_one(c, 'SELECT MAX(id) AS n FROM demo_orders')['n'] or 0) + 1,
        'start_decision_id': (_one(c, 'SELECT MAX(id) AS n FROM demo_decisions')['n'] or 0) + 1,
        'start_learning_id': (_one(c, 'SELECT MAX(id) AS n FROM demo_learning')['n'] or 0) + 1,
    }


def init(c):
    statements = [
        '''CREATE TABLE IF NOT EXISTS demo_run_sessions(
        id INTEGER PRIMARY KEY,bot TEXT NOT NULL,session_number INTEGER NOT NULL,
        state TEXT NOT NULL,created REAL NOT NULL,closed REAL,parent_session_id INTEGER,
        allocated_usd REAL NOT NULL,funded_usd REAL NOT NULL DEFAULT 0,
        opening_cash REAL NOT NULL DEFAULT 0,opening_equity REAL NOT NULL DEFAULT 0,
        closing_cash REAL,closing_equity REAL,start_order_id INTEGER NOT NULL,
        end_order_id INTEGER,start_decision_id INTEGER NOT NULL,end_decision_id INTEGER,
        start_learning_id INTEGER NOT NULL,end_learning_id INTEGER,
        review_decision_id INTEGER,parameters TEXT NOT NULL DEFAULT '{}',reason TEXT NOT NULL,
        UNIQUE(bot,session_number))''',
        '''CREATE UNIQUE INDEX IF NOT EXISTS demo_run_current ON demo_run_sessions(bot)
        WHERE state IN ('active','awaiting_review','ready_for_virtual_funding')''',
        '''CREATE TABLE IF NOT EXISTS demo_run_reviews(
        id INTEGER PRIMARY KEY,session_id INTEGER NOT NULL,bot TEXT NOT NULL,
        decision_id INTEGER NOT NULL UNIQUE,ts REAL NOT NULL,parameters TEXT NOT NULL,
        reason TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS demo_run_funding(
        id INTEGER PRIMARY KEY,session_id INTEGER NOT NULL UNIQUE,bot TEXT NOT NULL,
        ts REAL NOT NULL,amount REAL NOT NULL,request_key TEXT NOT NULL UNIQUE,
        ledger_ref TEXT NOT NULL UNIQUE)''',
        '''CREATE TABLE IF NOT EXISTS demo_run_events(
        id INTEGER PRIMARY KEY,session_id INTEGER NOT NULL,bot TEXT NOT NULL,
        ts REAL NOT NULL,kind TEXT NOT NULL,details TEXT NOT NULL)''',
    ]
    for statement in statements:
        c.execute(statement)
    for wallet in _all(c, 'SELECT * FROM demo_wallets ORDER BY bot'):
        if current(c, wallet['bot']):
            continue
        # Import the already-funded wallet as run 1 without touching its money
        # or rewriting any historical order, reward, fill or learning row.
        starts = {
            'start_order_id': 1,
            'start_decision_id': 1,
            'start_learning_id': 1,
        }
        cursor = c.execute('''INSERT INTO demo_run_sessions(
            bot,session_number,state,created,allocated_usd,funded_usd,
            opening_cash,opening_equity,start_order_id,start_decision_id,
            start_learning_id,reason) VALUES(?,1,'active',?,?,?,?,?,?,?,?,?)''',
            (wallet['bot'], wallet['created'], wallet['initial'], wallet['initial'],
             wallet['initial'], wallet['initial'], starts['start_order_id'],
             starts['start_decision_id'], starts['start_learning_id'],
             'Original funded virtual wallet; existing history preserved.'))
        _event(c, cursor.lastrowid, wallet['bot'], 'original_session_imported',
               {'funded_usd': wallet['initial'], 'new_cash_added': 0}, wallet['created'])


def current(c, bot):
    return _one(c, 'SELECT * FROM demo_run_sessions WHERE bot=? ORDER BY session_number DESC LIMIT 1', (bot,))


def _event(c, session_id, bot, kind, details, now):
    c.execute('INSERT INTO demo_run_events(session_id,bot,ts,kind,details) VALUES(?,?,?,?,?)',
              (session_id, bot, now, kind, json.dumps(details, allow_nan=False, sort_keys=True)))


def can_trade(c, bot):
    session = current(c, bot)
    return bool(session and session['state'] == 'active' and session['funded_usd'] > 0)


def check_depletion(c, bot, equity, cash=None, executable_holdings=None, now=None):
    """Retire a genuinely exhausted run and open one unfunded research successor.

    A fully-invested bot is not depleted merely because cash is zero. Unknown
    holdings are treated conservatively as still held; only the evaluator may
    explicitly state that none are executable. No dust, stale mark or provider
    error is silently converted to a new deposit.
    """
    equity = _number(equity, 'equity')
    now = time.time() if now is None else _number(now, 'time')
    wallet = _wallet(c, bot)
    cash = wallet['cash'] if cash is None else _number(cash, 'cash')
    if executable_holdings is not None and not isinstance(executable_holdings, bool):
        raise ValueError('Expected executable_holdings boolean or None')
    if executable_holdings is None:
        executable_holdings = bool(_one(c, 'SELECT 1 AS held FROM demo_positions WHERE bot=? AND qty>0 LIMIT 1', (bot,)))
    with _atomic(c):
        session = current(c, bot)
        if not session:
            raise ValueError('Simulation sessions are not initialized')
        if session['state'] != 'active':
            return {'depleted': False, 'transitioned': False, 'session': session}
        depleted = equity <= EPSILON or (cash <= EPSILON and not executable_holdings)
        if not depleted:
            return {'depleted': False, 'transitioned': False, 'session': session}
        reason = 'Virtual allocation exhausted; losing strategy retired. Replacement requires a real advisor review and separate explicit virtual funding.'
        c.execute('''UPDATE demo_run_sessions SET state='depleted',closed=?,
            closing_cash=?,closing_equity=?,end_order_id=?,end_decision_id=?,
            end_learning_id=?,reason=? WHERE id=? AND state='active' ''',
            (now, cash, equity,
             _one(c, 'SELECT MAX(id) AS n FROM demo_orders')['n'] or 0,
             _one(c, 'SELECT MAX(id) AS n FROM demo_decisions')['n'] or 0,
             _one(c, 'SELECT MAX(id) AS n FROM demo_learning')['n'] or 0,
             reason, session['id']))
        c.execute('''UPDATE demo_orders SET state='cancelled',finished=?,
            reason=COALESCE(reason,'')||' · depleted strategy session retired'
            WHERE bot=? AND side='buy' AND state IN ('queued','partial','awaiting_data')''', (now, bot))
        _event(c, session['id'], bot, 'strategy_depleted',
               {'equity_usd': equity, 'cash_usd': cash, 'replacement_funding_added': 0}, now)
        starts = _next_ids(c, bot)
        next_number = session['session_number'] + 1
        cursor = c.execute('''INSERT INTO demo_run_sessions(
            bot,session_number,state,created,parent_session_id,allocated_usd,
            funded_usd,opening_cash,opening_equity,start_order_id,start_decision_id,
            start_learning_id,reason) VALUES(?,?,'awaiting_review',?,?,?,0,0,0,?,?,?,?)''',
            (bot, next_number, now, session['id'], session['allocated_usd'],
             starts['start_order_id'], starts['start_decision_id'], starts['start_learning_id'],
             'Unfunded replacement strategy session awaiting an actual advisor review.'))
        _event(c, cursor.lastrowid, bot, 'replacement_session_created',
               {'previous_session_id': session['id'], 'funded_usd': 0, 'requires_actual_review': True}, now)
        return {'depleted': True, 'transitioned': True, 'retired_session_id': session['id'],
                'session': current(c, bot)}


def attach_review(c, bot, decision_id, parameters, reason, now=None):
    """Attach only the exact policy/summary from a completed genuine advisor job."""
    now = time.time() if now is None else _number(now, 'time')
    expected = validate_review(parameters)
    with _atomic(c):
        session = current(c, bot)
        if not session or session['state'] not in OPEN_STATES:
            raise ValueError('No current strategy session can receive a review')
        decision = _one(c, 'SELECT * FROM demo_decisions WHERE id=?', (decision_id,))
        if not decision or decision['bot'] != bot or decision['state'] != 'completed' or decision.get('source') != 'advisor':
            raise ValueError('Replacement requires an actual completed advisor review')
        if decision['created'] < session['created']:
            raise ValueError('Review predates the new strategy session')
        try:
            result = json.loads(decision['result'])
            actual = validate_review(result['policy'])
        except (ValueError, TypeError, KeyError):
            raise ValueError('Advisor did not provide a valid strategy policy') from None
        if expected != actual or reason != result.get('summary'):
            raise ValueError('Review parameters/reason must match the actual advisor result')
        prior = _one(c, 'SELECT * FROM demo_run_reviews WHERE decision_id=?', (decision_id,))
        if prior:
            if prior['session_id'] != session['id']:
                raise ValueError('Advisor review already belongs to a different session')
            return current(c, bot)
        c.execute('INSERT INTO demo_run_reviews(session_id,bot,decision_id,ts,parameters,reason) VALUES(?,?,?,?,?,?)',
                  (session['id'], bot, decision_id, now, json.dumps(actual, sort_keys=True), reason))
        state = 'ready_for_virtual_funding' if session['state'] == 'awaiting_review' else session['state']
        c.execute('UPDATE demo_run_sessions SET state=?,review_decision_id=?,parameters=?,reason=? WHERE id=?',
                  (state, decision_id, json.dumps(actual, sort_keys=True), reason, session['id']))
        _event(c, session['id'], bot, 'actual_advisor_review_attached',
               {'decision_id': decision_id, 'state': state, 'new_cash_added': 0}, now)
        return current(c, bot)


def fund_session(c, bot, session_id, amount, request_key, now=None):
    """Explicit new-run capital deposit; never called by depletion/review helpers.

    The existing wallet becomes a cumulative-capital ledger: cash and initial
    both increase by the explicitly supplied new virtual allocation. Thus old
    losses remain in lifetime P&L, while this session separately records its new
    funded amount. This is not a reset or a claimed trading profit.
    """
    amount = _number(amount, 'virtual funding amount')
    now = time.time() if now is None else _number(now, 'time')
    if amount <= 0 or not isinstance(request_key, str) or not 8 <= len(request_key) <= 120:
        raise ValueError('A positive amount and stable funding request key are required')
    with _atomic(c):
        previous = _one(c, 'SELECT * FROM demo_run_funding WHERE request_key=?', (request_key,))
        if previous:
            if previous['bot'] != bot or previous['session_id'] != session_id or previous['amount'] != amount:
                raise ValueError('Funding key belongs to a different request')
            return {'funded': False, 'reused': True, 'session': current(c, bot)}
        session = current(c, bot)
        if not session or session['id'] != session_id or session['state'] != 'ready_for_virtual_funding' or not session['review_decision_id']:
            raise ValueError('A replacement session with an actual advisor review is required')
        if amount > session['allocated_usd']:
            raise ValueError('Funding exceeds the separately recorded session allocation')
        wallet = _wallet(c, bot)
        if wallet['cash'] > EPSILON or _one(c, 'SELECT 1 AS held FROM demo_positions WHERE bot=? AND qty>0 LIMIT 1', (bot,)):
            raise ValueError('Previous session must be exhausted and positions settled before new funding')
        ledger_ref = 'strategy-session-funding-' + str(session_id)
        c.execute('INSERT INTO demo_cash_ledger(bot,ts,kind,amount,ref) VALUES(?,?,?,?,?)',
                  (bot, now, 'new session virtual funding', amount, ledger_ref))
        c.execute('UPDATE demo_wallets SET cash=cash+?,initial=initial+? WHERE bot=?', (amount, amount, bot))
        c.execute('INSERT INTO demo_run_funding(session_id,bot,ts,amount,request_key,ledger_ref) VALUES(?,?,?,?,?,?)',
                  (session_id, bot, now, amount, request_key, ledger_ref))
        c.execute('UPDATE demo_run_sessions SET state=\'active\',funded_usd=?,opening_cash=?,opening_equity=? WHERE id=?',
                  (amount, wallet['cash'] + amount, wallet['cash'] + amount, session_id))
        _event(c, session_id, bot, 'explicit_virtual_funding',
               {'amount_usd': amount, 'ledger_ref': ledger_ref, 'previous_losses_retained': True}, now)
        return {'funded': True, 'reused': False, 'session': current(c, bot)}


def status(c, bot=None):
    bots = [bot] if bot is not None else [w['bot'] for w in _all(c, 'SELECT bot FROM demo_wallets ORDER BY bot')]
    output = []
    for name in bots:
        wallet = _wallet(c, name)
        history = _all(c, 'SELECT * FROM demo_run_sessions WHERE bot=? ORDER BY session_number DESC', (name,))
        current_session = history[0] if history else None
        funding = _one(c, 'SELECT COALESCE(SUM(funded_usd),0) AS total FROM demo_run_sessions WHERE bot=?', (name,))['total']
        output.append({'bot': name, 'current': current_session, 'history': history,
                       'session_number': current_session['session_number'] if current_session else None,
                       'state': current_session['state'] if current_session else 'uninitialized',
                       'allocated_usd': current_session['allocated_usd'] if current_session else 0,
                       'funded_usd': current_session['funded_usd'] if current_session else 0,
                       'cumulative_funding_usd': funding, 'wallet_cumulative_initial_usd': wallet['initial'],
                       'can_trade': can_trade(c, name)})
    return output[0] if bot is not None else output
