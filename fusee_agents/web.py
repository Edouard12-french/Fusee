"""Serveur : tableau de bord (application installable), API JSON et chat public des sites."""
import asyncio
import base64
import json
import os
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analytics, budget, db, integrations, mailbox
from . import setup as setup_mod
from .agents import OWNER, TEAM
from .config import PLAN, PUBLIC_URL, USD_EUR, WORKSPACE, model_for
from .notify import notify
from .scheduler import scheduler
from .tools import _safe_path, deliver_reply, mentions, products_overview, skills, toolbox

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
    agents = [{"name": a.name, "kind": a.kind, "title": a.title, "emoji": a.emoji, "color": a.color,
               "tier": a.tier, "model": model_for(a.tier)[0], "interval_min": a.interval_min,
               **{k: v for k, v in states.get(a.name, {}).items() if k != "agent"}}
              for a in TEAM]
    b = budget.summary()
    return {
        "agents": agents,
        "messages": [_msg(m) for m in db.recent_messages(200, after)],
        "plan": PLAN,
        "budget": {k: b[k] for k in ("remaining_eur", "initial_eur", "api_today_eur", "api_daily_cap_eur",
                                     "api_spent_eur", "api_budget_eur")},
        "open_questions": db.q("SELECT COUNT(*) n FROM owner_questions WHERE answer IS NULL")[0]["n"],
        "open_owner_tasks": db.q("SELECT COUNT(*) n FROM owner_tasks WHERE done=0")[0]["n"],
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
                st = analytics.site_stats(d.name, 7)
                projects.append({"kind": kind, "name": d.name, "local": f"/w/{rel}/",
                                 "public": deployed.get(rel, {}).get("url"),
                                 "stats": {k: st[k] for k in ("visiteurs", "clics_achat", "chats_ouverts", "ventes",
                                                              "taux_conversion")},
                                 "updated": max(f.stat().st_mtime for f in d.rglob("*") if f.is_file())})
    media = [{"path": str(p.relative_to(WORKSPACE)), "ts": p.stat().st_mtime,
              "type": "video" if p.suffix in (".mp4", ".webm") else "image"}
             for p in WORKSPACE.rglob("*")
             if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm")]
    media.sort(key=lambda m: -m["ts"])
    return {"projects": sorted(projects, key=lambda p: -p["updated"]), "media": media[:120]}


# --- catalogue & statistiques -------------------------------------------------
@app.get("/api/products")
def products():
    return products_overview()


@app.get("/api/stats")
def stats(site: str = "", days: int = 7):
    days = max(1, min(days, 90))
    return analytics.site_stats(site, days) if site else {"sites": analytics.all_sites_summary(days)}


# --- ventes -------------------------------------------------------------------
_sales_cache: dict = {"ts": 0, "data": None}


@app.get("/api/sales")
async def sales():
    out = {"payment_links": db.q("SELECT * FROM payment_links ORDER BY id DESC"),
           "sales": db.q("SELECT * FROM sales ORDER BY ts DESC LIMIT 50"),
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
    targets = mentions(text) or ["Nexus"]  # sans mention, le routeur aiguille la demande
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
    if d.approve and (a["amount_eur"] or 0) > 0:
        free = budget.summary()["free_to_spend_eur"]
        if a["amount_eur"] > free:
            raise HTTPException(400, f"Cette dépense ({a['amount_eur']} €) dépasse ton argent disponible ({free:.2f} €).")
        db.x("INSERT INTO ledger (ts, kind, amount_eur, label, source, approval_id) VALUES (?,?,?,?,?,?)",
             (time.time(), "dépense", a["amount_eur"], a["title"], f"validation #{aid}", aid))
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


@app.get("/public/a.js")
def analytics_js():
    return FileResponse(STATIC / "analytics.js", media_type="application/javascript")


@app.post("/public/t")
async def track(request: Request):
    try:
        d = json.loads(await request.body())
    except ValueError:
        raise HTTPException(400)
    if not isinstance(d, dict):
        raise HTTPException(400)
    ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
    if not (_rate_ok(f"t:{ip}", 300, 3600) and _rate_ok("t:all", 20000, 3600)):
        return Response(status_code=204)
    analytics.record(str(d.get("site", "")), str(d.get("path", "")), str(d.get("event", "")),
                     str(d.get("visitor", "")), str(d.get("ref", "")), str(d.get("utm", "")), str(d.get("device", "")))
    return Response(status_code=204)


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


# --- pour Patron : questions & tâches ------------------------------------------
@app.get("/api/owner")
def owner_items():
    qs = db.q("SELECT * FROM owner_questions ORDER BY (answer IS NULL) DESC, id DESC LIMIT 60")
    for x in qs:
        x["options"] = json.loads(x["options"] or "[]")
    ts = db.q("SELECT * FROM owner_tasks ORDER BY done, CASE priority WHEN 'haute' THEN 0 WHEN 'normale' THEN 1 "
              "ELSE 2 END, id DESC LIMIT 80")
    return {"questions": qs, "tasks": ts}


class Answer(BaseModel):
    answer: str


@app.post("/api/questions/{qid}")
def answer_question(qid: int, a: Answer):
    rows = db.q("SELECT * FROM owner_questions WHERE id=?", (qid,))
    if not rows or not a.answer.strip():
        raise HTTPException(400)
    qrow = rows[0]
    db.x("UPDATE owner_questions SET answer=?, answered_ts=? WHERE id=?", (a.answer.strip()[:4000], time.time(), qid))
    db.post_message(OWNER, f"💬 Réponse à la question #{qid} ({qrow['question'][:120]}) : {a.answer.strip()}")
    scheduler.wake(qrow["agent"], f"{OWNER} a répondu à ta question #{qid} « {qrow['question'][:200]} » : {a.answer[:1000]}")
    return {"ok": True}


@app.post("/api/owner_tasks/{tid}")
def toggle_task(tid: int, done: bool):
    rows = db.q("SELECT * FROM owner_tasks WHERE id=?", (tid,))
    if not rows:
        raise HTTPException(404)
    db.x("UPDATE owner_tasks SET done=?, done_ts=? WHERE id=?", (1 if done else 0, time.time() if done else None, tid))
    if done:
        db.post_message(OWNER, f"✔️ Fait : {rows[0]['title']}")
        scheduler.wake(rows[0]["agent"], f"{OWNER} a fait la tâche #{tid} « {rows[0]['title']} »")
    return {"ok": True}


# --- workflows, boîte à outils, compétences ------------------------------------
@app.get("/api/jobs")
def jobs():
    out = db.q("SELECT * FROM jobs ORDER BY (status='en cours') DESC, id DESC LIMIT 40")
    for j in out:
        j["tasks"] = db.q("SELECT * FROM tasks WHERE job_id=? ORDER BY idx", (j["id"],))
    return out


@app.get("/api/toolbox")
def toolbox_api():
    return {"tools": [{"name": n, "desc": d, "path": f"outils/{n}.py"} for n, d in toolbox()],
            "skills": [{"name": n, "desc": d, "path": f"competences/{n}.md"} for n, d in skills()]}


# --- argent : budget, dépenses, profil investisseur, stratégie -----------------
@app.get("/api/budget")
async def budget_api():
    strategy = budget.strategy()
    return {"summary": budget.summary(), "ledger": db.q("SELECT * FROM ledger ORDER BY id DESC LIMIT 100"),
            "profile": budget.investor_profile(), "strategy": strategy,
            "strategy_ts": float(db.get_setting("strategy_ts", "0") or 0), "usd_eur": USD_EUR}


class BudgetSettings(BaseModel):
    initial_eur: float
    api_budget_eur: float
    api_days: float


@app.post("/api/budget/settings")
def budget_settings(b: BudgetSettings):
    if b.initial_eur < 0 or b.api_budget_eur < 0 or b.api_days < 1 or b.api_budget_eur > b.initial_eur:
        raise HTTPException(400, "valeurs invalides (la part IA doit être ≤ au budget total)")
    db.set_setting("budget_initial_eur", str(b.initial_eur))
    db.set_setting("api_budget_eur", str(b.api_budget_eur))
    db.set_setting("api_days", str(b.api_days))
    db.post_message(OWNER, f"💰 Budget mis à jour : {b.initial_eur:.0f} € au total, dont {b.api_budget_eur:.0f} € "
                           f"pour l'IA sur {b.api_days:.0f} jours.")
    return {"ok": True}


class LedgerEntry(BaseModel):
    kind: str
    amount_eur: float
    label: str


@app.post("/api/ledger")
def add_ledger(e: LedgerEntry):
    if e.kind not in ("dépense", "revenu") or e.amount_eur <= 0 or not e.label.strip():
        raise HTTPException(400)
    db.x("INSERT INTO ledger (ts, kind, amount_eur, label, source) VALUES (?,?,?,?,?)",
         (time.time(), e.kind, e.amount_eur, e.label.strip()[:200], OWNER))
    return {"ok": True}


@app.delete("/api/ledger/{lid}")
def del_ledger(lid: int):
    db.x("DELETE FROM ledger WHERE id=? AND source=?", (lid, OWNER))
    return {"ok": True}


@app.post("/api/profile")
async def save_profile(request: Request):
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(400)
    clean = {str(k)[:60]: str(v)[:500] for k, v in data.items() if str(v).strip()}
    db.set_setting("investor_profile", json.dumps(clean, ensure_ascii=False))
    db.post_message(OWNER, "🧾 J'ai rempli mon profil investisseur. @Wolf, mets à jour ma stratégie.")
    scheduler.wake("Wolf", f"{OWNER} a rempli son profil investisseur : rédige ou mets à jour sa stratégie (write_strategy)")
    return {"ok": True}


# --- assistant de démarrage -----------------------------------------------------
def _setup_allowed(request: Request) -> None:
    """Sans mot de passe d'appli, la configuration ne se modifie que depuis l'ordinateur lui-même."""
    if not PASSWORD and (request.client is None or request.client.host not in ("127.0.0.1", "::1", "localhost")):
        raise HTTPException(403, "Définis d'abord un mot de passe d'appli depuis l'ordinateur qui fait tourner Fusée.")


@app.get("/api/setup")
def setup_state(request: Request):
    cur = setup_mod.current()
    return {"values": cur, "needs_key": not cur["ANTHROPIC_API_KEY"]["set"],
            "local": request.client is not None and request.client.host in ("127.0.0.1", "::1", "localhost"),
            "has_password": bool(PASSWORD)}


@app.post("/api/setup/save")
async def setup_save(request: Request):
    _setup_allowed(request)
    data = await request.json()
    changed = setup_mod.save(data if isinstance(data, dict) else {})
    return {"ok": True, "changed": changed}


@app.post("/api/setup/test")
async def setup_test(request: Request):
    _setup_allowed(request)
    data = await request.json()
    return await asyncio.to_thread(setup_mod.test, str(data.get("service", "")), data.get("values") or {})


@app.post("/api/setup/restart")
async def setup_restart(request: Request):
    _setup_allowed(request)
    asyncio.get_running_loop().call_later(1.0, setup_mod.restart)
    return {"ok": True}


# --- calendrier de contenus -------------------------------------------------------
@app.get("/api/content")
def content_list():
    rows = db.q("SELECT * FROM content WHERE status!='abandonné' ORDER BY (status='prêt') DESC, day, id LIMIT 100")
    for r in rows:
        m = re.search(r"utm_source=([^&]+)", r["link"] or "")
        r["visits"] = (db.q("SELECT COUNT(DISTINCT visitor) n FROM events WHERE utm=? AND event='vue' AND ts>=?",
                            (m.group(1), r["posted_ts"]))[0]["n"] if m and r["posted_ts"] else None)
    return rows


@app.post("/api/content/{cid}")
def content_status(cid: int, status: str):
    rows = db.q("SELECT * FROM content WHERE id=?", (cid,))
    if not rows or status not in ("posté", "abandonné", "prêt"):
        raise HTTPException(400)
    db.x("UPDATE content SET status=?, posted_ts=? WHERE id=?", (status, time.time() if status == "posté" else None, cid))
    if status == "posté":
        db.post_message(OWNER, f"📤 J'ai posté la publication #{cid} sur {rows[0]['channel']}.")
        scheduler.wake(rows[0]["agent"], f"{OWNER} a posté la publication #{cid} ({rows[0]['channel']}) : suis ses "
                                         "visites dans les jours qui viennent (list_content)")
    return {"ok": True}
