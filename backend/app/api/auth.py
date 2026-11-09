from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status

from app.api.deps import DB, SESSION_COOKIE, CurrentAnmeldung, ElwAnmeldung
from app.config import get_settings
from app.schemas.auth import AnmeldungOut, FunktionOut, LoginRequest, MeOut
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _me(anmeldung) -> MeOut:
    return MeOut(
        name=anmeldung.user.name,
        rolle=anmeldung.rolle,
        funktion=anmeldung.funktion,
        einsatz=anmeldung.einsatz.bezeichnung,
    )


@router.get("/funktionen", response_model=list[FunktionOut])
def funktionen(db: DB) -> list[FunktionOut]:
    """Funktionen des aktiven Einsatzes für die Auswahl beim Login (ohne Einsatzdetails)."""
    einsatz = auth_service.aktiver_einsatz(db)
    return [FunktionOut(id=f.id, name=f.name) for f in einsatz.funktionen] if einsatz else []


@router.post("/login", response_model=MeOut)
def login(body: LoginRequest, request: Request, response: Response, background: BackgroundTasks, db: DB) -> MeOut:
    settings = get_settings()
    # Wer die Ansicht wechselt, meldet sich neu an. Die alte Anmeldung darf nicht als aktiv stehen bleiben.
    if bisher := auth_service.resolve_session(db, request.cookies.get(SESSION_COOKIE)):
        auth_service.logout(db, bisher)
        background.add_task(request.app.state.notifier.trenne_anmeldung, bisher.id)
    try:
        anmeldung, token = auth_service.login(db, body.name, body.funktion, body.rolle, settings.session_hours)
    except auth_service.LoginError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from None
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    return _me(anmeldung)


@router.get("/me", response_model=MeOut)
def me(anmeldung: CurrentAnmeldung) -> MeOut:
    return _me(anmeldung)


@router.post("/logout", status_code=204)
def logout(anmeldung: CurrentAnmeldung, request: Request, response: Response, background: BackgroundTasks, db: DB) -> None:
    auth_service.logout(db, anmeldung)
    background.add_task(request.app.state.notifier.trenne_anmeldung, anmeldung.id)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/anmeldungen", response_model=list[AnmeldungOut])
def anmeldungen(anmeldung: ElwAnmeldung, db: DB) -> list[AnmeldungOut]:
    """Wer gerade angemeldet ist. Ohne PIN ist das die einzige Sicht des ELW darauf, wer im System ist."""
    return [
        AnmeldungOut(name=a.user.name, rolle=a.rolle, funktion=a.funktion, angemeldet_at=a.angemeldet_at)
        for a in auth_service.aktive_anmeldungen(db, anmeldung.einsatz_id)
    ]
