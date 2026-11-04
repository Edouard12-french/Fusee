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

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analytics, briefing, budget, db, integrations, knowledge, mailbox, outreach, parent, runner
from . import setup as setup_mod
from .agents import (BY_NAME, OWNER, PROFILE_LABELS, TEAM, add_agent, agent_settings, make_custom, owner_profile,
                     save_team_config, team_config)
from .config import PLAN, PUBLIC_URL, USD_EUR, WORKSPACE, model_for
from . import notify as notify_mod
from .notify import notify
from .scheduler import scheduler
from .tools import _safe_path, deliver_reply, mentions, products_overview, skills, toolbox

STATIC = Path(__file__).parent / "static"
PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")


# Clé enregistrée dans 🚀 Démarrage → ce qu'on annonce à l'équipe, et les demandes qu'on peut clore
CONNECTED = {
    "STRIPE_SECRET_KEY": ("Stripe (paiements)", re.compile(r"stripe", re.I)),
    "NETLIFY_TOKEN": ("Netlify (mise en ligne des sites)", re.compile(r"netlify", re.I)),
    "EMAIL_PASSWORD": ("la boîte e-mail", re.compile(r"\b(e-?mail|smtp|imap|gmail)\b", re.I)),
}


def close_connected_requests(keys, announce: bool) -> int:
    """Quand une clé est branchée, les agents ne doivent plus la demander : on clôt leurs besoins et les tâches
    de Patron qui la réclament, et on le dit dans le groupe. Renvoie le nombre de demandes closes."""
    closed, labels = 0, []
    for key in keys:
        if key not in CONNECTED or not os.getenv(key, "").strip():
            continue
        label, rx = CONNECTED[key]
        n = 0
        for r in db.q("SELECT id, need FROM needs WHERE status != 'résolu'"):
            if rx.search(r["need"] or ""):
                db.x("UPDATE needs SET status='résolu', result=?, resolved_ts=? WHERE id=?",
                     (f"fait : {OWNER} a branché {label} dans 🚀 Démarrage", time.time(), r["id"]))
                n += 1
        for r in db.q("SELECT id, title, steps FROM owner_tasks WHERE done=0"):
            if rx.search((r["title"] or "") + " " + (r["steps"] or "")):
                db.x("UPDATE owner_tasks SET done=1, done_ts=? WHERE id=?", (time.time(), r["id"]))
                n += 1
        closed += n
        if announce or n:
            labels.append(label)
    if labels:
        db.post_message("Fusée", f"✅ {' et '.join(labels)} : c'est branché ({OWNER} a enregistré la clé dans 🚀 "
                                 "Démarrage). Ne lui redemandez plus cette clé et utilisez-le directement — en "
                                 "demandant toujours avant de publier ou de créer un lien de paiement.")
    return closed


@asynccontextmanager
async def lifespan(app: FastAPI):
    knowledge.install()
    close_connected_requests(CONNECTED, announce=False)  # clés déjà là : on clôt les vieilles demandes
    scheduler.start()
    yield


app = FastAPI(title="Fusée", lifespan=lifespan)
# Routes publiques (chat des sites, statistiques, désinscription) : servies AUSSI par un petit serveur séparé
# (public_app, port PUBLIC_PORT) — c'est le seul à exposer sur internet. L'application elle-même ne l'est jamais.
public = APIRouter()


@app.middleware("http")
async def guard(request: Request, call_next):
    """/public/* est ouvert (chat des sites, CORS). Le reste est protégé par DASHBOARD_PASSWORD s'il est défini."""
    if request.url.path.startswith("/public/"):
        resp = Response() if request.method == "OPTIONS" else await call_next(request)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp
    tailnet_user = (request.headers.get("tailscale-user-login") and request.client is not None
                    and request.client.host in ("127.0.0.1", "::1"))  # passé par « tailscale serve » (privé)
    if PASSWORD and not tailnet_user:
        try:
            _, pwd = base64.b64decode(request.headers.get("authorization", "")[6:]).decode().split(":", 1)
        except Exception:  # noqa: BLE001
            pwd = ""
        if not secrets.compare_digest(pwd.encode(), PASSWORD.encode()):
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Fusee"'})
    return await call_next(request)


