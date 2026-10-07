"""
db.py - SQLite database layer for Study Guard v2.
Includes HMAC hash-chain for tamper-evident analytics.
"""

import hashlib
import hmac
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "study_guard.db"

_local = threading.local()
_integrity_key: bytes = b""


def set_integrity_key(api_key: str) -> None:
    """Derive a stable HMAC key from the user API key."""
    global _integrity_key
    _integrity_key = hmac.new(
        api_key.encode("utf-8"),
        b"STUDYGUARD_INTEGRITY_v1",
        hashlib.sha256,
    ).digest()


def _conn() -> sqlite3.Connection:
    """Return a thread-local SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db() -> None:
    """Create all tables if they do not exist."""
    c = _conn()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    UNIQUE NOT NULL,
            description   TEXT    NOT NULL DEFAULT '',
            color         TEXT    NOT NULL DEFAULT '#6c63ff',
            is_productive INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            goal             TEXT    NOT NULL,
            category_id      INTEGER,
            category_name    TEXT,
            mode             TEXT    NOT NULL DEFAULT 'block',
            started_at       TEXT    NOT NULL,
            ended_at         TEXT,
            duration_secs    INTEGER,
            pomodoro_enabled INTEGER NOT NULL DEFAULT 0,
            pomo_study_mins  INTEGER NOT NULL DEFAULT 25,
            pomo_break_mins  INTEGER NOT NULL DEFAULT 5,
            blocks_count     INTEGER NOT NULL DEFAULT 0,
            jev_calls        INTEGER NOT NULL DEFAULT 0,
            row_hash         TEXT,
            chain_prev       TEXT,
            FOREIGN KEY(category_id) REFERENCES categories(id)
        );

        CREATE TABLE IF NOT EXISTS activity_events (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id          INTEGER NOT NULL,
            window_title        TEXT,
            process_name        TEXT,
            classified_category TEXT,
            classification      TEXT,
            duration_secs       INTEGER NOT NULL DEFAULT 1,
            action              TEXT    NOT NULL DEFAULT 'allowed',
            jev_confidence      REAL,
            timestamp           TEXT    NOT NULL,
            row_hash            TEXT,
            chain_prev          TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        INSERT OR IGNORE INTO meta VALUES ('chain_head_session', '');
        INSERT OR IGNORE INTO meta VALUES ('chain_head_event', '');
    """)
    c.commit()


# ---------------------------------------------------------------------------
# HMAC helpers
# ---------------------------------------------------------------------------

def _hmac_hash(data: dict, prev_hash: str) -> str:
    if not _integrity_key:
        return ""
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False) + prev_hash
    return hmac.new(_integrity_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _get_chain_head(table: str) -> str:
    c = _conn()
    row = c.execute("SELECT value FROM meta WHERE key=?", (f"chain_head_{table}",)).fetchone()
    return row["value"] if row and row["value"] else ""


def _set_chain_head(table: str, h: str) -> None:
    _conn().execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (f"chain_head_{table}", h))


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

