"""Fait tourner chaque agent en continu : un cycle à intervalle régulier, ou dès qu'il est mentionné."""
import asyncio

from . import db, mailbox
from .agents import BY_NAME, TEAM
from .config import INTERVAL_MULTIPLIER, MAX_PARALLEL_AGENTS, MIN_SECONDS_BETWEEN_CYCLES
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
        interval = agent.interval_min * 60 * INTERVAL_MULTIPLIER
        await asyncio.sleep(first_delay)
        reason = "démarrage"
        while True:
            if not self.paused:
                async with self.sem:
                    await run_cycle(agent, reason, self.wake)
            # attendre le prochain cycle (ou une mention), avec un délai minimum anti ping-pong
            await asyncio.sleep(MIN_SECONDS_BETWEEN_CYCLES)
            if not self.reasons[name]:
                self.events[name].clear()
            try:
                await asyncio.wait_for(self.events[name].wait(), timeout=max(0, interval - MIN_SECONDS_BETWEEN_CYCLES))
            except asyncio.TimeoutError:
                pass
            self.events[name].clear()
            pending, self.reasons[name] = self.reasons[name], []
            reason = " | ".join(pending[-5:]) if pending else "cycle régulier"

    def start(self) -> None:
        for i, a in enumerate(TEAM):
            db.set_state(a.name, status="en attente")
            self.tasks.append(asyncio.create_task(self._loop(a.name, first_delay=i * 20)))
        self.tasks.append(asyncio.create_task(mailbox.poll_forever(
            lambda ids: self.wake("Iris", f"{len(ids)} nouvel(s) e-mail(s) client : ids {ids}"))))


scheduler = Scheduler()