# --- application (PWA) ------------------------------------------------------
NO_CACHE = {"Cache-Control": "no-cache"}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers=NO_CACHE)  # après une mise à jour : nouvelle version tout de suite


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return FileResponse(STATIC / "sw.js", media_type="application/javascript", headers=NO_CACHE)


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
               "tier": a.tier, "model": model_for(a.tier)[0],
               "interval_min": agent_settings(a.name).get("interval_min", a.interval_min),
               "learned": agent_settings(a.name).get("extra", ""),
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
        "unread_dms": {r["agent"]: r["n"] for r in db.q(
            "SELECT agent, COUNT(*) n FROM dms WHERE sender!=? AND read=0 GROUP BY agent", (OWNER,))},
        "profile_done": bool(owner_profile().get("prenom")),
        "paused": scheduler.paused,
        "work": _work_state(),
        "directive": db.get_setting("directive", ""),
        "pending_approvals": db.q("SELECT COUNT(*) n FROM approvals WHERE status='en attente'")[0]["n"],
        "unread_notifications": db.q("SELECT COUNT(*) n FROM notifications WHERE read=0")[0]["n"],
        "latest_notification": (db.q("SELECT id, kind, title, body FROM notifications ORDER BY id DESC LIMIT 1") or [None])[0],
        "waiting_contacts": len(db.unanswered_contacts()),
        "support_mode": db.get_setting("support_mode", "auto"),
        "browser_enabled": db.get_setting("browser_enabled", "1") == "1",
        "capabilities": {"email": mailbox.ENABLED, "netlify": bool(integrations.NETLIFY_TOKEN),
                         "stripe": bool(integrations.STRIPE_KEY), "public_url": PUBLIC_URL,
                         "push": bool(os.getenv("NTFY_TOPIC")), "mac_notifications": notify_mod.mac_available()},
    }


@app.get("/api/activity")
def activity(agent: str | None = None, limit: int = 150):
    return db.activity(agent, limit)


@app.get("/api/ideas")
def ideas():
    """Le classement des business, du meilleur au moins bon (les idées abandonnées à la fin)."""
    gone = db.q("SELECT * FROM ideas WHERE status = 'abandonnée' ORDER BY id DESC LIMIT 50")
    return {"ranked": briefing.ranked(200), "abandoned": gone, "briefing": briefing.settings(),
            "last_briefing": (db.q("SELECT id, ts, title FROM reports WHERE title LIKE '%Briefing%' "
                                   "ORDER BY id DESC LIMIT 1") or [None])[0]}


@app.post("/api/briefing")
async def briefing_now():  # async : le briefing de secours est une tâche de la boucle principale
    """Patron veut le briefing tout de suite."""
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        raise HTTPException(400, "Il faut d'abord la clé API (onglet 🚀 Démarrage).")
    db.post_message(OWNER, "📋 @Atlas, fais-moi le briefing maintenant : le classement des meilleurs business, "
                           "le meilleur en détail et le choix en QCM.")
    scheduler.briefing()
    return {"ok": True, "fallback_min": briefing.FALLBACK_AFTER_S // 60}


@app.post("/api/briefing_settings")
async def briefing_settings(request: Request):
    d = await request.json()
    if "enabled" in d:
        db.set_setting("briefing_enabled", "1" if d["enabled"] else "0")
    if "hour" in d and 0 <= int(d["hour"]) <= 23:
        db.set_setting("briefing_hour", str(int(d["hour"])))
        db.set_setting("briefing_last", "")  # la nouvelle heure compte dès aujourd'hui
    return briefing.settings()


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
    content: str = ""
    attachments: list[str] = []  # fichiers déjà envoyés avec /api/upload (dans de-patron/)


UPLOAD_DIR = "de-patron"
UPLOAD_MAX = 15_000_000  # 15 Mo par fichier
UPLOAD_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".pdf", ".txt", ".md", ".csv", ".json",
              ".docx", ".xlsx", ".pptx", ".mp3", ".m4a", ".wav", ".mp4", ".mov", ".zip"}


class Upload(BaseModel):
    name: str
    data: str  # contenu en base64 (ou « data:…;base64,… »)


