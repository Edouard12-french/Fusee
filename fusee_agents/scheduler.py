"""Fait tourner chaque agent en continu : un cycle à intervalle régulier, ou dès qu'il est mentionné."""
import asyncio

from . import db, mailbox, markets, sales
from .agents import BY_NAME, TEAM
from .config import INTERVAL_MULTIPLIER, MAX_PARALLEL_AGENTS
from .runner import run_cycle


class Scheduler:
    def __init__(self) -> None:
        self.events = {a.name: asyncio.Event() for a in TEAM}
        self.reasons: dict[str, list[str]] = {a.name: [] for a in TEAM}
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
        interval = agent.interval_min * 60 * INTERVAL_MULTIPLIER  # 0 = seulement à la demande
        await asyncio.sleep(first_delay)
        reason = "démarrage"
        if not interval:  # agent « à la demande » : attend d'être appelé
            await self.events[name].wait()
            self.events[name].clear()
            pending, self.reasons[name] = self.reasons[name], []
            reason = " | ".join(pending[-5:]) or "appel"
        while True:
            if not self.paused:
                async with self.sem:
                    await run_cycle(agent, reason, self.wake)
            # attendre le prochain cycle (ou une mention), avec un délai minimum anti ping-pong
            await asyncio.sleep(agent.min_gap_s)
            if not self.reasons[name]:
                self.events[name].clear()
            try:
                await asyncio.wait_for(self.events[name].wait(),
                                       timeout=max(0, interval - agent.min_gap_s) if interval else None)
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

    def start(self) -> None:
        for i, a in enumerate(TEAM):
            db.set_state(a.name, status="en attente")
            self.tasks.append(asyncio.create_task(self._loop(a.name, first_delay=i * 30)))
        self.tasks.append(asyncio.create_task(sales.poll_forever(self.wake)))
        self.tasks.append(asyncio.create_task(self._mark_prices()))
        self.tasks.append(asyncio.create_task(mailbox.poll_forever(
            lambda ids: self.wake("Iris", f"nouvel(s) e-mail(s) de contact(s) {ids}"))))


scheduler = Scheduler()

