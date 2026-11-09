import shutil
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.models import Anhang, Anhangart, Anmeldung, AuditEvent, Einsatz, Funktion, Nachricht, Status
from app.schemas.message import NachrichtCreate
from app.services import ablage


class AnhangFehler(ValueError):
    """Zu viele Fotos an einer Nachricht."""


@dataclass
class Ergebnis:
    nachricht: Nachricht
    neu: bool  # False: dieselbe Sende-ID kam schon einmal an (Wiederholung nach verlorener Antwort)
    fehlende_anhaenge: int = 0


def _naechste_lfd_nr(db: Session, einsatz_id: int) -> int:
    # Atomar in einem Statement – auch bei gleichzeitigen Meldungen keine doppelten Nummern.
    return db.execute(
        update(Einsatz)
        .where(Einsatz.id == einsatz_id)
        .values(naechste_lfd_nr=Einsatz.naechste_lfd_nr + 1)
        .returning(Einsatz.naechste_lfd_nr - 1)
    ).scalar_one()


def _snapshot(n: Nachricht) -> dict:
    return {
        "lfd_nr": n.lfd_nr,
        "von_funktion": n.von_funktion,
        "an": n.an,
        "inhalt": n.inhalt,
        "status": n.status.value,
        "anhaenge": [{"datei": a.dateiname, "sha256": a.sha256} for a in n.anhaenge],
    }


def _hole_anhaenge(anmeldung: Anmeldung, ids: list[str]) -> tuple[list[ablage.Vorgemerkt], int]:
    """Gibt die vorhandenen Uploads und die Zahl der fehlenden zurück.

    Fehlende (Serverneustart, Abmeldung, fremde ID) blockieren das Absenden nicht: Die Nachricht selbst ist
    wichtiger. Das Fehlen wird im Protokoll und in der Ablage vermerkt.
    """
    vorgemerkt, fehlend = [], 0
    for upload_id in dict.fromkeys(ids):  # doppelte IDs ignorieren, Reihenfolge behalten
        v = ablage.hole(anmeldung.id, upload_id)
        if v is None:
            fehlend += 1
        else:
            vorgemerkt.append(v)
    if sum(v.art == Anhangart.FOTO for v in vorgemerkt) > get_settings().max_fotos:
        raise AnhangFehler(f"Höchstens {get_settings().max_fotos} Fotos pro Nachricht")
    return vorgemerkt, fehlend


def _per_sende_id(db: Session, anmeldung: Anmeldung, sende_id: str | None) -> Nachricht | None:
    if not sende_id:
        return None
    return db.scalars(
        select(Nachricht).where(Nachricht.anmeldung_id == anmeldung.id, Nachricht.sende_id == sende_id)
    ).first()


def create_nachricht(db: Session, anmeldung: Anmeldung, data: NachrichtCreate) -> Ergebnis:
    """Legt die Nachricht in DB und Einsatzablage an. Schlägt eins fehl, bleibt keins von beiden zurück.

    Synchron und mit Datei-I/O: vom Aufrufer im Thread-Pool ausführen.
    """
    if vorhanden := _per_sende_id(db, anmeldung, data.sende_id):
        return Ergebnis(vorhanden, neu=False)

    beginn = utcnow()
    vorgemerkt, fehlend = _hole_anhaenge(anmeldung, data.anhaenge)
    # Dateien kopieren und hashen, bevor die Datenbank gesperrt wird (UPDATE der lfd. Nr.).
    bereit = ablage.bereitstellen(vorgemerkt)
    ordner = None
    try:
        einsatz = anmeldung.einsatz
        an_funktion = db.scalars(
            select(Funktion).where(Funktion.einsatz_id == einsatz.id, Funktion.name == data.an.strip())
        ).first()
        nachricht = Nachricht(
            einsatz_id=einsatz.id,
            lfd_nr=_naechste_lfd_nr(db, einsatz.id),
            von_funktion=anmeldung.funktion,
            von_user_id=anmeldung.user_id,
            anmeldung_id=anmeldung.id,
            an=data.an.strip(),
            an_funktion_id=an_funktion.id if an_funktion else None,
            inhalt=data.inhalt.strip(),
            erfasst_at=data.erfasst_at.astimezone(UTC) if data.erfasst_at else None,
            eingabe={k: v.model_dump(exclude_none=True) for k, v in data.eingabe.items()},
            sende_id=data.sende_id,
        )
        db.add(nachricht)
        db.flush()
        if einsatz.ablage_ordner is None:
            einsatz.ablage_ordner = ablage.einsatz_ordnername(einsatz)
        nachricht.ablage_ordner = f"{einsatz.ablage_ordner}/{ablage.nachricht_ordnername(nachricht)}"
        for v, name, groesse, sha256 in bereit.dateien:
            nachricht.anhaenge.append(Anhang(
                art=Anhangart(v.art), feld=v.feld, dateiname=name, mime=v.mime, groesse=groesse,
                sha256=sha256, hochgeladen_at=v.hochgeladen_at, meta=v.meta,
            ))
        db.flush()
        aenderungen = {k: {"alt": None, "neu": v} for k, v in _snapshot(nachricht).items()}
        if fehlend:
            aenderungen["fehlende_anhaenge"] = {"alt": None, "neu": fehlend}
        audit = AuditEvent(
            nachricht_id=nachricht.id,
            user_id=anmeldung.user_id,
            funktion=anmeldung.funktion,
            aktion="erstellt",
            zeitpunkt=nachricht.eingang_at,
            aenderungen=aenderungen,
        )
        db.add(audit)

        ablage.schreibe_einsatz(ablage.pfad(einsatz.ablage_ordner), einsatz)
        ziel = ablage.pfad(nachricht.ablage_ordner)
        ablage.platz_schaffen(ziel)
        ablage.verschiebe(bereit.ordner, ziel)
        ordner = ziel
        ablage.schreibe_nachricht(ordner, nachricht, anmeldung.user.name, fehlend)
        ablage.protokolliere(ordner, audit, anmeldung.user.name)
        db.commit()
    except IntegrityError:
        # Dieselbe Sende-ID kam gleichzeitig doppelt an – die andere Anfrage hat gewonnen.
        db.rollback()
        _entferne(ordner, bereit)
        if vorhanden := _per_sende_id(db, anmeldung, data.sende_id):
            return Ergebnis(vorhanden, neu=False)
        raise
    except BaseException:
        db.rollback()
        _entferne(ordner, bereit)
        raise
    # Übernommene und übrige Uploads dieses Formulars (neu eingesprochen, verworfen) nicht aufbewahren.
    ablage.verwerfen(anmeldung.id, ids=[v.id for v in vorgemerkt], bis=beginn)
    return Ergebnis(nachricht, neu=True, fehlende_anhaenge=fehlend)


