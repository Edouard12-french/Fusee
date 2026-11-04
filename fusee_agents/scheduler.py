"""Fait tourner chaque agent en continu : un cycle à intervalle régulier, ou dès qu'il est mentionné."""
import asyncio
import time
from datetime import date, datetime

from . import briefing, budget, db, mailbox, markets, outreach, sales
from .agents import BY_NAME, OWNER, TEAM, Agent, agent_settings
from .config import INTERVAL_MULTIPLIER, MAX_PARALLEL_AGENTS
from .runner import run_cycle


# Réveils qui viennent de Patron : ils font toujours travailler l'agent concerné
OWNER_WAKES = (f"message de {OWNER}", f"{OWNER} a ", f"en privé, {OWNER}", "pendant la réunion", "la clé API vient")
IDLE = ("cycle régulier", "démarrage")


def why_may_work(name: str, reason: str) -> str | None:
    """Pourquoi cet agent peut travailler maintenant : « patron », « client », « autonome »… ou None (il attend).
    Par défaut l'équipe ne travaille que quand Patron lui parle (+ 30 min pour s'organiser entre agents),
    pour les clients (Iris, ventes), ou pendant une période où Patron l'a autorisée à travailler seule."""
    parts = [p.strip() for p in reason.split(" | ")]
    if any(p.startswith(OWNER_WAKES) for p in parts):
        return "patron"
    if name == "Iris" or any("nouvelle(s) vente(s)" in p for p in parts):
        return "client"
    if budget.owner_active() and any(p not in IDLE for p in parts):
        return "patron"  # un collègue l'appelle pour répondre à ce que Patron vient de demander
    if budget.work_authorized():
        return "autonome"
    return None


