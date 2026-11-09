import logging

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app.api.deps import DB, LESE_ROLLEN, CurrentAnmeldung, ElwAnmeldung, LeseAnmeldung, MeldeAnmeldung
from app.models import Anhang, Anmeldung, Nachricht
from app.schemas.message import AuditOut, NachrichtCreate, NachrichtOut, StatusUpdate
from app.services import ablage, message_service

router = APIRouter(prefix="/api/messages", tags=["messages"])
log = logging.getLogger("meldi")


def _ablage_fehler(exc: OSError) -> HTTPException:
    log.error("Einsatzablage nicht beschreibbar: %s", exc)
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Einsatzablage nicht beschreibbar. Im ELW prüfen: Datei geöffnet oder Datenträger voll?",
    )


def to_out(n: Nachricht, **extra) -> NachrichtOut:
    return NachrichtOut.model_validate({**n.__dict__, "von_name": n.von_user.name, **extra})


@router.post("", response_model=NachrichtOut, status_code=201)
async def create(
    body: NachrichtCreate, request: Request, response: Response, anmeldung: MeldeAnmeldung, db: DB
) -> NachrichtOut:
    try:
        # Datei-I/O der Einsatzablage nicht im Event-Loop (WebSocket, andere Anfragen).
        ergebnis = await run_in_threadpool(message_service.create_nachricht, db, anmeldung, body)
    except message_service.AnhangFehler as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    except OSError as exc:
        raise _ablage_fehler(exc) from None
    out = to_out(ergebnis.nachricht, fehlende_anhaenge=ergebnis.fehlende_anhaenge)
    if not ergebnis.neu:
        response.status_code = status.HTTP_200_OK  # Wiederholung: schon angekommen, nicht erneut verteilen
        return out
    await request.app.state.notifier.broadcast(
        anmeldung.einsatz_id, {"type": "nachricht.neu", "nachricht": out.model_dump(mode="json")}
    )
    return out


@router.get("", response_model=list[NachrichtOut])
def list_messages(anmeldung: CurrentAnmeldung, db: DB, nur_eigene: bool = False) -> list[NachrichtOut]:
    """ELW und Beobachter sehen alle Nachrichten des Einsatzes, Melder nur die eigenen der aktuellen Anmeldung.

    `nur_eigene` nutzt die Melder-Ansicht, damit das ELW dort beim Erfassen nur seine eigenen Nachrichten sieht.
    """
    if anmeldung.rolle in LESE_ROLLEN and not nur_eigene:
        nachrichten = message_service.list_for_einsatz(db, anmeldung.einsatz_id)
    else:
        nachrichten = message_service.list_for_anmeldung(db, anmeldung)
    return [to_out(n) for n in nachrichten]


def _get_im_einsatz(db: DB, anmeldung: Anmeldung, nachricht_id: int) -> Nachricht:
    n = db.get(Nachricht, nachricht_id)
    if n is None or n.einsatz_id != anmeldung.einsatz_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nachricht nicht gefunden")
    return n


@router.get("/{nachricht_id}", response_model=NachrichtOut)
def get_message(nachricht_id: int, anmeldung: LeseAnmeldung, db: DB) -> NachrichtOut:
    return to_out(_get_im_einsatz(db, anmeldung, nachricht_id))


@router.get("/{nachricht_id}/audit", response_model=list[AuditOut])
def get_audit(nachricht_id: int, anmeldung: LeseAnmeldung, db: DB) -> list[AuditOut]:
    _get_im_einsatz(db, anmeldung, nachricht_id)
    return [AuditOut.model_validate({**a.__dict__, "name": a.user.name}) for a in message_service.audit_for(db, nachricht_id)]


@router.put("/{nachricht_id}/status", response_model=NachrichtOut)
async def set_status(
    nachricht_id: int, body: StatusUpdate, request: Request, anmeldung: ElwAnmeldung, db: DB
) -> NachrichtOut:
    n = _get_im_einsatz(db, anmeldung, nachricht_id)
    try:
        # Datei-I/O der Einsatzablage nicht im Event-Loop, auch nicht beim Warten auf gesperrte Dateien.
        geaendert = await run_in_threadpool(message_service.setze_status, db, anmeldung, n, body.status)
    except OSError as exc:
        raise _ablage_fehler(exc) from None
    out = to_out(n)
    if geaendert:
        await request.app.state.notifier.broadcast(
            anmeldung.einsatz_id, {"type": "nachricht.geaendert", "nachricht": out.model_dump(mode="json")}
        )
    return out


@router.get("/{nachricht_id}/anhaenge/{anhang_id}")
def get_anhang(nachricht_id: int, anhang_id: int, anmeldung: LeseAnmeldung, db: DB) -> FileResponse:
    n = _get_im_einsatz(db, anmeldung, nachricht_id)
    a = db.get(Anhang, anhang_id)
    if a is None or a.nachricht_id != n.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anhang nicht gefunden")
    datei = ablage.pfad(n.ablage_ordner) / a.dateiname if n.ablage_ordner else None
    if datei is None or not datei.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Datei fehlt in der Einsatzablage")
    # Nur Audio und Bilder im Browser anzeigen, alles andere als Download.
    inline = a.mime.startswith(("audio/", "image/"))
    return FileResponse(
        datei, media_type=a.mime, filename=a.dateiname, content_disposition_type="inline" if inline else "attachment"
    )
