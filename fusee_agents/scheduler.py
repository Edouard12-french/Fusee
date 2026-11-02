"""Fait tourner chaque agent en continu : un cycle à intervalle régulier, ou dès qu'il est mentionné."""
import asyncio

from . import budget, db, mailbox, markets, outreach, sales
from .agents import BY_NAME, OWNER, TEAM, Agent, agent_settings
from .config import INTERVAL_MULTIPLIER, MAX_PARALLEL_AGENTS
from .runner import run_cycle


# La nuit, seuls ces réveils font travailler un agent : ceux qui viennent de Patron (et Iris pour les clients)
OWNER_WAKES = (f"message de {OWNER}", f"{OWNER} a ", f"en privé, {OWNER}", "pendant la réunion", "la clé API vient")


def allowed_at_night(name: str, reason: str) -> bool:
    if name == "Iris":  # les clients écrivent à toute heure
        return True
    return any(part.strip().startswith(OWNER_WAKES) for part in reason.split(" | "))


class Scheduler:
    def __init__(self) -> None:
        self.events = {a.name: asyncio.Event() for a in TEAM}
        self.reasons: dict[str, list[str]] = {a.name: [] for a in TEAM}
        self.deferred: dict[str, list[str]] = {a.name: [] for a in TEAM}  # réveils de la nuit, gardés pour le matin
        self.sem = asyncio.Semaphore(MAX_PARALLEL_AGENTS)
        self.tasks: list[asyncio.Task] = []

    @property
    def paused(self) -> bool:
        return db.get_setting("paused", "0") == "1"

    def wake(self, name: str, reason: str) -> None:
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
                if budget.is_night() and not allowed_at_night(name, reason):
                    if reason not in ("cycle régulier", "démarrage"):
                        self.deferred[name] = (self.deferred[name] + [reason])[-5:]
                    db.set_state(name, status=f"😴 dort jusqu'à {budget.night_settings()['to']} h (économie)")
                else:
                    if self.deferred[name]:
                        reason = " | ".join(self.deferred[name] + [reason])
                        self.deferred[name] = []
                    async with self.sem:
                        await run_cycle(agent, reason, self.wake)
            # attendre le prochain cycle (ou une mention), avec un délai minimum anti ping-pong
            await asyncio.sleep(agent.min_gap_s)
            if not self.reasons[name]:
                self.events[name].clear()
            try:
                iv = interval()
                timeout = max(0, iv - agent.min_gap_s) if iv else None
                if self.deferred[name]:  # un réveil attend le matin : on se réveille au plus tard à l'heure prévue
                    timeout = min(timeout or 1e12, budget.seconds_until_morning() + 60)
                await asyncio.wait_for(self.events[name].wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass
            self.events[name].clear()
            pending, self.reasons[name] = self.reasons[name], []
            reason = " | ".join(pending[-5:]) if pending else "cycle régulier"

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
        self.tasks.append(asyncio.create_task(self._followups()))
        self.tasks.append(asyncio.create_task(self._backups()))
        self.tasks.append(asyncio.create_task(mailbox.poll_forever(
            lambda ids: self.wake("Iris", f"nouvel(s) e-mail(s) de contact(s) {ids}"))))


scheduler = Scheduler()

