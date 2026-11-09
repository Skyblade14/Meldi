import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Anmeldung, Einsatz, Rolle, User
from app.services import ablage


class LoginError(Exception):
    pass


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def aktiver_einsatz(db: Session) -> Einsatz | None:
    return db.scalars(select(Einsatz).where(Einsatz.ende.is_(None)).order_by(Einsatz.beginn.desc())).first()


def _user_zum_namen(db: Session, name: str) -> User:
    user = db.scalars(select(User).where(User.name == name)).first()
    if user is not None:
        return user
    user = User(name=name)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Derselbe Name meldete sich gleichzeitig zum ersten Mal an.
        db.rollback()
        return db.scalars(select(User).where(User.name == name)).one()
    return user


def login(db: Session, name: str, funktion: str, rolle: Rolle, session_hours: int) -> tuple[Anmeldung, str]:
    """Legt eine Anmeldung im aktiven Einsatz an. Gibt (Anmeldung, Token) zurück.

    Name und Rolle sind nur Angaben der Person. Sie dokumentieren, wer was geschrieben hat, und schützen nicht.
    """
    einsatz = aktiver_einsatz(db)
    if einsatz is None:
        raise LoginError("Kein aktiver Einsatz – bitte im ELW das Startfenster prüfen")

    token = secrets.token_urlsafe(32)
    now = utcnow()
    anmeldung = Anmeldung(
        user=_user_zum_namen(db, name),
        einsatz_id=einsatz.id,
        rolle=rolle,
        funktion=funktion,
        token_hash=_token_hash(token),
        angemeldet_at=now,
        gueltig_bis=now + timedelta(hours=session_hours),
    )
    db.add(anmeldung)
    db.commit()
    return anmeldung, token


def resolve_session(db: Session, token: str | None) -> Anmeldung | None:
    if not token:
        return None
    anmeldung = db.scalars(select(Anmeldung).where(Anmeldung.token_hash == _token_hash(token))).first()
    if anmeldung is None or anmeldung.abgemeldet_at is not None or anmeldung.gueltig_bis < utcnow():
        return None
    return anmeldung


def logout(db: Session, anmeldung: Anmeldung) -> None:
    anmeldung.abgemeldet_at = utcnow()
    db.commit()
    ablage.verwerfen(anmeldung.id)  # nicht abgesendete Aufnahmen und Fotos


def aktive_anmeldungen(db: Session, einsatz_id: int) -> list[Anmeldung]:
    return list(
        db.scalars(
            select(Anmeldung)
            .where(
                Anmeldung.einsatz_id == einsatz_id,
                Anmeldung.abgemeldet_at.is_(None),
                Anmeldung.gueltig_bis >= utcnow(),
            )
            .order_by(Anmeldung.angemeldet_at.desc())
        )
    )