@app.post("/api/upload")
def upload(u: Upload):
    """Patron envoie une image ou un fichier : il est rangé dans workspace/de-patron/<date>/."""
    import base64
    import binascii
    import unicodedata
    stem, dot, ext = u.name.rpartition(".")
    ext = ("." + ext.lower()) if dot else ""
    if ext not in UPLOAD_EXT:
        raise HTTPException(400, f"Type de fichier non accepté ({ext or 'sans extension'}). Images, PDF, textes, "
                                 "documents Office, sons, vidéos ou ZIP.")
    try:
        raw = base64.b64decode(u.data.split(",", 1)[-1], validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "fichier illisible")
    if len(raw) > UPLOAD_MAX:
        raise HTTPException(400, "Fichier trop lourd (15 Mo maximum).")
    safe = unicodedata.normalize("NFKD", stem or "fichier").encode("ascii", "ignore").decode()
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", safe).strip("-")[:50] or "fichier"
    folder = WORKSPACE / UPLOAD_DIR / time.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{time.strftime('%H%M%S')}-{safe}{ext}"
    n = 1
    while dest.exists():
        dest, n = folder / f"{time.strftime('%H%M%S')}-{safe}-{n}{ext}", n + 1
    dest.write_bytes(raw)
    return {"path": str(dest.relative_to(WORKSPACE)), "size": len(raw)}


def _owner_files(paths: list[str]) -> list[str]:
    """Seulement des fichiers envoyés par Patron (de-patron/), qui existent vraiment."""
    out = []
    for p in paths[:8]:
        try:
            full = _safe_path(p)
        except ValueError:
            continue
        if full.is_file() and str(p).startswith(UPLOAD_DIR + "/"):
            out.append(str(p))
    return out


def _files_note(files: list[str]) -> str:
    return (f" [pièce(s) jointe(s) de {OWNER} : {', '.join(files)} — regarde-les avec view_file]" if files else "")


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
    text, files = msg.content.strip(), _owner_files(msg.attachments)
    if not text and not files:
        raise HTTPException(400, "message vide")
    text = text or "📎 Regardez ce que je vous envoie."
    db.post_message(OWNER, text, json.dumps({"files": files, "links": []}) if files else "")
    targets = mentions(text) or ["Nexus"]  # sans mention, le routeur aiguille la demande
    for t in targets:
        scheduler.wake(t, f"message de {OWNER} : {text[:500]}{_files_note(files)}")
    return {"ok": True, "woken": targets}


@app.post("/api/meeting")
async def meeting(msg: Msg):
    """Réunion : tous les agents (ou ceux mentionnés) répondent en même temps, en quelques secondes."""
    text = msg.content.strip()
    if not text:
        raise HTTPException(400, "message vide")
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        raise HTTPException(400, "Il faut d'abord la clé API (onglet 🚀 Démarrage).")
    if budget.api_exhausted() or budget.owner_exhausted():
        raise HTTPException(400, "Même la rallonge du jour est utilisée : la réunion reprendra demain (ou augmente le "
                                 "budget dans 💰 Argent).")
    named = [n for n in mentions(text) if n in BY_NAME]
    pool = [BY_NAME[n] for n in named] if named and len(named) < len(BY_NAME) else list(TEAM)
    agents = [a for a in pool if agent_settings(a.name).get("enabled", True) is not False]
    mid = db.post_message(OWNER, f"🎙️ {text}")
    budget.note_owner_active()
    asyncio.create_task(runner.run_meeting(agents, text, scheduler.wake))
    return {"ok": True, "message_id": mid, "agents": [a.name for a in agents]}


@app.post("/api/diagnostic")
async def diagnostic():
    """Mini-requête réelle par agent : vérifie clé, modèles, instructions et outils d'un coup."""
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        raise HTTPException(400, "Il faut d'abord la clé API (étape 1), puis redémarrer Fusée.")
    results = await runner.diagnose(list(TEAM))
    ok = sum(r["ok"] for r in results)
    db.log("système", "diagnostic", f"diagnostic : {ok}/{len(results)} agents OK", json.dumps(results, ensure_ascii=False, indent=1))
    return {"ok": ok == len(results), "results": results}


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
    notify("alerte", "Test des notifications", "Si tu vois ce message, les notifications de Fusée marchent ! 🎉",
           priority="urgent")  # « urgent » : passe même pendant les heures de silence
    return {"ok": True, "mac": notify_mod.mac_available(), "phone": bool(notify_mod.NTFY_TOPIC)}


