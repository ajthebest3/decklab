"""DeckLab Phase1 foundation readiness snapshot.

Read-only view over persisted state. Owns a single connect_db() connection
opened with PRAGMA query_only=ON and always closed. No writes, no
subprocesses, no network, no model calls, no imports of server/init.
"""

from __future__ import annotations

import math
import os
import time
import hashlib
import json
import re
from pathlib import Path

CONTRACT_VERSION = "2.0"
PAUSE_MARKERS = ("owner-research-paused-until-asked", "owner-pause-until-tuesday")
QUOTES_LIMIT = 5000
CRYPTO_STALE = 120
OTHER_STALE = 300
FX_STALE = 3600
RECEIPT_STALE = 120
FUTURE_TOLERANCE = 5
BUILD_FINGERPRINT = hashlib.sha256(b''.join((Path(__file__).parent/name).read_bytes() for name in ('foundation.py','server.py','mirai_client.py','operations.py'))).hexdigest()


def _num(value):
    """Return a finite float or None. Never emits NaN/inf."""
    try:
        if value is None or isinstance(value, bool):
            return None
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _positive(value):
    out = _num(value)
    if out is None or out <= 0:
        return None
    return out


def _text(value, limit=200):
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if not value:
        return None
    return value[:limit]


def _rows(conn, sql, params=()):
    """Fetch rows; any failure (incl. missing table) -> None, no detail leak."""
    try:
        cur = conn.execute(sql, params)
    except Exception:
        return None
    try:
        return cur.fetchall()
    except Exception:
        return None
    finally:
        try:
            cur.close()
        except Exception:
            pass


def _field(row, name, index=None):
    try:
        if index is not None and not hasattr(row, "keys"):
            return row[index]
        return row[name]
    except Exception:
        return None


def _owner_marker(data_dir):
    if not data_dir:
        return None
    try:
        entries = set(os.listdir(data_dir))
    except Exception:
        return None
    for name in PAUSE_MARKERS:
        if name in entries:
            return name
    return None


def _quotes(conn, now):
    rows = _rows(
        conn,
        "SELECT q.symbol, q.price, q.asof, q.fetched, q.source, a.kind FROM quotes q "
        "LEFT JOIN assets a ON a.symbol=q.symbol WHERE q.symbol IS NOT NULL ORDER BY q.symbol LIMIT ?",
        (QUOTES_LIMIT + 1,),
    )
    if rows is None:
        return {"state": "unknown", "items": [], "truncated": False}
    truncated = len(rows) > QUOTES_LIMIT
    rows = rows[:QUOTES_LIMIT]
    items = []
    for row in rows:
        symbol = _text(_field(row, "symbol", 0), 40)
        if symbol is None:
            continue
        source = _text(_field(row, "source", 4), 80)
        crypto = _field(row, "kind", 5) == "crypto"
        threshold = CRYPTO_STALE if crypto else OTHER_STALE
        price = _positive(_field(row, "price", 1))
        asof = _num(_field(row, "asof", 2))
        fetched = _num(_field(row, "fetched", 3))
        source_future = max(0, asof - now) if asof is not None else None
        state = "unknown"
        if (asof is not None and asof > now + FUTURE_TOLERANCE) or (fetched is not None and fetched > now + FUTURE_TOLERANCE):
            source_future = max(0, asof - now) if asof is not None else None
            state = "clock-invalid"
        elif (
            price is not None
            and asof is not None
            and fetched is not None
            and asof > 0
            and fetched > 0
            and fetched <= now + FUTURE_TOLERANCE
        ):
            source_age = now - asof
            receipt_age = now - fetched
            if source_age >= 0 and receipt_age >= 0:
                if source_age <= threshold and receipt_age <= RECEIPT_STALE:
                    state = "fresh"
                else:
                    state = "stale"
            elif receipt_age < 0:
                state = "clock-invalid"
            else:
                state = "stale"
        items.append(
            {
                "symbol": symbol,
                "source": source,
                "market_scope": "crypto" if crypto else "India" if symbol.endswith(('.NS','.BO')) else "other-market",
                "session_state": "not_assessed",
                "source_timestamp": asof,
                "received_at": fetched,
                "last_attempt": None,
                "last_success": None,
                "stale_after_seconds": threshold,
                "clock_skew_seconds": None,
                "source_future_seconds": source_future,
                "state": state,
            }
        )
    if not items:
        state = "unknown"
    elif all(i["state"] == "fresh" for i in items) and not truncated:
        state = "fresh"
    elif any(i["state"] in ("fresh", "stale") for i in items):
        state = "partial"
    else:
        state = "unknown"
    return {"state": state, "items": items, "truncated": truncated}


