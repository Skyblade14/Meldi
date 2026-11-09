"""Standard-Stammdaten für neue Einsätze."""

from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Einsatz, Funktion

# (Name, gesprochene Varianten)
STANDARD_FUNKTIONEN: list[tuple[str, str]] = [
    ("Einsatzleitung", "EL, Einsatzleiter"),
    ("ELW", "Einsatzleitwagen, Führungsassistent"),
    ("EA Brand", "Brandbekämpfung"),
    ("EA Wasserversorgung", "EA Wasser, Abschnitt Wasser"),
    ("EA Atemschutz", "Atemschutz"),
    ("EA Technische Hilfe", "EA THL, Technische Hilfeleistung"),
    ("Atemschutzüberwachung", "ASÜ"),
    ("Bereitstellungsraum", "BR, Bereitstellung"),
    ("Rettungsdienst", "RD, OrgL, Organisatorischer Leiter"),
    ("Polizei", ""),
]


def einsatz_oeffnen(db: Session, bezeichnung: str) -> Einsatz:
    """Beim Serverstart: Ein laufender Einsatz wird fortgesetzt, nur ohne ihn entsteht ein neuer."""
    return db.query(Einsatz).filter(Einsatz.ende.is_(None)).order_by(Einsatz.beginn.desc()).first() or neuer_einsatz(
        db, bezeichnung
    )


def neuer_einsatz(db: Session, bezeichnung: str) -> Einsatz:
    for alt in db.query(Einsatz).filter(Einsatz.ende.is_(None)):
        alt.ende = utcnow()
    einsatz = Einsatz(bezeichnung=bezeichnung)
    einsatz.funktionen = [
        Funktion(name=name, aliase=aliase, sortierung=i) for i, (name, aliase) in enumerate(STANDARD_FUNKTIONEN)
    ]
    db.add(einsatz)
    db.commit()
    return einsatz