def _entferne(ordner: Path | None, bereit: ablage.Bereitgestellt) -> None:
    # Bleibt etwas liegen (Datei gesperrt), schiebt platz_schaffen() es beim nächsten Mal beiseite.
    for d in (ordner, bereit.ordner):
        if d is not None:
            shutil.rmtree(d, ignore_errors=True)


def setze_status(db: Session, anmeldung: Anmeldung, nachricht: Nachricht, status: Status) -> bool:
    """Setzt den Status mit Audit-Eintrag und aktualisiert die Einsatzablage. False, wenn er schon so war."""
    # Erst die Schreibsperre holen, dann lesen: Bei zwei ELW-Plätzen gleichzeitig stimmte sonst „alt“ im Audit nicht.
    db.execute(
        update(Nachricht)
        .where(Nachricht.id == nachricht.id)
        .values(status=Nachricht.status)
        .execution_options(synchronize_session=False)
    )
    db.refresh(nachricht)
    alt = nachricht.status
    if alt == status:
        db.commit()  # Sperre freigeben; ohne Änderung kein Audit-Eintrag
        return False
    nachricht.status = status
    audit = AuditEvent(
        nachricht_id=nachricht.id,
        user_id=anmeldung.user_id,
        funktion=anmeldung.funktion,
        aktion="status",
        aenderungen={"status": {"alt": alt.value, "neu": status.value}},
    )
    db.add(audit)
    db.flush()
    ordner = ablage.pfad(nachricht.ablage_ordner)
    fehlend = _fehlende_anhaenge(db, nachricht)
    try:
        ablage.schreibe_nachricht(ordner, nachricht, nachricht.von_user.name, fehlend)
        ablage.protokolliere(ordner, audit, anmeldung.user.name)
        db.commit()
    except BaseException:
        db.rollback()
        # Ablage wieder auf den Stand der DB bringen, falls nachricht.json schon geschrieben war
        db.refresh(nachricht)
        try:
            ablage.schreibe_nachricht(ordner, nachricht, nachricht.von_user.name, fehlend)
        except OSError:
            pass
        raise
    return True


def ablage_neu_aufbauen(db: Session, einsatz: Einsatz) -> int:
    """Nach einem gelöschten Einsatzordner: Gibt die Zahl der neu geschriebenen Nachrichten zurück."""
    if einsatz.ablage_ordner:
        ablage.schreibe_einsatz(ablage.pfad(einsatz.ablage_ordner), einsatz)
    neu = 0
    for n in reversed(list_for_einsatz(db, einsatz.id)):
        if n.ablage_ordner and ablage.baue_nachricht_neu(n, audit_for(db, n.id), _fehlende_anhaenge(db, n)):
            neu += 1
    return neu


def _fehlende_anhaenge(db: Session, nachricht: Nachricht) -> int:
    # Steht nur im Audit-Eintrag „erstellt“; beim Neuschreiben der Ablage darf der Hinweis nicht verloren gehen.
    erstellt = db.scalar(
        select(AuditEvent).where(AuditEvent.nachricht_id == nachricht.id, AuditEvent.aktion == "erstellt")
    )
    if erstellt is None:
        return 0
    return (erstellt.aenderungen.get("fehlende_anhaenge") or {}).get("neu") or 0


def list_for_anmeldung(db: Session, anmeldung: Anmeldung) -> list[Nachricht]:
    return list(
        db.scalars(select(Nachricht).where(Nachricht.anmeldung_id == anmeldung.id).order_by(Nachricht.lfd_nr.desc()))
    )


def list_for_einsatz(db: Session, einsatz_id: int) -> list[Nachricht]:
    return list(
        db.scalars(select(Nachricht).where(Nachricht.einsatz_id == einsatz_id).order_by(Nachricht.lfd_nr.desc()))
    )


def audit_for(db: Session, nachricht_id: int) -> list[AuditEvent]:
    return list(db.scalars(select(AuditEvent).where(AuditEvent.nachricht_id == nachricht_id).order_by(AuditEvent.id)))