def _providers(conn, now):
    rows = _rows(conn, "SELECT name, state, checked FROM providers ORDER BY name")
    if rows is None:
        return {"state": "unknown", "items": []}
    items = []
    for row in rows:
        name = _text(_field(row, "name", 0), 80)
        if name is None:
            continue
        raw_state = (_text(_field(row, "state", 1), 40) or "").lower()
        if raw_state == "error":
            state = "error"
        elif raw_state in ("available", "ok"):
            checked = _positive(_field(row, "checked", 2))
            state = "available" if checked is not None and 0 <= now - checked <= 300 else "stale"
        elif raw_state == "stale":
            state = "stale"
        else:
            state = "unknown"
        items.append(
            {
                "name": name,
                "last_attempt": _num(_field(row, "checked", 2)),
                "last_success": None,
                "state": state,
            }
        )
    if not items:
        overall = "unknown"
    elif any(i["state"] == "error" for i in items):
        overall = "error"
    elif any(i["state"] in ("fresh", "stale") for i in items):
        overall = "partial"
    elif all(i["state"] == "available" for i in items):
        overall = "available"
    else:
        overall = "unknown"
    return {"state": overall, "items": items}


def _fx(conn, now):
    rows = _rows(
        conn,
        "SELECT currency, units_per_usd, asof, fetched, source "
        "FROM demo_fx WHERE currency IS NOT NULL ORDER BY currency",
    )
    if rows is None:
        return {"state": "unknown", "items": []}
    items = []
    for row in rows:
        currency = _text(_field(row, "currency", 0), 16)
        if currency is None:
            continue
        rate_valid = _positive(_field(row, "units_per_usd", 1)) is not None
        asof = _num(_field(row, "asof", 2))
        fetched = _num(_field(row, "fetched", 3))
        state = "unknown"
        if (asof is not None and asof > now + FUTURE_TOLERANCE) or (fetched is not None and fetched > now + FUTURE_TOLERANCE):
            state = "clock-invalid"
        elif rate_valid and asof is not None and fetched is not None and asof > 0 and fetched > 0 \
                and fetched <= now + FUTURE_TOLERANCE:
            source_age = now - asof
            receipt_age = now - fetched
            if source_age >= 0 and receipt_age >= 0 and source_age <= FX_STALE and receipt_age <= FX_STALE:
                state = "fresh"
            elif source_age < 0:
                state = "clock-invalid"
            else:
                state = "stale"
        items.append(
            {
                "currency": currency,
                "source_timestamp": asof,
                "received_at": fetched,
                "last_attempt": None,
                "last_success": None,
                "stale_after_seconds": FX_STALE,
                "clock_skew_seconds": None,
                "state": state,
            }
        )
    if not items:
        overall = "unknown"
    elif all(i["state"] == "fresh" for i in items):
        overall = "fresh"
    elif any(i["state"] in ("fresh", "stale") for i in items):
        overall = "partial"
    else:
        overall = "unknown"
    return {"state": overall, "items": items}


def _unknown_resources(reason):
    return {
        "quotes": {"state": "unknown", "items": [], "truncated": False},
        "providers": {"state": "unknown", "items": []},
        "fx": {"state": "unknown", "items": []},
        "executable_books": {"state": "unknown", "reason": reason},
        "models": {"state": "unverified", "identity": "upstream unverified"},
    }