@app.get("/api/notif_settings")
def notif_settings():
    return {**notify_mod.settings(), "mac_available": notify_mod.mac_available(), "phone": bool(notify_mod.NTFY_TOPIC),
            "quiet_now": notify_mod.is_quiet()}


@app.get("/api/costs")
def costs():
    """Où part l'argent de l'IA aujourd'hui : par agent, recherches web, nuit des agents."""
    from .config import WEB_SEARCH_COST
    rows = []
    for r in db.usage_today():
        a = BY_NAME.get(r["agent"])
        rows.append({"agent": r["agent"], "emoji": a.emoji if a else "🤖", "model": model_for(a.tier)[0] if a else "",
                     "cost_eur": r["cost_usd"] * USD_EUR, "searches": r["searches"], "cycles": r["cycles"]})
    n = db.searches_today()
    return {"plan": PLAN, "agents": rows, "spent_today_eur": db.cost_today() * USD_EUR,
            "daily_cap_eur": budget.daily_cap_usd() * USD_EUR, "searches": n, "search_limit": budget.web_search_limit(),
            "search_cost_eur": n * WEB_SEARCH_COST * USD_EUR, "reserve_pct": budget.owner_reserve_pct(),
            "owner_cap_eur": budget.owner_cap_usd() * USD_EUR}


def _work_state() -> dict:
    on, planned = budget.work_authorized(), budget.work_scheduled()
    return {"authorized": on, "until": budget.work_until() if on or planned else 0,
            "label": budget.when_label(budget.work_until()) if on or planned else "",
            "scheduled": planned, "from_label": budget.when_label(budget.work_from()) if planned else "",
            "range_label": budget.range_label(budget.work_from(), budget.work_until()) if planned else "",
            "reserve_pct": budget.owner_reserve_pct()}


class WorkReq(BaseModel):
    choice: str = ""  # "nuit", "2h", "24h", "2j", "plan", "stop" (vide = seulement régler la réserve)
    day: str = "demain"  # pour « plan » : "aujourdhui" ou "demain"
    h_from: int = 8
    h_to: int = 17
    reserve: int | None = None  # % du budget du jour gardé pour Patron


@app.post("/api/work")
def set_work(w: WorkReq):
    """Patron autorise l'équipe à travailler seule pendant un moment (sinon elle attend qu'il parle)."""
    if w.reserve is not None:
        if not 10 <= w.reserve <= 90:
            raise HTTPException(400, "réserve entre 10 et 90 %")
        db.set_setting("owner_reserve_pct", str(int(w.reserve)))
        if not w.choice:
            return _work_state()
    if w.choice == "plan":
        if not (0 <= w.h_from <= 23 and 0 <= w.h_to <= 23) or w.h_from == w.h_to:
            raise HTTPException(400, "heures invalides")
        start, end = budget.planned_window(w.day, w.h_from, w.h_to)
        if end <= time.time():
            raise HTTPException(400, "cette période est déjà passée")
        label = scheduler.authorize(end, max(start, time.time()))
        when_txt = budget.range_label(start, end) if start > time.time() else f"maintenant → {label}"
        db.post_message(OWNER, f"📅 Je vous autorise à travailler seuls : {when_txt}. Gardez "
                               f"{budget.owner_reserve_pct()} % du budget du jour pour quand je vous parle, et "
                               "demandez-moi toujours avant de publier.")
        return _work_state()
    if w.choice == "stop":
        budget.stop_work()
        db.post_message(OWNER, "⏹️ Stop : maintenant vous travaillez seulement quand je vous parle.")
        return _work_state()
    hours = {"2h": 2, "24h": 24, "2j": 48}.get(w.choice)
    if w.choice == "nuit":
        until = budget.next_morning(7).timestamp()
    elif hours:
        until = time.time() + hours * 3600
    else:
        raise HTTPException(400, "choix inconnu")
    label = scheduler.authorize(until)
    db.post_message(OWNER, f"▶️ Je vous autorise à travailler seuls jusqu'à {label}. Avancez sur vos projets "
                           "(et demandez-moi toujours avant de publier).")
    return _work_state()


