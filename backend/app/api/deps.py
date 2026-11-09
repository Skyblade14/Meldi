from typing import Annotated

from fastapi import Depends, HTTPException, Request, WebSocket, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Anmeldung, Rolle
from app.services import auth_service

SESSION_COOKIE = "meldi_session"

# Wer alle Nachrichten des Einsatzes sieht bzw. wer Nachrichten erfassen darf (das ELW über die Melder-Ansicht).
LESE_ROLLEN = frozenset({Rolle.ELW, Rolle.BEOBACHTER})
MELDE_ROLLEN = frozenset({Rolle.MELDER, Rolle.ELW})

DB = Annotated[Session, Depends(get_db)]


def current_anmeldung(request: Request, db: DB) -> Anmeldung:
    anmeldung = auth_service.resolve_session(db, request.cookies.get(SESSION_COOKIE))
    if anmeldung is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nicht angemeldet")
    return anmeldung


def require_elw(anmeldung: Annotated[Anmeldung, Depends(current_anmeldung)]) -> Anmeldung:
    if anmeldung.rolle != Rolle.ELW:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur für ELW-Personal")
    return anmeldung


def require_lesen(anmeldung: Annotated[Anmeldung, Depends(current_anmeldung)]) -> Anmeldung:
    if anmeldung.rolle not in LESE_ROLLEN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur für ELW-Personal und Beobachter")
    return anmeldung


def require_melden(anmeldung: Annotated[Anmeldung, Depends(current_anmeldung)]) -> Anmeldung:
    if anmeldung.rolle not in MELDE_ROLLEN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Beobachter können keine Nachrichten erfassen")
    return anmeldung


def websocket_anmeldung(ws: WebSocket, db: Session) -> Anmeldung | None:
    return auth_service.resolve_session(db, ws.cookies.get(SESSION_COOKIE))


CurrentAnmeldung = Annotated[Anmeldung, Depends(current_anmeldung)]
ElwAnmeldung = Annotated[Anmeldung, Depends(require_elw)]
LeseAnmeldung = Annotated[Anmeldung, Depends(require_lesen)]
MeldeAnmeldung = Annotated[Anmeldung, Depends(require_melden)]
