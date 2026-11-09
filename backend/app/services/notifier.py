"""Verteilt Ereignisse live an alle offenen ELW-Ansichten (WebSocket)."""

import asyncio
import logging
from dataclasses import dataclass

from fastapi import WebSocket, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from app.db import new_session, utcnow
from app.models import Anmeldung

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Client:
    einsatz_id: int
    anmeldung_id: int


def _noch_gueltig(anmeldung_ids: set[int]) -> set[int]:
    with new_session() as db:
        return set(
            db.scalars(
                select(Anmeldung.id).where(
                    Anmeldung.id.in_(anmeldung_ids),
                    Anmeldung.abgemeldet_at.is_(None),
                    Anmeldung.gueltig_bis >= utcnow(),
                )
            )
        )


class Notifier:
    def __init__(self) -> None:
        self._clients: dict[WebSocket, _Client] = {}

    def add(self, ws: WebSocket, einsatz_id: int, anmeldung_id: int) -> None:
        self._clients[ws] = _Client(einsatz_id, anmeldung_id)

    def remove(self, ws: WebSocket) -> None:
        self._clients.pop(ws, None)

    async def _schliesse(self, ws: WebSocket) -> None:
        self.remove(ws)
        try:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        except (RuntimeError, OSError) as exc:  # Verbindung ist schon weg
            log.debug("WebSocket bereits getrennt: %s", exc)

    async def trenne_anmeldung(self, anmeldung_id: int) -> None:
        """Beim Abmelden: Der Browser erfährt sofort, dass der Kanal nicht mehr gilt."""
        await asyncio.gather(*(self._schliesse(ws) for ws, c in list(self._clients.items()) if c.anmeldung_id == anmeldung_id))

    async def broadcast(self, einsatz_id: int, event: dict) -> None:
        kandidaten = {ws: c for ws, c in self._clients.items() if c.einsatz_id == einsatz_id}
        if not kandidaten:
            return
        # Vor jedem Versand prüfen: Sitzungen laufen ab, ohne dass der Server davon ein Ereignis bekommt.
        gueltig = await run_in_threadpool(_noch_gueltig, {c.anmeldung_id for c in kandidaten.values()})
        await asyncio.gather(*(self._schliesse(ws) for ws, c in kandidaten.items() if c.anmeldung_id not in gueltig))
        targets = [ws for ws, c in kandidaten.items() if c.anmeldung_id in gueltig]
        results = await asyncio.gather(*(ws.send_json(event) for ws in targets), return_exceptions=True)
        for ws, result in zip(targets, results, strict=True):
            if isinstance(result, Exception):
                log.info("ELW-Client getrennt: %s", result)
                self.remove(ws)
