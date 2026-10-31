"""Stockage SQLite : groupe de discussion, activité, idées, trades, rapports, mémoire."""
import json
import sqlite3
import threading
import time
from datetime import date

from .config import DB_PATH, PAPER_START_CASH

_lock = threading.Lock()
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row

_conn.executescript(
    """
CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, ts REAL, sender TEXT, content TEXT);
CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY, ts REAL, agent TEXT, kind TEXT, summary TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS ideas (id INTEGER PRIMARY KEY, ts REAL, agent TEXT, title TEXT, description TEXT,
    revenue_eur_month REAL, effort TEXT, status TEXT DEFAULT 'proposée');
CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, ts REAL, agent TEXT, symbol TEXT, side TEXT,
    qty REAL, price REAL, rationale TEXT);
CREATE TABLE IF NOT EXISTS marks (symbol TEXT PRIMARY KEY, price REAL, ts REAL);
CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY, ts REAL, agent TEXT, title TEXT, content TEXT);
CREATE TABLE IF NOT EXISTS memory (agent TEXT PRIMARY KEY, content TEXT);
CREATE TABLE IF NOT EXISTS agent_state (agent TEXT PRIMARY KEY, status TEXT, task TEXT, last_run REAL,
    cycles INTEGER DEFAULT 0, cost_usd REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS usage (day TEXT PRIMARY KEY, cost_usd REAL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""
)


def q(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in _conn.execute(sql, args).fetchall()]


def x(sql: str, args: tuple = ()) -> int:
    with _lock:
        cur = _conn.execute(sql, args)
        _conn.commit()
        return cur.lastrowid


# --- groupe de discussion -------------------------------------------------
def post_message(sender: str, content: str) -> int:
    return x("INSERT INTO messages (ts, sender, content) VALUES (?,?,?)", (time.time(), sender, content))


def recent_messages(limit: int = 40, after_id: int = 0) -> list[dict]:
    rows = q("SELECT * FROM messages WHERE id > ? ORDER BY id DESC LIMIT ?", (after_id, limit))
    return rows[::-1]


# --- activité --------------------------------------------------------------
def log(agent: str, kind: str, summary: str, detail: str | dict | None = None) -> None:
    if isinstance(detail, (dict, list)):
        detail = json.dumps(detail, ensure_ascii=False, indent=1)
    x(
        "INSERT INTO activity (ts, agent, kind, summary, detail) VALUES (?,?,?,?,?)",
        (time.time(), agent, kind, summary[:500], (detail or "")[:20000]),
    )


def activity(agent: str | None = None, limit: int = 100) -> list[dict]:
    if agent:
        return q("SELECT * FROM activity WHERE agent=? ORDER BY id DESC LIMIT ?", (agent, limit))
    return q("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,))


# --- état des agents & coûts ----------------------------------------------
def set_state(agent: str, **fields) -> None:
    x("INSERT OR IGNORE INTO agent_state (agent, status, task) VALUES (?, 'en attente', '')", (agent,))
    for k, v in fields.items():
        x(f"UPDATE agent_state SET {k}=? WHERE agent=?", (v, agent))


def get_states() -> dict[str, dict]:
    return {r["agent"]: r for r in q("SELECT * FROM agent_state")}


def add_cost(agent: str, usd: float) -> None:
    today = date.today().isoformat()
    x("INSERT OR IGNORE INTO usage (day, cost_usd) VALUES (?, 0)", (today,))
    x("UPDATE usage SET cost_usd = cost_usd + ? WHERE day=?", (usd, today))
    x("UPDATE agent_state SET cost_usd = cost_usd + ? WHERE agent=?", (usd, agent))


def cost_today() -> float:
    rows = q("SELECT cost_usd FROM usage WHERE day=?", (date.today().isoformat(),))
    return rows[0]["cost_usd"] if rows else 0.0


# --- mémoire ---------------------------------------------------------------
def get_memory(agent: str) -> str:
    rows = q("SELECT content FROM memory WHERE agent=?", (agent,))
    return rows[0]["content"] if rows else ""


def set_memory(agent: str, content: str) -> None:
    x("INSERT OR REPLACE INTO memory (agent, content) VALUES (?,?)", (agent, content))


# --- réglages --------------------------------------------------------------
def get_setting(key: str, default: str = "") -> str:
    rows = q("SELECT value FROM settings WHERE key=?", (key,))
    return rows[0]["value"] if rows else default


def set_setting(key: str, value: str) -> None:
    x("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))


# --- portefeuille simulé ---------------------------------------------------
def portfolio() -> dict:
    cash = PAPER_START_CASH
    positions: dict[str, dict] = {}
    for t in q("SELECT * FROM trades ORDER BY id"):
        sign = 1 if t["side"] == "buy" else -1
        cash -= sign * t["qty"] * t["price"]
        p = positions.setdefault(t["symbol"], {"qty": 0.0, "cost": 0.0})
        if sign > 0:
            p["cost"] += t["qty"] * t["price"]
        elif p["qty"]:
            p["cost"] -= p["cost"] * (t["qty"] / p["qty"])
        p["qty"] += sign * t["qty"]
    marks = {m["symbol"]: m for m in q("SELECT * FROM marks")}
    value = cash
    out = []
    for sym, p in positions.items():
        if abs(p["qty"]) < 1e-12:
            continue
        price = marks.get(sym, {}).get("price") or (p["cost"] / p["qty"] if p["qty"] else 0)
        mv = p["qty"] * price
        value += mv
        out.append({"symbol": sym, "qty": p["qty"], "avg_price": p["cost"] / p["qty"],
                    "last_price": price, "value": mv, "pnl": mv - p["cost"]})
    return {"cash": cash, "total_value": value, "start": PAPER_START_CASH,
            "pnl": value - PAPER_START_CASH, "positions": out}
