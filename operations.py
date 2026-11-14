"""Original-account stop: one-way, feature-flagged, no resume/rollback."""
import hashlib
import json
import re
import uuid

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,100}$")
_ALLOWED = ("account", "command_id", "origin", "settings_revision", "server_id")
_REV_KEY = "foundation_control_revision"
_PRINCIPAL = "local-owner"
_ACCOUNT = "original"
_DDL = ("CREATE TABLE IF NOT EXISTS foundation_commands ("
        " origin TEXT NOT NULL, principal TEXT NOT NULL, account TEXT NOT NULL,"
        " command_id TEXT NOT NULL, payload_hash TEXT NOT NULL, result TEXT NOT NULL,"
        " PRIMARY KEY (origin, principal, account, command_id))")


class OperationError(Exception):
    """Transport-safe failure: status, code, generic text."""

    def __init__(self, status, code):
        self.status = status
        self.code = code
        self.text = "operation rejected"
        super().__init__(self.text)


class OriginalStop:
    def __init__(self, connect_db, lock, enabled=False):
        self._connect_db = connect_db
        self._lock = lock
        self._enabled = enabled is True

    def init(self, c):
        if not c.in_transaction:c.execute('BEGIN IMMEDIATE')
        c.execute(_DDL)
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",('foundation_server_identity',json.dumps(uuid.uuid4().hex)))

    def server_identity(self,c):
        row=c.execute("SELECT value FROM settings WHERE key='foundation_server_identity'").fetchone()
        try:value=json.loads(row[0]) if row else None
        except (ValueError,TypeError):value=None
        if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{32}',value):
            raise OperationError(503,'server_identity_unavailable')
        return value

    def revision(self, c):
        row = c.execute("SELECT value FROM settings WHERE key=?", (_REV_KEY,)).fetchone()
        if not row or row[0] is None:
            return "0"
        try:
            val = json.loads(row[0])
        except (TypeError, ValueError):
            val = row[0]
        text = str(val)
        if not re.fullmatch(r"[0-9]{1,19}",text):
            raise OperationError(503,"revision_unavailable")
        return text

    def bump(self, c):
        nxt = str(int(self.revision(c)) + 1)
        c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
                  (_REV_KEY, json.dumps(nxt)))
        return nxt

    def inspect(self, origin, command_id=None):
        c = self._connect_db()
        try:
            c.execute("PRAGMA query_only=ON")
            out = {"origin": origin, "account": _ACCOUNT,
                   "server_id": self.server_identity(c),
                   "settings_revision": self.revision(c), "enabled": self._enabled}
            if command_id is not None:
                if not isinstance(command_id,str) or not _ID_RE.fullmatch(command_id):
                    raise OperationError(400,"invalid_request")
                row = c.execute("SELECT result FROM foundation_commands WHERE origin=?"
                                " AND principal=? AND account=? AND command_id=?",
                                (origin, _PRINCIPAL, _ACCOUNT, command_id)).fetchone()
                if row:
                    out["state"] = "applied"
                    out["result"] = json.loads(row[0])
                else:
                    raise OperationError(404,"command_not_found")
            return out
        finally:
            c.close()

    def stop(self, body, actual_origin):
        if not self._enabled:
            raise OperationError(409, "feature_disabled")
        if not isinstance(body, dict) or not isinstance(actual_origin, str) or not actual_origin:
            raise OperationError(400, "invalid_request")
        if set(body) != set(_ALLOWED):
            raise OperationError(400, "invalid_request")
        cid, rev = body["command_id"], body["settings_revision"]
        if body["origin"] != actual_origin:
            raise OperationError(409, "origin_mismatch")
        if body["account"] != _ACCOUNT:
            raise OperationError(400, "invalid_request")
        if not isinstance(cid, str) or not _ID_RE.fullmatch(cid):
            raise OperationError(400, "invalid_request")
        if not isinstance(rev, str) or not re.fullmatch(r"[0-9]{1,19}",rev):
            raise OperationError(400, "invalid_request")
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        with self._lock:
            c = self._connect_db()
            try:
                c.execute("BEGIN IMMEDIATE")
                if body['server_id'] != self.server_identity(c):
                    raise OperationError(409,'server_mismatch')
                row = c.execute("SELECT payload_hash, result FROM foundation_commands"
                                " WHERE origin=? AND principal=? AND account=? AND command_id=?",
                                (actual_origin, _PRINCIPAL, _ACCOUNT, cid)).fetchone()
                if row is not None:
                    if row[0] != digest:
                        raise OperationError(409, "command_conflict")
                    c.rollback()
                    return json.loads(row[1])
                if self.revision(c) != rev:
                    raise OperationError(409, "revision_conflict")
                new_rev = self.bump(c)
                c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
                          ("kill_switch", json.dumps(True)))
                result = {"ok": True, "command_id": cid, "origin": actual_origin,
                          "server_id": self.server_identity(c),
                          "account": _ACCOUNT, "state": "applied",
                          "settings_revision": new_rev, "holdings": "retained",
                          "scope": "manual and automatic buys/sells only; independent engines unchanged"}
                c.execute("INSERT INTO foundation_commands VALUES (?, ?, ?, ?, ?, ?)",
                          (actual_origin, _PRINCIPAL, _ACCOUNT, cid, digest,
                           json.dumps(result, sort_keys=True)))
                c.commit()
                return result
            except OperationError:
                try:
                    c.rollback()
                except Exception:
                    pass
                raise
            except Exception:
                try:
                    c.rollback()
                except Exception:
                    pass
                raise OperationError(503, "command_uncertain") from None
            finally:
                c.close()