@app.post("/api/notif_settings")
async def save_notif_settings(request: Request):
    d = await request.json()
    for k in ("mac", "sound", "quiet"):
        if k in d:
            db.set_setting(f"notif_{k}", "1" if d[k] else "0")
    for k in ("quiet_from", "quiet_to"):
        if k in d and 0 <= int(d[k]) <= 23:
            db.set_setting(f"notif_{k}", str(int(d[k])))
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
    parent_pin: str = ""  # code parent, pour les demandes qui ont besoin de l'accord d'un parent


@app.post("/api/approvals/{aid}")
async def decide(aid: int, d: Decision):
    rows = db.q("SELECT * FROM approvals WHERE id=?", (aid,))
    if not rows:
        raise HTTPException(404)
    a = rows[0]
    if a["status"] != "en attente":
        raise HTTPException(409, "déjà décidée")
    status = "acceptée" if d.approve else "refusée"
    by_parent = False
    if d.approve and a.get("needs_parent"):
        if not parent.is_set():
            raise HTTPException(403, "Cette demande a besoin de l'accord d'un parent : il doit d'abord créer son code "
                                     "parent dans ⚙️ Réglages → 👪 Accord d'un parent.")
        if not parent.check(d.parent_pin):
            raise HTTPException(403, "Trop d'essais : réessaie dans 15 minutes." if parent.locked()
                                else "Code parent incorrect.")
        by_parent = True
    if d.approve and (a["amount_eur"] or 0) > 0:
        free = budget.summary()["free_to_spend_eur"]
        if a["amount_eur"] > free:
            raise HTTPException(400, f"Cette dépense ({a['amount_eur']} €) dépasse ton argent disponible ({free:.2f} €).")
        db.x("INSERT INTO ledger (ts, kind, amount_eur, label, source, approval_id) VALUES (?,?,?,?,?,?)",
             (time.time(), "dépense", a["amount_eur"], a["title"], f"validation #{aid}", aid))
    if a["kind"] == "prospection":
        camp_id = json.loads(a["payload"])["campaign_id"]
        db.x("UPDATE campaigns SET status=? WHERE id=?", ("active" if d.approve else "refusée", camp_id))
    if a["kind"] == "équipe" and d.approve:
        spec = json.loads(a["payload"])
        if spec["name"] not in BY_NAME:
            cfg = team_config()
            cfg.setdefault("custom_agents", []).append(spec)
            save_team_config(cfg)
            new = make_custom(spec)
            add_agent(new)
            scheduler.add(new)
    if a["kind"] == "réponse client" and d.approve:
        try:
            await deliver_reply(json.loads(a["payload"])["contact_id"], a["details"], a["agent"])
        except RuntimeError as e:
            raise HTTPException(400, str(e))
    decided_by = parent.sender() if by_parent else OWNER
    db.x("UPDATE approvals SET status=?, response=?, decided_by=?, decided_ts=CAST(strftime('%s','now') AS REAL) "
         "WHERE id=?", (status, d.comment.strip(), decided_by, aid))
    emoji = "✅" if d.approve else "❌"
    db.post_message(decided_by, f"{emoji} Demande #{aid} {status} : {a['title']}"
                    + (" — accord du parent donné avec son code" if by_parent else "")
                    + (f" — {d.comment.strip()}" if d.comment.strip() else ""))
    for t in {a["agent"], "Atlas"}:
        scheduler.wake(t, f"{OWNER} a {'accepté' if d.approve else 'refusé'} la demande #{aid} « {a['title']} »"
                          + (f" — ✅ ACCORD PARENT de {parent.name()} vérifié (code parent)" if by_parent else "")
                          + (f" avec ce commentaire : {d.comment}" if d.comment else ""))
    return {"ok": True}


@app.get("/api/parent")
def parent_state():
    return {"set": parent.is_set(), "name": parent.name() if parent.is_set() else "", "locked": parent.locked()}


class ParentSetup(BaseModel):
    name: str
    pin: str
    old_pin: str = ""


@app.post("/api/parent/setup")
def parent_setup(p: ParentSetup):
    first = not parent.is_set()
    try:
        parent.setup(p.name, p.pin, p.old_pin)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if first:
        db.post_message("Fusée", f"👪 {parent.name()} a créé son code parent. Pour ce qui a besoin de l'accord d'un "
                                 "parent, utilisez request_approval avec parent=true : il validera avec son code.")
    return parent_state()


