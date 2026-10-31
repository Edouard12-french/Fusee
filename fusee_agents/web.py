"""Serveur : tableau de bord (application installable), API JSON et chat public des sites."""
import asyncio
import base64
import json
import os
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, integrations, mailbox
from .agents import OWNER, TEAM
from .config import DAILY_BUDGET_USD, MODEL, PUBLIC_URL, WORKSPACE
from .notify import notify
from .scheduler import scheduler
from .tools import _safe_path, deliver_reply, mentions

STATIC = Path(__file__).parent / "static"
PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield


app = FastAPI(title="Fusée", lifespan=lifespan)


@app.middleware("http")
async def guard(request: Request, call_next):
    """/public/* est ouvert (chat des sites, CORS). Le reste est protégé par DASHBOARD_PASSWORD s'il est défini."""
    if request.url.path.startswith("/public/"):
        resp = Response() if request.method == "OPTIONS" else await call_next(request)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp
    if PASSWORD:
        try:
            _, pwd = base64.b64decode(request.headers.get("authorization", "")[6:]).decode().split(":", 1)
        except Exception:  # noqa: BLE001
            pwd = ""
        if not secrets.compare_digest(pwd.encode(), PASSWORD.encode()):
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Fusee"'})
    return await call_next(request)


# --- application (PWA) ------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return FileResponse(STATIC / "sw.js", media_type="application/javascript")


@app.get("/icon-{size}.png")
def icon(size: int):
    if size not in (192, 512):
        raise HTTPException(404)
    return FileResponse(STATIC / f"icon-{size}.png")


# Tout le workspace (sites, jeux, captures, vidéos) consultable depuis l'app : /w/sites/mon-site/
app.mount("/w", StaticFiles(directory=WORKSPACE, html=True), name="workspace")


# --- état général -------------------------------------------------------------
def _msg(m: dict) -> dict:
    try:
        m["attachments"] = json.loads(m.get("attachments") or "{}")
    except ValueError:
        m["attachments"] = {}
    return m


@app.get("/api/state")
def state(after: int = 0):
    states = db.get_states()
    agents = [{"name": a.name, "title": a.title, "emoji": a.emoji, "color": a.color,
               "interval_min": a.interval_min, **{k: v for k, v in states.get(a.name, {}).items() if k != "agent"}}
              for a in TEAM]
    return {
        "agents": agents,
        "messages": [_msg(m) for m in db.recent_messages(200, after)],
        "cost_today": db.cost_today(),
        "budget": DAILY_BUDGET_USD,
        "model": MODEL,
        "paused": scheduler.paused,
        "directive": db.get_setting("directive", ""),
        "pending_approvals": db.q("SELECT COUNT(*) n FROM approvals WHERE status='en attente'")[0]["n"],
        "unread_notifications": db.q("SELECT COUNT(*) n FROM notifications WHERE read=0")[0]["n"],
        "waiting_contacts": len(db.unanswered_contacts()),
        "support_mode": db.get_setting("support_mode", "auto"),
        "browser_enabled": db.get_setting("browser_enabled", "0") == "1",
        "capabilities": {"email": mailbox.ENABLED, "netlify": bool(integrations.NETLIFY_TOKEN),
                         "stripe": bool(integrations.STRIPE_KEY), "public_url": PUBLIC_URL,
                         "push": bool(os.getenv("NTFY_TOPIC"))},
    }


@app.get("/api/activity")
def activity(agent: str | None = None, limit: int = 150):
    return db.activity(agent, limit)


@app.get("/api/ideas")
def ideas():
    return db.q("SELECT * FROM ideas ORDER BY CASE status WHEN 'en ligne' THEN 0 WHEN 'en cours' THEN 1 "
                "WHEN 'prête à vendre' THEN 2 WHEN 'validée' THEN 3 WHEN 'proposée' THEN 4 ELSE 5 END, "
                "revenue_eur_month DESC")


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


# --- vitrine : sites, jeux, captures, vidéos --------------------------------
@app.get("/api/vitrine")
def vitrine():
    deployed = {d["site"]: d for d in db.q("SELECT site, url, max(ts) ts FROM deployments GROUP BY site")}
    projects = []
    for kind, folder in (("site", "sites"), ("jeu", "jeux")):
        base = WORKSPACE / folder
        for d in sorted(p for p in base.iterdir() if p.is_dir()) if base.exists() else []:
            if (d / "index.html").is_file():
                rel = str(d.relative_to(WORKSPACE))
                projects.append({"kind": kind, "name": d.name, "local": f"/w/{rel}/",
                                 "public": deployed.get(rel, {}).get("url"),
                                 "updated": max(f.stat().st_mtime for f in d.rglob("*") if f.is_file())})
    media = [{"path": str(p.relative_to(WORKSPACE)), "ts": p.stat().st_mtime,
              "type": "video" if p.suffix in (".mp4", ".webm") else "image"}
             for p in WORKSPACE.rglob("*")
             if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm")]
    media.sort(key=lambda m: -m["ts"])
    return {"projects": sorted(projects, key=lambda p: -p["updated"]), "media": media[:120]}


# --- ventes -------------------------------------------------------------------
_sales_cache: dict = {"ts": 0, "data": None}


@app.get("/api/sales")
async def sales():
    out = {"payment_links": db.q("SELECT * FROM payment_links ORDER BY id DESC"),
           "deployments": db.q("SELECT site, url, max(ts) ts FROM deployments GROUP BY site ORDER BY ts DESC"),
           "stripe": None, "stripe_error": None}
    if integrations.STRIPE_KEY:
        if time.time() - _sales_cache["ts"] > 300:
            try:
                _sales_cache["data"] = await asyncio.to_thread(integrations.sales_summary)
                _sales_cache["ts"] = time.time()
            except Exception as e:  # noqa: BLE001
                out["stripe_error"] = str(e)
        out["stripe"] = _sales_cache["data"]
    return out


# --- prospects ----------------------------------------------------------------
@app.get("/api/contacts")
def contacts():
    waiting = {c["id"] for c in db.unanswered_contacts()}
    rows = db.q("SELECT * FROM contacts ORDER BY score DESC, last_ts DESC LIMIT 300")
    return [{**r, "waiting": r["id"] in waiting} for r in rows]


@app.get("/api/contacts/{cid}")
def contact(cid: int):
    c = db.q("SELECT * FROM contacts WHERE id=?", (cid,))
    if not c:
        raise HTTPException(404)
    return {"contact": c[0], "messages": db.thread(cid, 500)}


class Msg(BaseModel):
    content: str


@app.post("/api/contacts/{cid}/reply")
async def owner_reply(cid: int, msg: Msg):
    """Patron répond lui-même à un client."""
    if not db.q("SELECT id FROM contacts WHERE id=?", (cid,)) or not msg.content.strip():
        raise HTTPException(400)
    try:
        channel = await deliver_reply(cid, msg.content.strip(), OWNER)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "channel": channel}


