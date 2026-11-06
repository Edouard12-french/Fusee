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


def unlimited() -> bool:
    """« Sans limite par jour » (réglé avec le code parent) : seul le budget IA total arrête les agents."""
    return db.get_setting("budget_unlimited", "0") == "1"


def web_search_limit() -> int:
    """Recherches web autorisées par jour : la plus grosse dépense des petits modèles, donc plafonnée."""
    forced = os.getenv("WEB_SEARCH_DAILY_LIMIT", "").strip()
    if forced.isdigit():
        return int(forced)
    if unlimited():
        return 300
    return max(5, int(daily_cap_usd() * SEARCH_SHARE / WEB_SEARCH_COST))


def searches_exhausted() -> bool:
    return db.searches_today() >= web_search_limit()


OWNER_WINDOW_S = 30 * 60   # après un message de Patron, l'équipe peut s'organiser 30 min pour lui répondre
DEFAULT_RESERVE_PCT = 40   # part du budget du jour gardée pour Patron quand l'équipe travaille seule (réglable)
JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def work_until() -> float:
    try:
        return float(db.get_setting("work_until", "0") or 0)
    except ValueError:
        return 0.0


def work_from() -> float:
    try:
        return float(db.get_setting("work_from", "0") or 0)
    except ValueError:
        return 0.0


def work_authorized(now: float | None = None) -> bool:
    """Patron a autorisé l'équipe à travailler seule (sans attendre ses messages), de work_from() à work_until()."""
    t = now or time.time()
    return work_from() <= t < work_until()


def work_scheduled(now: float | None = None) -> bool:
    """Une période de travail en solo est programmée mais pas encore commencée (ex. « demain de 8 h à 17 h »)."""
    t = now or time.time()
    return t < work_from() < work_until()


def authorize_work(until_ts: float, from_ts: float | None = None) -> None:
    db.set_setting("work_from", str(float(from_ts or 0)))
    db.set_setting("work_until", str(float(until_ts)))


def stop_work() -> None:
    db.set_setting("work_from", "0")
    db.set_setting("work_until", "0")


def planned_window(day: str, h_from: int, h_to: int, now: datetime | None = None,
                   end_days: int | None = None) -> tuple[float, float]:
    """« demain de 8 h à 17 h » → (début, fin). Sans end_days, une fin plus tôt que le début = le lendemain
    (ex. 22 h → 7 h). Avec end_days (0 à 7) : la fin est ce nombre de jours après le jour de début."""
    now = now or datetime.now()
    base = (now + timedelta(days=1 if day == "demain" else 0)).replace(minute=0, second=0, microsecond=0)
    start = base.replace(hour=h_from)
    end = base.replace(hour=h_to)
    if end_days is not None:
        end += timedelta(days=max(0, min(7, int(end_days))))
    elif end <= start:
        end += timedelta(days=1)
    return start.timestamp(), end.timestamp()


def owner_reserve_pct() -> int:
    try:
        return min(90, max(10, int(db.get_setting("owner_reserve_pct", str(DEFAULT_RESERVE_PCT)))))
    except ValueError:
        return DEFAULT_RESERVE_PCT


def autonomous_share() -> float:
    """Le travail en solo s'arrête à cette part du budget du jour : le reste est gardé pour Patron."""
    return 1 - owner_reserve_pct() / 100


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


def range_label(from_ts: float, until_ts: float, now: datetime | None = None) -> str:
    """« demain 8 h → 17 h » (le jour n'est pas répété quand c'est le même)."""
    a, b = datetime.fromtimestamp(from_ts), datetime.fromtimestamp(until_ts)
    end = when_label(until_ts, now)
    if a.date() == b.date():
        end = f"{b.hour} h" + (f"{b.minute:02d}" if b.minute else "")
    return f"{when_label(from_ts, now)} → {end}"


def note_owner_active() -> None:
    db.set_setting("owner_active_until", str(time.time() + OWNER_WINDOW_S))


def owner_active() -> bool:
    try:
        return time.time() < float(db.get_setting("owner_active_until", "0") or 0)
    except ValueError:
        return False


def total_reserve_eur() -> float:
    """Sans limite par jour : petite réserve gardée sur le budget IA total pour que Patron puisse encore parler
    à l'équipe et vérifier (5 % du budget IA, au moins 0,50 €)."""
    return max(0.5, 0.05 * settings()["api_budget_eur"])


def api_left_eur() -> float:
    return max(0.0, settings()["api_budget_eur"] - api_spent_eur())


def autonomous_budget_used() -> bool:
    """Le travail en solo doit-il s'arrêter ? Limité : à la part du budget du jour. Sans limite : seulement quand il
    ne reste plus que la petite réserve du budget IA total."""
    if unlimited():
        return api_left_eur() <= total_reserve_eur()
    return db.cost_today() >= autonomous_share() * daily_cap_usd()


def api_spent_eur() -> float:
    return db.cost_total() * USD_EUR


def api_exhausted() -> bool:
    return api_spent_eur() >= settings()["api_budget_eur"]


OWNER_EXTRA = 1.0  # rallonge : quand Patron parle (ou qu'un client écrit), jusqu'à 2 fois le budget du jour


def owner_cap_usd() -> float:
    return daily_cap_usd() * (1 + OWNER_EXTRA)


def owner_exhausted() -> bool:
    """Même la rallonge du jour est utilisée : là seulement, on ne répond plus à Patron avant demain."""
    return not unlimited() and db.cost_today() >= owner_cap_usd()


def today_exhausted() -> bool:
    return not unlimited() and db.cost_today() >= daily_cap_usd()


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
        "unlimited": unlimited(),
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
