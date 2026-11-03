"""Budget réel de Patron : argent de départ, dépenses IA, autres dépenses validées, revenus."""
import json
import os
import time
from datetime import datetime, timedelta

from . import db
from .config import (API_BUDGET_DAYS, API_BUDGET_EUR, BUDGET_INITIAL_EUR, DAILY_BUDGET_USD, ROOT, USD_EUR,
                     WEB_SEARCH_COST)

SEARCH_SHARE = 0.4  # au plus 40 % du budget du jour en recherches web (~1 centime chacune)


def settings() -> dict:
    return {
        "initial_eur": float(db.get_setting("budget_initial_eur", str(BUDGET_INITIAL_EUR))),
        "api_budget_eur": float(db.get_setting("api_budget_eur", str(API_BUDGET_EUR))),
        "api_days": max(1.0, float(db.get_setting("api_days", str(API_BUDGET_DAYS)))),
    }


def daily_cap_usd() -> float:
    """Dépense IA maximale par jour : la part IA du budget étalée sur la durée choisie."""
    s = settings()
    cap = s["api_budget_eur"] / s["api_days"] / USD_EUR
    return min(cap, DAILY_BUDGET_USD) if DAILY_BUDGET_USD > 0 else cap


def web_search_limit() -> int:
    """Recherches web autorisées par jour : la plus grosse dépense des petits modèles, donc plafonnée."""
    forced = os.getenv("WEB_SEARCH_DAILY_LIMIT", "").strip()
    if forced.isdigit():
        return int(forced)
    return max(5, int(daily_cap_usd() * SEARCH_SHARE / WEB_SEARCH_COST))


def searches_exhausted() -> bool:
    return db.searches_today() >= web_search_limit()


OWNER_WINDOW_S = 30 * 60   # après un message de Patron, l'équipe peut s'organiser 30 min pour lui répondre
AUTONOMOUS_SHARE = 0.6     # le travail en solo s'arrête à 60 % du budget du jour : le reste est gardé pour Patron
JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def work_until() -> float:
    try:
        return float(db.get_setting("work_until", "0") or 0)
    except ValueError:
        return 0.0


def work_authorized(now: float | None = None) -> bool:
    """Patron a autorisé l'équipe à travailler seule (sans attendre ses messages) jusqu'à work_until()."""
    return (now or time.time()) < work_until()


def authorize_work(until_ts: float) -> None:
    db.set_setting("work_until", str(float(until_ts)))


def stop_work() -> None:
    db.set_setting("work_until", "0")


def next_morning(hour: int = 7, now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    wake = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    return wake if wake > now else wake + timedelta(days=1)


def when_label(ts: float, now: datetime | None = None) -> str:
    d, now = datetime.fromtimestamp(ts), now or datetime.now()
    hm = f"{d.hour} h" + (f"{d.minute:02d}" if d.minute else "")
    if d.date() == now.date():
        return hm
    if d.date() == (now + timedelta(days=1)).date():
        return f"demain {hm}"
    return f"{JOURS_FR[d.weekday()]} {d.day} à {hm}"


def note_owner_active() -> None:
    db.set_setting("owner_active_until", str(time.time() + OWNER_WINDOW_S))


def owner_active() -> bool:
    try:
        return time.time() < float(db.get_setting("owner_active_until", "0") or 0)
    except ValueError:
        return False


def autonomous_budget_used() -> bool:
    return db.cost_today() >= AUTONOMOUS_SHARE * daily_cap_usd()


def api_spent_eur() -> float:
    return db.cost_total() * USD_EUR


def api_exhausted() -> bool:
    return api_spent_eur() >= settings()["api_budget_eur"]


OWNER_EXTRA = 1.0  # rallonge : quand Patron parle (ou qu'un client écrit), jusqu'à 2 fois le budget du jour


def owner_cap_usd() -> float:
    return daily_cap_usd() * (1 + OWNER_EXTRA)


def owner_exhausted() -> bool:
    """Même la rallonge du jour est utilisée : là seulement, on ne répond plus à Patron avant demain."""
    return db.cost_today() >= owner_cap_usd()


def today_exhausted() -> bool:
    return db.cost_today() >= daily_cap_usd()


def summary() -> dict:
    s = settings()
    rows = db.q("SELECT kind, COALESCE(SUM(amount_eur), 0) t FROM ledger GROUP BY kind")
    by = {r["kind"]: r["t"] for r in rows}
    api = api_spent_eur()
    expenses = by.get("dépense", 0.0)
    sales = db.q("SELECT COALESCE(SUM(amount_eur), 0) t, COUNT(*) n FROM sales")[0]
    revenues = by.get("revenu", 0.0) + sales["t"]
    return {
        **s,
        "api_spent_eur": api,
        "api_today_eur": db.cost_today() * USD_EUR,
        "api_daily_cap_eur": daily_cap_usd() * USD_EUR,
        "api_left_eur": max(0.0, s["api_budget_eur"] - api),
        "expenses_eur": expenses,
        "revenues_eur": revenues,
        "sales_eur": sales["t"],
        "sales_count": sales["n"],
        "remaining_eur": s["initial_eur"] - api - expenses + revenues,
        "free_to_spend_eur": s["initial_eur"] - s["api_budget_eur"] - expenses + revenues,
    }


def investor_profile() -> dict:
    try:
        return json.loads(db.get_setting("investor_profile", "{}"))
    except ValueError:
        return {}


def strategy() -> str:
    """Stratégie d'investissement : celle tenue à jour par Wolf, sinon la première version (STRATEGIE.md)."""
    s = db.get_setting("strategy", "")
    if not s and (ROOT / "STRATEGIE.md").is_file():
        s = (ROOT / "STRATEGIE.md").read_text(errors="replace")
    return s