class ParentMsg(BaseModel):
    pin: str
    content: str


@app.post("/api/parent/message")
def parent_message(m: ParentMsg):
    """Le parent écrit à l'équipe EN SON NOM (badge 👪), après avoir tapé son code."""
    text = m.content.strip()
    if not text:
        raise HTTPException(400, "message vide")
    if not parent.check(m.pin):
        raise HTTPException(403, "Trop d'essais : réessaie dans 15 minutes." if parent.locked() else "Code parent incorrect.")
    db.post_message(parent.sender(), text)
    targets = mentions(text) or ["Atlas"]
    for t in targets:
        scheduler.wake(t, f"message du parent {parent.name()} (code parent vérifié) : {text[:500]}")
    return {"ok": True, "woken": targets}


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


@public.get("/public/a.js")
def analytics_js():
    return FileResponse(STATIC / "analytics.js", media_type="application/javascript")


@public.post("/public/t")
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


@public.get("/public/chat.js")
def chat_js():
    return FileResponse(STATIC / "chat-widget.js", media_type="application/javascript")


@public.post("/public/chat/send")
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
    voice = data.get("voice") is True  # dicté au micro : la réponse sera lue à voix haute chez le visiteur
    db.add_conv(cid, "chat", "in", f"🎤 {text}" if voice else text, subject=site)
    if is_new:
        notify("client", f"{'🎤' if voice else '💬'} Nouveau visiteur sur le chat {site}", text[:500], priority="low")
    scheduler.wake("Iris", f"message {'VOCAL ' if voice else ''}chat du contact #{cid} sur le site {site}")
    return {"ok": True}


@public.get("/public/chat/poll")
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
    approvals = db.q("SELECT * FROM approvals WHERE status='en attente' ORDER BY id")
    for r in approvals:
        try:
            r["attachments"] = json.loads(r["payload"]) if r["kind"] != "réponse client" and r["payload"] else {}
        except ValueError:
            r["attachments"] = {}
        if r["kind"] in ("équipe", "prospection"):
            r["attachments"] = {}
    in_progress = db.q("SELECT id, agent, need, urgency FROM needs WHERE status='nouveau' ORDER BY id")
    return {"questions": qs, "tasks": ts, "approvals": approvals, "needs_in_progress": in_progress}


class Answer(BaseModel):
    answer: str


@app.post("/api/questions/{qid}")
def answer_question(qid: int, a: Answer):
    rows = db.q("SELECT * FROM owner_questions WHERE id=?", (qid,))
    if not rows or not a.answer.strip():
        raise HTTPException(400)
    qrow = rows[0]
    db.x("UPDATE owner_questions SET answer=?, answered_ts=? WHERE id=?", (a.answer.strip()[:4000], time.time(), qid))
    for n in json.loads(qrow.get("need_ids") or "[]"):
        db.x("UPDATE needs SET status='résolu', result=?, resolved_ts=? WHERE id=?", (a.answer.strip()[:4000], time.time(), n))
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
        for n in json.loads(rows[0].get("need_ids") or "[]"):
            db.x("UPDATE needs SET status='résolu', result='fait par Patron', resolved_ts=? WHERE id=?", (time.time(), n))
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
    applied = False
    if "ANTHROPIC_API_KEY" in changed:  # clé appliquée tout de suite + l'équipe se réveille
        runner.reload_client()
        for a in TEAM:
            st = (db.get_states().get(a.name) or {}).get("status", "")
            if "clé API" in st or st.startswith("erreur"):
                db.set_state(a.name, status="en attente")
            if (agent_settings(a.name).get("interval_min", a.interval_min) or 0) > 0:
                scheduler.wake(a.name, "la clé API vient d'être ajoutée : l'équipe démarre, présente-toi et commence")
        applied = True
    if "NETLIFY_TOKEN" in changed or "STRIPE_SECRET_KEY" in changed:  # sites et paiements : tout de suite, sans redémarrer
        integrations.NETLIFY_TOKEN = os.getenv("NETLIFY_TOKEN", "").strip()
        integrations.STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
        applied = True
    close_connected_requests([k for k in changed if k in CONNECTED], announce=True)
    return {"ok": True, "changed": changed, "applied": applied}


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


