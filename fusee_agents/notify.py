"""Notifications : enregistrées dans le tableau de bord + push sur le téléphone via ntfy (gratuit)."""
import asyncio
import json
import os
import urllib.request

from . import db

NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "").strip()
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "")


PRIORITIES = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5}


def _push(title: str, body: str, priority: str, tags: str) -> None:
    if not NTFY_TOPIC:
        return
    payload = {"topic": NTFY_TOPIC, "title": title[:200], "message": body[:4000],
               "priority": PRIORITIES.get(priority, 3), "tags": [tags]}
    if DASHBOARD_URL:
        payload["click"] = DASHBOARD_URL
    req = urllib.request.Request(NTFY_SERVER, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:  # noqa: BLE001 — une notif ratée ne doit rien casser
        db.log("système", "erreur", f"notification push échouée : {e}")


def notify(kind: str, title: str, body: str, priority: str = "default") -> None:
    """kind : validation | rapport | client | alerte. priority : min|low|default|high|urgent."""
    db.x("INSERT INTO notifications (ts, kind, title, body) VALUES (CAST(strftime('%s','now') AS REAL),?,?,?)",
         (kind, title, body[:4000]))
    tags = {"validation": "question", "rapport": "page_facing_up", "client": "envelope", "alerte": "warning"}.get(kind, "rocket")
    try:
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _push, title, body, priority, tags)
    except RuntimeError:
        _push(title, body, priority, tags)
