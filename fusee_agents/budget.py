"""Budget réel de Patron : argent de départ, dépenses IA, autres dépenses validées, revenus."""
import json
import os
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


def night_settings() -> dict:
    return {"enabled": db.get_setting("night_enabled", "1") == "1",
            "from": int(db.get_setting("night_from", "23")), "to": int(db.get_setting("night_to", "7"))}


def is_night(now: datetime | None = None) -> bool:
    """Les agents dorment la nuit (économie) : personne ne valide rien, les entreprises ne lisent pas leurs e-mails."""
    s = night_settings()
    if not s["enabled"] or s["from"] == s["to"]:
        return False
    h, a, b = (now or datetime.now()).hour, s["from"], s["to"]
    return (a <= h or h < b) if a > b else (a <= h < b)


def seconds_until_morning(now: datetime | None = None) -> float:
    now = now or datetime.now()
    wake = now.replace(hour=night_settings()["to"], minute=0, second=0, microsecond=0)
    if wake <= now:
        wake += timedelta(days=1)
    return (wake - now).total_seconds()


def api_spent_eur() -> float:
    return db.cost_total() * USD_EUR


def api_exhausted() -> bool:
    return api_spent_eur() >= settings()["api_budget_eur"]


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