# --- prospection ------------------------------------------------------------------
@app.get("/api/outreach")
def outreach_api():
    camps = db.q("SELECT * FROM campaigns ORDER BY (status='active') DESC, id DESC LIMIT 30")
    for c in camps:
        c["stats"] = outreach.stats(c["id"])
        c["prospects"] = db.q("SELECT * FROM prospects WHERE campaign_id=? ORDER BY (status='à envoyer par Patron') DESC, "
                              "id DESC LIMIT 200", (c["id"],))
    return {"campaigns": camps, "sent_today": outreach.sent_today(), "daily_limit": outreach.DAILY_LIMIT,
            "mail_enabled": mailbox.ENABLED, "suppressed": db.q("SELECT COUNT(*) n FROM suppression")[0]["n"]}


@app.post("/api/campaigns/{cid}")
def campaign_status(cid: int, status: str):
    c = db.q("SELECT * FROM campaigns WHERE id=?", (cid,))
    if not c or status not in ("active", "en pause", "terminée") or c[0]["status"] in ("refusée", "en attente de validation"):
        raise HTTPException(400, "changement impossible")
    db.x("UPDATE campaigns SET status=? WHERE id=?", (status, cid))
    db.post_message(OWNER, f"🎯 Campagne « {c[0]['name']} » : {status}.")
    return {"ok": True}


@app.post("/api/prospects/{pid}/sent")
def prospect_sent(pid: int):
    """Patron a envoyé lui-même un brouillon (boîte mail non configurée)."""
    p = db.q("SELECT * FROM prospects WHERE id=? AND status='à envoyer par Patron'", (pid,))
    if not p:
        raise HTTPException(400)
    db.add_conv(p[0]["contact_id"], "email", "out", p[0]["message"], subject=p[0]["subject"], agent="prospection (Patron)")
    db.x("UPDATE prospects SET status='contacté', sends=1, last_sent_ts=? WHERE id=?", (time.time(), pid))
    return {"ok": True}


@app.post("/api/prospects/{pid}/stop")
def prospect_stop(pid: int):
    p = db.q("SELECT email FROM prospects WHERE id=?", (pid,))
    if not p:
        raise HTTPException(404)
    outreach.suppress(p[0]["email"], f"retiré par {OWNER}")
    return {"ok": True}


@public.get("/public/stop", response_class=HTMLResponse)
def public_stop(e: str = "", t: str = ""):
    """Lien de désinscription des e-mails de prospection (sans mot de passe)."""
    ok = bool(e) and outreach.check_stop_token(e, t)
    if ok:
        outreach.suppress(e, "lien de désinscription")
        db.post_message("Iris", f"🚫 {e} s'est désinscrit de la prospection (respecté pour toujours).")
    msg = ("C'est noté : vous ne recevrez plus aucun message de notre part." if ok else
           "Lien invalide. Répondez simplement STOP à notre e-mail et nous ne vous contacterons plus.")
    return f"""<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Désinscription</title><body style="font-family:system-ui;max-width:560px;margin:80px auto;padding:20px;text-align:center">
<h1>{"✅" if ok else "ℹ️"} Désinscription</h1><p>{msg}</p><p style="color:#666">Toutes nos excuses pour le dérangement.</p></body></html>"""


# --- discussion privée avec un agent -------------------------------------------------------------------
@app.get("/api/dm/{agent}")
def dm_get(agent: str):
    if agent not in BY_NAME:
        raise HTTPException(404)
    db.x("UPDATE dms SET read=1 WHERE agent=? AND sender!=?", (agent, OWNER))
    rows = runner.dm_thread(agent, 100)
    for r in rows:
        _msg(r)
    return {"messages": rows, "typing": db.get_states().get(agent, {}).get("status") == "en discussion privée"}


