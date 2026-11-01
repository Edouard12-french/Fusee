"""Notifications de Fusée :
- enregistrées dans l'appli (onglet 🔔 Notifs + alerte dans la fenêtre ouverte) ;
- notifications natives du Mac (en haut à droite de l'écran), même fenêtre fermée ;
- et, en option, sur le téléphone via l'app gratuite ntfy."""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime

from . import db

NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "").strip()
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "")
PRIORITIES = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5}
ICONS = {"validation": "🛡️", "rapport": "📄", "client": "💬", "alerte": "🔔"}


def settings() -> dict:
    return {
        "mac": db.get_setting("notif_mac", "1") == "1",
        "sound": db.get_setting("notif_sound", "1") == "1",
        "quiet": db.get_setting("notif_quiet", "1") == "1",
        "quiet_from": int(db.get_setting("notif_quiet_from", "22")),
        "quiet_to": int(db.get_setting("notif_quiet_to", "8")),
    }


def is_quiet(now: datetime | None = None) -> bool:
    s = settings()
    if not s["quiet"]:
        return False
    h = (now or datetime.now()).hour
    a, b = s["quiet_from"], s["quiet_to"]
    return (a <= h or h < b) if a > b else (a <= h < b)


def mac_available() -> bool:
    return sys.platform == "darwin" and shutil.which("osascript") is not None


def _mac(title: str, body: str, sound: bool) -> None:
    """Notification native macOS. Le texte est passé en argument (pas d'injection possible dans le script)."""
    script = ['on run argv',
              'display notification (item 2 of argv) with title "Fusée 🚀" subtitle (item 1 of argv)'
              + (' sound name "Glass"' if sound else ''),
              'end run']
    cmd = ["osascript"] + [x for line in script for x in ("-e", line)] + [title[:120], body[:240]]
    try:
        subprocess.run(cmd, timeout=10, capture_output=True)
    except Exception as e:  # noqa: BLE001
        db.log("système", "erreur", f"notification Mac échouée : {e}")


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


def _deliver(kind: str, title: str, body: str, priority: str) -> None:
    s = settings()
    quiet = is_quiet() and priority != "urgent"
    if s["mac"] and mac_available() and not quiet:
        _mac(f"{ICONS.get(kind, '🔔')} {title}", body, s["sound"])
    if not quiet or priority in ("high", "urgent"):
        tags = {"validation": "question", "rapport": "page_facing_up", "client": "envelope", "alerte": "warning"}.get(kind, "rocket")
        _push(title, body, priority if not quiet else "low", tags)


def notify(kind: str, title: str, body: str, priority: str = "default") -> None:
    """kind : validation | rapport | client | alerte. priority : min|low|default|high|urgent."""
    db.x("INSERT INTO notifications (ts, kind, title, body) VALUES (CAST(strftime('%s','now') AS REAL),?,?,?)",
         (kind, title, body[:4000]))
    try:
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _deliver, kind, title, body, priority)
    except RuntimeError:
        _deliver(kind, title, body, priority)