def get_categories() -> list:
    rows = _conn().execute(
        "SELECT id, name, description, color, is_productive FROM categories ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def add_category(name: str, description: str, color: str, is_productive: bool) -> dict:
    c = _conn()
    c.execute(
        "INSERT INTO categories (name, description, color, is_productive, created_at) VALUES (?,?,?,?,?)",
        (name.strip(), description.strip(), color, int(is_productive), datetime.now().isoformat()),
    )
    c.commit()
    row = c.execute("SELECT id,name,description,color,is_productive FROM categories WHERE name=?",
                    (name.strip(),)).fetchone()
    return dict(row)


def update_category(cat_id: int, name: str, description: str, color: str, is_productive: bool) -> None:
    c = _conn()
    c.execute(
        "UPDATE categories SET name=?,description=?,color=?,is_productive=? WHERE id=?",
        (name.strip(), description.strip(), color, int(is_productive), cat_id),
    )
    c.commit()


def delete_category(cat_id: int) -> None:
    c = _conn()
    c.execute("DELETE FROM categories WHERE id=?", (cat_id,))
    c.commit()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def start_session(goal: str, category_id, category_name: str,
                  mode: str, duration_mins: int,
                  pomodoro: bool, pomo_study: int, pomo_break: int) -> int:
    now = datetime.now().isoformat()
    c = _conn()
    cur = c.execute(
        """INSERT INTO sessions
             (goal, category_id, category_name, mode, started_at,
              pomodoro_enabled, pomo_study_mins, pomo_break_mins)
           VALUES (?,?,?,?,?,?,?,?)""",
        (goal, category_id, category_name, mode, now,
         int(pomodoro), pomo_study, pomo_break),
    )
    session_id = cur.lastrowid

    row_data = {"id": session_id, "goal": goal, "category_name": category_name,
                "mode": mode, "started_at": now}
    prev = _get_chain_head("session")
    row_hash = _hmac_hash(row_data, prev)
    c.execute("UPDATE sessions SET row_hash=?, chain_prev=? WHERE id=?",
              (row_hash, prev, session_id))
    _set_chain_head("session", row_hash)
    c.commit()
    return session_id


def end_session(session_id: int, blocks_count: int, jev_calls: int) -> None:
    now = datetime.now().isoformat()
    c = _conn()
    row = c.execute("SELECT started_at FROM sessions WHERE id=?", (session_id,)).fetchone()
    duration = 0
    if row:
        started = datetime.fromisoformat(row["started_at"])
        duration = int((datetime.now() - started).total_seconds())
    c.execute(
        "UPDATE sessions SET ended_at=?, duration_secs=?, blocks_count=?, jev_calls=? WHERE id=?",
        (now, duration, blocks_count, jev_calls, session_id),
    )
    c.commit()


def log_event(session_id: int, window_title: str, process_name: str,
              classified_category: str, classification: str,
              action: str, jev_confidence) -> None:
    now = datetime.now().isoformat()
    c = _conn()
    cur = c.execute(
        """INSERT INTO activity_events
             (session_id, window_title, process_name, classified_category,
              classification, action, jev_confidence, timestamp)
           VALUES (?,?,?,?,?,?,?,?)""",
        (session_id, window_title, process_name, classified_category,
         classification, action, jev_confidence, now),
    )
    event_id = cur.lastrowid

    row_data = {"id": event_id, "session_id": session_id, "window_title": window_title,
                "classified_category": classified_category, "classification": classification,
                "action": action, "timestamp": now}
    prev = _get_chain_head("event")
    row_hash = _hmac_hash(row_data, prev)
    c.execute("UPDATE activity_events SET row_hash=?, chain_prev=? WHERE id=?",
              (row_hash, prev, event_id))
    _set_chain_head("event", row_hash)
    c.commit()


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def get_overview(days: int = 30) -> dict:
    c = _conn()
    period = f"-{days} days"

    row = c.execute(
        """SELECT COUNT(*) as sessions,
                  COALESCE(SUM(duration_secs),0) as total_secs,
                  COALESCE(SUM(blocks_count),0) as total_blocks
           FROM sessions
           WHERE ended_at IS NOT NULL AND date(started_at) >= date('now', ?)""",
        (period,),
    ).fetchone()

    cats = c.execute(
        """SELECT category_name, COALESCE(SUM(duration_secs),0) as secs
           FROM sessions
           WHERE ended_at IS NOT NULL AND category_name IS NOT NULL
             AND date(started_at) >= date('now', ?)
           GROUP BY category_name ORDER BY secs DESC""",
        (period,),
    ).fetchall()

    daily = c.execute(
        """SELECT date(started_at) as day, COALESCE(SUM(duration_secs),0) as secs
           FROM sessions
           WHERE ended_at IS NOT NULL AND date(started_at) >= date('now', ?)
           GROUP BY day ORDER BY day ASC""",
        (period,),
    ).fetchall()

    color_map = {r["name"]: r["color"] for r in
                 c.execute("SELECT name, color FROM categories").fetchall()}

    return {
        "sessions_count": row["sessions"],
        "total_study_mins": round(row["total_secs"] / 60, 1),
        "total_blocks": row["total_blocks"],
        "categories_breakdown": [
            {"name": r["category_name"], "mins": round(r["secs"] / 60, 1),
             "color": color_map.get(r["category_name"], "#6c63ff")}
            for r in cats
        ],
        "daily_activity": [
            {"date": r["day"], "mins": round(r["secs"] / 60, 1)} for r in daily
        ],
        "most_studied": cats[0]["category_name"] if cats else None,
    }


def get_sessions(limit: int = 20, offset: int = 0) -> dict:
    c = _conn()
    total = c.execute("SELECT COUNT(*) FROM sessions WHERE ended_at IS NOT NULL").fetchone()[0]
    rows = c.execute(
        """SELECT id, goal, category_name, mode, started_at, ended_at,
                  duration_secs, blocks_count, jev_calls
           FROM sessions WHERE ended_at IS NOT NULL
           ORDER BY started_at DESC LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()
    return {"total": total, "sessions": [dict(r) for r in rows]}


def get_session_detail(session_id: int) -> dict:
    c = _conn()
    s = c.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not s:
        return {}
    events = c.execute(
        """SELECT window_title, process_name, classified_category, classification,
                  action, jev_confidence, timestamp
           FROM activity_events WHERE session_id=? ORDER BY timestamp ASC""",
        (session_id,),
    ).fetchall()
    return {"session": dict(s), "events": [dict(e) for e in events]}


# ---------------------------------------------------------------------------
# Integrity verification
# ---------------------------------------------------------------------------

def verify_integrity() -> dict:
    c = _conn()

    def check_table(rows, key_fields):
        prev = ""
        for row in rows:
            row = dict(row)
            stored_hash = row.pop("row_hash", "") or ""
            row.pop("chain_prev", None)
            row_data = {k: row.get(k) for k in key_fields}
            expected = _hmac_hash(row_data, prev)
            if stored_hash and expected and stored_hash != expected:
                return False, row.get("id")
            prev = stored_hash
        return True, None

    sess_rows = c.execute("SELECT * FROM sessions ORDER BY id ASC").fetchall()
    sess_ok, bad_sess = check_table(
        sess_rows,
        ["id", "goal", "category_name", "mode", "started_at"]
    )

    evt_rows = c.execute("SELECT * FROM activity_events ORDER BY id ASC").fetchall()
    evt_ok, bad_evt = check_table(
        evt_rows,
        ["id", "session_id", "window_title", "classified_category",
         "classification", "action", "timestamp"]
    )

    return {
        "ok": sess_ok and evt_ok,
        "sessions_checked": len(sess_rows),
        "events_checked": len(evt_rows),
        "first_tampered_session": bad_sess,
        "first_tampered_event": bad_evt,
    }