@app.post("/api/dm/{agent}")
async def dm_send(agent: str, msg: Msg):
    if agent not in BY_NAME:
        raise HTTPException(404)
    text, files = msg.content.strip(), _owner_files(msg.attachments)
    if not text and not files:
        raise HTTPException(400, "message vide")
    text = text or "📎 Regarde ce que je t'envoie."
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        raise HTTPException(400, "Il faut d'abord la clé API (onglet 🚀 Démarrage).")
    if budget.api_exhausted() or budget.owner_exhausted():
        raise HTTPException(400, "Même la rallonge du jour est utilisée : il te répondra demain (ou augmente le budget "
                                 "dans 💰 Argent).")
    db.x("INSERT INTO dms (ts, agent, sender, content, attachments, read) VALUES (?,?,?,?,?,1)",
         (time.time(), agent, OWNER, text, json.dumps({"files": files, "links": []}) if files else ""))
    budget.note_owner_active()
    asyncio.create_task(runner.dm_reply(BY_NAME[agent], scheduler.wake))
    return {"ok": True}


# --- se présenter à l'équipe ------------------------------------------------------------------------------
@app.get("/api/owner_profile")
def get_owner_profile():
    return {"profile": owner_profile(), "labels": PROFILE_LABELS}


@app.post("/api/owner_profile")
async def save_owner_profile(request: Request):
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(400)
    clean = {k: str(data.get(k, "")).strip()[:400] for k in PROFILE_LABELS if str(data.get(k, "")).strip()}
    first = not owner_profile().get("prenom")
    db.set_setting("owner_profile", json.dumps(clean, ensure_ascii=False))
    name = clean.get("appel") or clean.get("prenom") or OWNER
    if first and clean.get("prenom"):
        intro = f"👋 Salut l'équipe, c'est {name} !" + (f" J'habite vers {clean['ville']}." if clean.get("ville") else "") \
            + (f" J'aime : {clean['aime']}." if clean.get("aime") else "") + (f" Mon objectif : {clean['objectif']}." if clean.get("objectif") else "")
        db.post_message(OWNER, intro)
    return {"ok": True}


# --- notifications sur l'iPhone (Web Push) ------------------------------------------------------------
@app.get("/api/push")
def push_info():
    from . import webpush
    return {"key": webpush.public_key_b64(),
            "devices": [{"device": r["device"], "ts": r["ts"]} for r in webpush.subscriptions()]}


@app.post("/api/push/subscribe")
async def push_subscribe(request: Request):
    from . import webpush
    d = await request.json()
    try:
        webpush.add_subscription(d.get("subscription") or {}, str(d.get("device") or "appareil"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    await asyncio.to_thread(webpush.broadcast, "🔔 Notifications activées", "Fusée pourra te prévenir ici. 🚀", "/#settings")
    return {"ok": True}


@app.post("/api/push/forget")
def push_forget():
    db.x("DELETE FROM push_subs")
    return {"ok": True}


# --- serveur public séparé ------------------------------------------------------------------------------
app.include_router(public)
public_app = FastAPI(title="Fusée — public", docs_url=None, redoc_url=None, openapi_url=None)
public_app.include_router(public)


@public_app.middleware("http")
async def public_cors(request: Request, call_next):
    resp = Response() if request.method == "OPTIONS" else await call_next(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


# --- ouvrir Fusée sur l'iPhone / l'iPad : QR code de l'adresse privée ------------------------------------
TAILSCALE_DOWNLOAD = "https://tailscale.com/download"  # la page propose la bonne version (App Store sur iPhone/iPad)


@app.get("/api/qr")
def qr_code(target: str = Query("fusee", alias="for")):
    """QR code (SVG) à scanner avec l'appareil photo de l'iPhone ou de l'iPad : l'adresse privée de Fusée,
    ou (?for=tailscale) la page de téléchargement de Tailscale."""
    import io

    import qrcode
    import qrcode.image.svg
    if target == "tailscale":
        url = TAILSCALE_DOWNLOAD
    else:
        url = setup_mod._read().get("DASHBOARD_URL", os.getenv("DASHBOARD_URL", "")).strip()
        if not url.startswith("https://"):
            raise HTTPException(404, "adresse privée pas encore créée")
    buf = io.BytesIO()
    qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2).save(buf)
    return Response(buf.getvalue(), media_type="image/svg+xml")


@app.get("/api/device_url")
def device_url():
    return {"url": setup_mod._read().get("DASHBOARD_URL", os.getenv("DASHBOARD_URL", "")).strip()}
