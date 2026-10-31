"""Serveur du tableau de bord : API JSON + page web."""
import asyncio
import base64
import json
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from . import db, mailbox
from .notify import notify
from .agents import OWNER, TEAM
from .config import DAILY_BUDGET_USD, MODEL, WORKSPACE
from .scheduler import scheduler
from .tools import _safe_path, mentions

STATIC = __import__("pathlib").Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield


app = FastAPI(title="Fusée", lifespan=lifespan)
PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    """Protège le tableau de bord par mot de passe (utilisateur : n'importe lequel) si DASHBOARD_PASSWORD est défini."""
    if PASSWORD:
        try:
            _, pwd = base64.b64decode(request.headers.get("authorization", "")[6:]).decode().split(":", 1)
        except Exception:  # noqa: BLE001
            pwd = ""
        if not secrets.compare_digest(pwd.encode(), PASSWORD.encode()):
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Fusee"'})
    return await call_next(request)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
def state(after: int = 0):
    states = db.get_states()
    agents = [{"name": a.name, "title": a.title, "emoji": a.emoji, "color": a.color,
               "interval_min": a.interval_min, **{k: v for k, v in states.get(a.name, {}).items() if k != "agent"}}
              for a in TEAM]
    return {
        "agents": agents,
        "messages": db.recent_messages(200, after),
        "cost_today": db.cost_today(),
        "budget": DAILY_BUDGET_USD,
        "model": MODEL,
        "paused": scheduler.paused,
        "directive": db.get_setting("directive", ""),
        "pending_approvals": db.q("SELECT COUNT(*) n FROM approvals WHERE status='en attente'")[0]["n"],
        "unread_notifications": db.q("SELECT COUNT(*) n FROM notifications WHERE read=0")[0]["n"],
        "support_mode": db.get_setting("support_mode", "auto"),
        "mail_enabled": mailbox.ENABLED,
    }


@app.get("/api/activity")
def activity(agent: str | None = None, limit: int = 150):
    return db.activity(agent, limit)


@app.get("/api/ideas")
def ideas():
    return db.q("SELECT * FROM ideas ORDER BY CASE status WHEN 'en cours' THEN 0 WHEN 'prête à vendre' THEN 1 "
                "WHEN 'validée' THEN 2 WHEN 'proposée' THEN 3 ELSE 4 END, revenue_eur_month DESC")


@app.get("/api/reports")
def reports():
    return db.q("SELECT * FROM reports ORDER BY id DESC LIMIT 50")


@app.get("/api/portfolio")
def portfolio():
    return {**db.portfolio(), "trades": db.q("SELECT * FROM trades ORDER BY id DESC LIMIT 100")}


@app.get("/api/memory/{agent}")
def memory(agent: str):
    return {"content": db.get_memory(agent)}


@app.get("/api/files")
def files():
    return [str(p.relative_to(WORKSPACE)) for p in sorted(WORKSPACE.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts]


@app.get("/api/file")
def file(path: str):
    try:
        p = _safe_path(path)
    except ValueError:
        raise HTTPException(400, "chemin invalide")
    if not p.is_file():
        raise HTTPException(404)
    return FileResponse(p)


class Msg(BaseModel):
    content: str


@app.post("/api/message")
def send(msg: Msg):
    text = msg.content.strip()
    if not text:
        raise HTTPException(400, "message vide")
    db.post_message(OWNER, text)
    targets = mentions(text) or ["Atlas"]  # sans mention, le directeur répond
    for t in targets:
        scheduler.wake(t, f"message de {OWNER} : {text[:500]}")
    return {"ok": True, "woken": targets}


@app.post("/api/directive")
def directive(msg: Msg):
    db.set_setting("directive", msg.content.strip())
    return {"ok": True}


@app.post("/api/pause")
def pause(on: bool):
    db.set_setting("paused", "1" if on else "0")
    return {"paused": on}


@app.post("/api/wake/{agent}")
def wake(agent: str):
    scheduler.wake(agent, f"{OWNER} a demandé un cycle maintenant")
    return {"ok": True}


@app.get("/api/approvals")
def approvals():
    return db.q("SELECT * FROM approvals ORDER BY (status='en attente') DESC, id DESC LIMIT 100")


class Decision(BaseModel):
    approve: bool
    comment: str = ""


@app.post("/api/approvals/{aid}")
async def decide(aid: int, d: Decision):
    rows = db.q("SELECT * FROM approvals WHERE id=?", (aid,))
    if not rows:
        raise HTTPException(404)
    a = rows[0]
    if a["status"] != "en attente":
        raise HTTPException(409, "déjà décidée")
    status = "acceptée" if d.approve else "refusée"
    if a["kind"] == "réponse client":
        inbox_id = json.loads(a["payload"])["inbox_id"]
        if d.approve:
            if not mailbox.ENABLED:
                raise HTTPException(400, "boîte mail non configurée")
            await asyncio.to_thread(mailbox.send, inbox_id, a["details"])
        else:
            db.x("UPDATE inbox SET status='nouveau' WHERE id=?", (inbox_id,))
    db.x("UPDATE approvals SET status=?, response=?, decided_ts=CAST(strftime('%s','now') AS REAL) WHERE id=?",
         (status, d.comment.strip(), aid))
    emoji = "✅" if d.approve else "❌"
    db.post_message(OWNER, f"{emoji} Demande #{aid} {status} : {a['title']}" + (f" — {d.comment.strip()}" if d.comment.strip() else ""))
    for t in {a["agent"], "Atlas"}:
        scheduler.wake(t, f"{OWNER} a {'accepté' if d.approve else 'refusé'} la demande #{aid} « {a['title']} »"
                          + (f" avec ce commentaire : {d.comment}" if d.comment else ""))
    return {"ok": True}


@app.get("/api/notifications")
def notifications():
    rows = db.q("SELECT * FROM notifications ORDER BY id DESC LIMIT 100")
    db.x("UPDATE notifications SET read=1 WHERE read=0")
    return rows


@app.get("/api/inbox")
def inbox():
    return db.q("SELECT * FROM inbox ORDER BY id DESC LIMIT 100")


@app.post("/api/support_mode")
def support_mode(mode: str):
    if mode not in ("auto", "validation"):
        raise HTTPException(400)
    db.set_setting("support_mode", mode)
    return {"mode": mode}


@app.post("/api/test_notification")
def test_notification():
    notify("alerte", "Test Fusée 🚀", "Si tu vois ce message sur ton téléphone, les notifications marchent !")
    return {"ok": True}