# --- discussion d'équipe & réglages ------------------------------------------
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


@app.post("/api/browser")
def browser_permission(on: bool):
    db.set_setting("browser_enabled", "1" if on else "0")
    db.post_message(OWNER, "🌐 Navigation web autorisée pour l'équipe." if on else "🌐 Navigation web désactivée.")
    return {"browser_enabled": on}


@app.post("/api/wake/{agent}")
def wake(agent: str):
    scheduler.wake(agent, f"{OWNER} a demandé un cycle maintenant")
    return {"ok": True}


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


# --- validations --------------------------------------------------------------
@app.get("/api/approvals")
def approvals():
    rows = db.q("SELECT * FROM approvals ORDER BY (status='en attente') DESC, id DESC LIMIT 100")
    for r in rows:
        try:
            r["attachments"] = json.loads(r["payload"]) if r["kind"] != "réponse client" and r["payload"] else {}
        except ValueError:
            r["attachments"] = {}
    return rows


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
    if a["kind"] == "réponse client" and d.approve:
        try:
            await deliver_reply(json.loads(a["payload"])["contact_id"], a["details"], a["agent"])
        except RuntimeError as e:
            raise HTTPException(400, str(e))
    db.x("UPDATE approvals SET status=?, response=?, decided_ts=CAST(strftime('%s','now') AS REAL) WHERE id=?",
         (status, d.comment.strip(), aid))
    emoji = "✅" if d.approve else "❌"
    db.post_message(OWNER, f"{emoji} Demande #{aid} {status} : {a['title']}"
                    + (f" — {d.comment.strip()}" if d.comment.strip() else ""))
    for t in {a["agent"], "Atlas"}:
        scheduler.wake(t, f"{OWNER} a {'accepté' if d.approve else 'refusé'} la demande #{aid} « {a['title']} »"
                          + (f" avec ce commentaire : {d.comment}" if d.comment else ""))
    return {"ok": True}


@app.get("/api/notifications")
def notifications():
    rows = db.q("SELECT * FROM notifications ORDER BY id DESC LIMIT 100")
    db.x("UPDATE notifications SET read=1 WHERE read=0")
    return rows


# --- chat public des sites (sans mot de passe) --------------------------------
_hits: dict[str, deque] = defaultdict(deque)


def _rate_ok(key: str, limit: int, window: int) -> bool:
    q = _hits[key]
    now = time.time()
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


@app.get("/public/chat.js")
def chat_js():
    return FileResponse(STATIC / "chat-widget.js", media_type="application/javascript")


@app.post("/public/chat/send")
async def chat_send(request: Request):
    try:
        data = json.loads(await request.body())  # envoyé en text/plain → pas de pré-vol CORS
        session, text = str(data["session"])[:64], str(data["message"]).strip()[:2000]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400)
    if len(session) < 16 or not text:
        raise HTTPException(400)
    ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
    if not (_rate_ok(f"s:{session}", 20, 3600) and _rate_ok(f"ip:{ip}", 40, 3600) and _rate_ok("all", 400, 3600)):
        return JSONResponse({"error": "Trop de messages, réessayez plus tard."}, status_code=429)
    site = str(data.get("site", ""))[:60]
    email = str(data.get("email", "")).strip()[:120]
    email = email if "@" in email and "." in email.split("@")[-1] else ""
    is_new = not db.q("SELECT id FROM contacts WHERE session=?", (session,))
    cid = db.upsert_contact(session=session, email=email, name=str(data.get("name", ""))[:80],
                            source=f"chat {site}".strip())
    db.add_conv(cid, "chat", "in", text, subject=site)
    if is_new:
        notify("client", f"💬 Nouveau visiteur sur le chat {site}", text[:500], priority="low")
    scheduler.wake("Iris", f"message chat du contact #{cid} sur le site {site}")
    return {"ok": True}


@app.get("/public/chat/poll")
def chat_poll(session: str, after: int = 0):
    c = db.q("SELECT id FROM contacts WHERE session=?", (session[:64],))
    if not c or len(session) < 16:
        return {"messages": []}
    rows = db.q("SELECT id, ts, direction, content FROM conv WHERE contact_id=? AND channel='chat' AND id>? "
                "ORDER BY id", (c[0]["id"], after))
    return {"messages": rows}