class Scheduler:
    def __init__(self) -> None:
        self.events = {a.name: asyncio.Event() for a in TEAM}
        self.reasons: dict[str, list[str]] = {a.name: [] for a in TEAM}
        self.deferred: dict[str, list[str]] = {a.name: [] for a in TEAM}  # appels reçus pendant qu'il attendait
        self.sem = asyncio.Semaphore(MAX_PARALLEL_AGENTS)
        self.tasks: list[asyncio.Task] = []

    @property
    def paused(self) -> bool:
        return db.get_setting("paused", "0") == "1"

    def wake(self, name: str, reason: str) -> None:
        if reason.startswith(OWNER_WAKES):
            budget.note_owner_active()
        if name in self.events:
            self.reasons[name].append(reason)
            self.events[name].set()

    async def _loop(self, name: str, first_delay: float) -> None:
        agent = BY_NAME[name]

        def interval() -> float:  # l'équipe peut changer le rythme d'un agent (adjust_agent)
            return agent_settings(name).get("interval_min", agent.interval_min) * 60 * INTERVAL_MULTIPLIER

        await asyncio.sleep(first_delay)
        reason = "démarrage"
        if not interval():  # agent « à la demande » : attend d'être appelé
            await self.events[name].wait()
            self.events[name].clear()
            pending, self.reasons[name] = self.reasons[name], []
            reason = " | ".join(pending[-5:]) or "appel"
        while True:
            if agent_settings(name).get("enabled", True) is False:
                db.set_state(name, status="en pause (décision de l'équipe)")
            elif not self.paused:
                why = why_may_work(name, reason)
                if why is None or (why == "autonome" and budget.autonomous_budget_used()):
                    if reason not in IDLE:
                        self.deferred[name] = (self.deferred[name] + [reason])[-5:]
                    db.set_state(name, status=f"💤 attend que {OWNER} parle" if why is None
                                 else f"⏸️ garde le reste du budget du jour pour {OWNER}")
                else:
                    if self.deferred[name]:
                        reason = " | ".join(self.deferred[name] + [reason])
                        self.deferred[name] = []
                    async with self.sem:
                        await run_cycle(agent, reason, self.wake, for_owner=why in ("patron", "client"))
            # attendre le prochain cycle (ou une mention), avec un délai minimum anti ping-pong
            await asyncio.sleep(agent.min_gap_s)
            if not self.reasons[name]:
                self.events[name].clear()
            try:
                iv = interval()
                timeout = max(0, iv - agent.min_gap_s) if iv else None
                await asyncio.wait_for(self.events[name].wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass
            self.events[name].clear()
            pending, self.reasons[name] = self.reasons[name], []
            reason = " | ".join(pending[-5:]) if pending else "cycle régulier"

    def authorize(self, until_ts: float, from_ts: float | None = None) -> str:
        """Patron autorise l'équipe à travailler seule jusqu'à until_ts (à partir de from_ts, ou tout de suite) :
        les agents réguliers démarrent dès que la période commence."""
        budget.authorize_work(until_ts, from_ts)
        if budget.work_authorized():
            self._kick()
        return budget.when_label(until_ts)

    def _kick(self) -> None:
        db.set_setting("work_kicked", str(budget.work_from()))
        label = budget.when_label(budget.work_until())
        for a in TEAM:
            if agent_settings(a.name).get("interval_min", a.interval_min):
                self.wake(a.name, f"autorisation : {OWNER} vous laisse travailler seuls jusqu'à {label} — avancez sur "
                                  "vos projets en équipe (toujours request_approval avant de publier)")

    def briefing(self) -> float:
        """Atlas rédige le briefing maintenant (avec la rallonge si besoin). Si rien n'est rendu à temps, Fusée
        publie elle-même le classement : Patron a toujours son briefing."""
        since = time.time()
        self.wake("Atlas", briefing.BRIEFING_REASON.format(day=date.today().strftime("%d/%m")))

        async def fallback() -> None:
            await asyncio.sleep(briefing.FALLBACK_AFTER_S)
            briefing.fallback_report(since)
        self.tasks.append(asyncio.create_task(fallback()))
        return since

    async def _briefings(self) -> None:
        """Chaque jour à l'heure choisie (17 h par défaut) : le briefing pour Patron."""
        while True:
            await asyncio.sleep(60)
            s, today = briefing.settings(), date.today().isoformat()
            if s["enabled"] and datetime.now().hour == s["hour"] and db.get_setting("briefing_last", "") != today:
                db.set_setting("briefing_last", today)
                self.briefing()

    async def _work_watch(self) -> None:
        """Chaque minute : une période programmée (« demain 8 h → 17 h ») qui commence réveille l'équipe."""
        while True:
            await asyncio.sleep(60)
            if budget.work_authorized() and db.get_setting("work_kicked", "") != str(budget.work_from()):
                self._kick()

    async def _mark_prices(self) -> None:
        """Toutes les heures : prix réels des positions du portefeuille simulé."""
        while True:
            for pos in db.portfolio()["positions"]:
                try:
                    price = await asyncio.to_thread(markets.last_price, pos["symbol"])
                    db.x("INSERT OR REPLACE INTO marks (symbol, price, ts) VALUES (?,?,CAST(strftime('%s','now') AS REAL))",
                         (pos["symbol"], price))
                except Exception:  # noqa: BLE001 — symbole sans données : Wolf le met à jour à la main
                    pass
            await asyncio.sleep(3600)

    async def _followups(self) -> None:
        """Toutes les heures (en semaine, heures de bureau) : relances automatiques de prospection."""
        while True:
            if mailbox.ENABLED and outreach.business_hours() and not self.paused:
                try:
                    n = await asyncio.to_thread(outreach.run_followups)
                    if n:
                        db.log("Victor", "prospection", f"{n} relance(s) automatique(s) envoyée(s)")
                except Exception as e:  # noqa: BLE001
                    db.log("système", "erreur", f"relances de prospection : {str(e)[:200]}")
            await asyncio.sleep(3600)

    async def _backups(self) -> None:
        """Sauvegarde quotidienne de la base (7 derniers jours gardés dans data/sauvegardes)."""
        while True:
            try:
                path = await asyncio.to_thread(db.backup)
                if path:
                    db.log("système", "sauvegarde", f"base sauvegardée : {path.rsplit('/', 1)[-1]}")
            except Exception as e:  # noqa: BLE001
                db.log("système", "erreur", f"sauvegarde : {str(e)[:200]}")
            await asyncio.sleep(6 * 3600)

    def add(self, agent: Agent) -> None:
        """Ajoute un agent recruté en cours de route (sans redémarrer)."""
        self.events[agent.name] = asyncio.Event()
        self.reasons[agent.name] = ["tu viens d'être recruté dans l'équipe : présente-toi et commence ton travail"]
        self.events[agent.name].set()
        db.set_state(agent.name, status="en attente")
        self.tasks.append(asyncio.create_task(self._loop(agent.name, first_delay=1)))

    def start(self) -> None:
        for i, a in enumerate(TEAM):
            db.set_state(a.name, status="en attente")
            self.tasks.append(asyncio.create_task(self._loop(a.name, first_delay=i * 30)))
        self.tasks.append(asyncio.create_task(sales.poll_forever(self.wake)))
        self.tasks.append(asyncio.create_task(self._mark_prices()))
        self.tasks.append(asyncio.create_task(self._work_watch()))
        self.tasks.append(asyncio.create_task(self._briefings()))
        self.tasks.append(asyncio.create_task(self._followups()))
        self.tasks.append(asyncio.create_task(self._backups()))
        self.tasks.append(asyncio.create_task(mailbox.poll_forever(
            lambda ids: self.wake("Iris", f"nouvel(s) e-mail(s) de contact(s) {ids}"))))


scheduler = Scheduler()