def _controls():
    return {
        "original": {"kill_switch": None, "autopilot": None},
        "scope_note": (
            "Original account only; blocks manual+automatic buys/sells; "
            "holdings remain; other engines unaffected"
        ),
    }


def _compatibility():
    return {
        "legacy_supported": ["web-current", "android-2.2-code20"],
        "new_mutations_enabled": False,
        "backend_build": BUILD_FINGERPRINT,
        "schema_scope": "main market database only",
        "schema_fingerprint": None,
        "schema_compatible": False,
    }


def _respond(now, origin, resources, marker, controls, schema=None):
    compatible = _compatibility()
    if schema:
        compatible.update(schema)
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": now,
        "origin": origin,
        "mode": "paper",
        "live_execution": False,
        "owner_pause": {"active": marker is not None, "state": "paused" if marker else "unknown", "source": marker if marker else "none"},
        "compatibility": compatible,
        "resources": resources,
        "controls": controls,
        "health_state": "paused" if marker else "partial",
    }


def readiness(data_dir, connect_db, origin, model_status=None, now=None):
    """Return the contract_version 2.0 readiness snapshot. Never raises."""
    current = _num(now)
    if current is None:
        current = time.time()
    origin_value = _text(origin, 120) or "unknown"
    marker = _owner_marker(data_dir)

    conn = None
    controls = _controls()
    schema = None
    try:
        conn = connect_db()
        conn.execute("PRAGMA query_only=ON")
        objects = _rows(conn, "SELECT type,name,sql FROM sqlite_master ORDER BY type,name")
        if objects is not None:
            schema = {"schema_fingerprint": hashlib.sha256(json.dumps([list(r) for r in objects]).encode()).hexdigest(),
                      "schema_compatible": all(_rows(conn, sql) is not None for sql in (
                          "SELECT symbol,kind FROM assets LIMIT 0", "SELECT symbol,price,asof,fetched,source FROM quotes LIMIT 0",
                          "SELECT name,state,checked FROM providers LIMIT 0", "SELECT currency,units_per_usd,asof,fetched FROM demo_fx LIMIT 0",
                          "SELECT key,value FROM settings LIMIT 0"))}
        saved = _rows(conn, "SELECT key, value FROM settings WHERE key IN ('kill_switch', 'autopilot')")
        for row in saved or []:
            try:
                value = json.loads(_field(row, "value", 1))
                if type(value) is bool:
                    controls["original"][_field(row, "key", 0)] = value
            except (ValueError, TypeError):
                pass
        resources = {
            "quotes": _quotes(conn, current),
            "providers": _providers(conn, current),
            "fx": _fx(conn, current),
            "executable_books": {
                "state": "unknown",
                "reason": "no independently verified executable books source in foundation",
            },
            "models": {"state": "unverified", "identity": "upstream unverified"},
        }
    except Exception:
        resources = _unknown_resources("database connection unavailable")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    resources['market_calendars']={
        'US': {'state':'unknown','scope':'US only','reason':'Current exchange calendar not assessed by readiness; no US rule applied to other markets'},
        'NSE': {'state':'unknown','scope':'NSE only','reason':'Holiday/special-session calendar not verified here; persisted quote freshness is separate'},
        'crypto': {'state':'continuous-schedule','availability':'unknown','reason':'Continuous schedule does not prove fresh venue connectivity or executable books'}}
    model_checks=[]
    if isinstance(model_status,dict):
        for name,record in sorted(model_status.items()):
            if len(model_checks)>=100:break
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/:+@-]{0,199}',name) or not isinstance(record,dict):continue
            state=record.get('verification_state','untested')
            if state not in ('listed','untested','completion_verified','failed','expired'):state='untested'
            model_checks.append({'requested_model':name,'verification_state':state,'checked':_num(record.get('checked')),
                                 'expires_at':_num(record.get('expires_at')),'schema_verified':False,'upstream_identity':'unverified'})
    resources['models']['checks']=model_checks
    resources['models']['transport_state']='completion_verified' if any(r['verification_state']=='completion_verified' for r in model_checks) else 'unverified'

    return _respond(current, origin_value, resources, marker, controls, schema)
