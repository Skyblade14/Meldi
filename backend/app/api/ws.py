from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.api.deps import LESE_ROLLEN, websocket_anmeldung
from app.db import new_session

router = APIRouter()


@router.websocket("/api/ws/elw")
async def elw_feed(ws: WebSocket) -> None:
    with new_session() as db:
        anmeldung = websocket_anmeldung(ws, db)
        erlaubt = anmeldung is not None and anmeldung.rolle in LESE_ROLLEN
        einsatz_id, anmeldung_id = (anmeldung.einsatz_id, anmeldung.id) if erlaubt else (None, None)
    if einsatz_id is None:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    notifier = ws.app.state.notifier
    await ws.accept()
    notifier.add(ws, einsatz_id, anmeldung_id)
    try:
        while True:
            await ws.receive_text()  # Client sendet nur Pings
    except WebSocketDisconnect:
        pass
    finally:
        notifier.remove(ws)
