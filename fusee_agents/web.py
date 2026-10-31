"""Serveur du tableau de bord : API JSON + page web."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import db
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
