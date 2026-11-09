"""Einsatzordner erkennen und vorbereiten, ohne Oberfläche.

Der gewählte Ordner (meist auf der NAS) ist die Einsatzakte und trägt die Kennungsdatei. Die Datenbank liegt lokal
unter `<data_dir>/einsaetze/<kennung>/meldi.db`, weil SQLite im WAL-Modus auf Netzlaufwerken nicht zuverlässig läuft.
Alle Zugriffe auf den Ordner können auf einer NAS hängen und gehören deshalb nicht in den Tk-Thread.
"""

import json
import os
import re
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

KENNUNGSDATEI = "meldi-einsatz.json"
_STARTER_DATEI = "starter.json"
_DB_DATEI = "meldi.db"
MAX_BEZEICHNUNG = 200
# Die Kennung wird Teil eines lokalen Pfads und kommt aus einer Datei auf der NAS.
_KENNUNG = re.compile(r"[0-9a-f]{32}")


class KennungFehler(Exception):
    """Die Kennungsdatei existiert, lässt sich aber nicht lesen oder ist ungültig."""


class OrdnerArt(StrEnum):
    NEU = "neu"
    VORHANDEN = "vorhanden"
    DB_FEHLT = "db_fehlt"
    FREMD = "fremd"
    UNBRAUCHBAR = "unbrauchbar"


@dataclass(frozen=True)
class Kennung:
    kennung: str
    bezeichnung: str
    beginn: datetime | None


@dataclass(frozen=True)
class EinsatzInfo:
    kennung: str
    bezeichnung: str
    beginn: datetime | None = None
    nachrichten: int = 0
    ordner: Path | None = None
    ordner_fehlt: bool = False
    zuletzt: datetime | None = None


@dataclass(frozen=True)
class Analyse:
    art: OrdnerArt
    ordner: Path
    einsatz: EinsatzInfo | None = None
    fehler: str | None = None


@dataclass(frozen=True)
class Startauftrag:
    kennung: str
    bezeichnung: str
    ordner: Path
    neu_aufbauen: bool = False


@dataclass(frozen=True)
class Vorschlag:
    """Was das Startfenster zum gewählten Ordner anbietet."""

    knopf: str
    erlaubt: bool
    name_gesperrt: bool
    hinweis: str
    bezeichnung: str | None = None
    rueckfrage: str | None = None


def einsatz_verzeichnis(data_dir: Path, kennung: str) -> Path:
    return data_dir / "einsaetze" / kennung


def einsatz_db(data_dir: Path, kennung: str) -> Path:
    return einsatz_verzeichnis(data_dir, kennung) / _DB_DATEI


def _zeit(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # SQLite speichert UTC ohne Zeitzone


def _schreibe_atomar(datei: Path, text: str) -> None:
    tmp = datei.with_name(f".{datei.name}.{secrets.token_hex(4)}.tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        os.replace(tmp, datei)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def lies_kennung(ordner: Path) -> Kennung | None:
    """None, wenn der Ordner keine Kennungsdatei hat. Eine beschädigte Datei ist ein Fehler, kein neuer Ordner."""
    try:
        text = (ordner / KENNUNGSDATEI).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise KennungFehler(f"Kennungsdatei nicht lesbar: {exc}") from exc
    try:
        daten = json.loads(text)
        kennung, bezeichnung = daten["kennung"], daten["bezeichnung"]
    except (ValueError, KeyError, TypeError) as exc:
        raise KennungFehler("Kennungsdatei ist beschädigt") from exc
    if not isinstance(kennung, str) or not _KENNUNG.fullmatch(kennung) or not isinstance(bezeichnung, str):
        raise KennungFehler("Kennungsdatei ist beschädigt")
    beginn = daten.get("beginn")
    return Kennung(kennung, bezeichnung, _zeit(beginn) if isinstance(beginn, str) else None)


def schreibe_kennung(ordner: Path, kennung: str, bezeichnung: str, beginn: datetime) -> None:
    daten = {"kennung": kennung, "bezeichnung": bezeichnung, "beginn": beginn.isoformat()}
    _schreibe_atomar(ordner / KENNUNGSDATEI, json.dumps(daten, ensure_ascii=False, indent=2))


def kennung_vorhanden(ordner: Path, kennung: str) -> bool:
    """Für die Überwachung im Betrieb: Auch ein nicht erreichbarer Ordner zählt als fehlend."""
    try:
        gelesen = lies_kennung(ordner)
    except KennungFehler:
        return False
    return gelesen is not None and gelesen.kennung == kennung


def _lies_db(db: Path) -> tuple[str, datetime | None, int] | None:
    """Liest den Einsatz schreibgeschützt. None, wenn es die Datei oder das Schema (noch) nicht gibt."""
    if not db.is_file():
        return None
    try:
        verbindung = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True, timeout=2)
    except sqlite3.Error:
        return None
    try:
        zeile = verbindung.execute(
            "SELECT bezeichnung, beginn, naechste_lfd_nr FROM einsatz WHERE ende IS NULL ORDER BY beginn DESC LIMIT 1"
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        verbindung.close()
    if zeile is None:
        return None
    return zeile[0], _zeit(zeile[1]), max(zeile[2] - 1, 0)


def _einsatz_info(data_dir: Path, kennung: Kennung, ordner: Path) -> EinsatzInfo:
    aus_db = _lies_db(einsatz_db(data_dir, kennung.kennung))
    if aus_db is None:
        return EinsatzInfo(kennung.kennung, kennung.bezeichnung, kennung.beginn, ordner=ordner)
    bezeichnung, beginn, nachrichten = aus_db
    return EinsatzInfo(kennung.kennung, bezeichnung, beginn or kennung.beginn, nachrichten, ordner)


def _nur_interne_dateien(inhalt: list[str]) -> bool:
    return all(name == KENNUNGSDATEI or name.startswith((".", "_")) for name in inhalt)


def analysiere(data_dir: Path, ordner: Path) -> Analyse:
    try:
        if not ordner.exists():
            return Analyse(OrdnerArt.NEU, ordner)
        if not ordner.is_dir():
            return Analyse(OrdnerArt.UNBRAUCHBAR, ordner, fehler="Das ist kein Ordner.")
        inhalt = [eintrag.name for eintrag in ordner.iterdir()]
    except OSError as exc:
        return Analyse(OrdnerArt.UNBRAUCHBAR, ordner, fehler=f"Ordner nicht lesbar: {exc}")
    try:
        kennung = lies_kennung(ordner)
    except KennungFehler as exc:
        return Analyse(OrdnerArt.UNBRAUCHBAR, ordner, fehler=str(exc))
    if kennung is None:
        return Analyse(OrdnerArt.NEU if not inhalt else OrdnerArt.FREMD, ordner)
    info = _einsatz_info(data_dir, kennung, ordner)
    # Ohne Datenbank, aber auch ohne Nachrichten (Start abgebrochen) geht nichts verloren, wenn man weitermacht.
    if einsatz_db(data_dir, kennung.kennung).is_file() or _nur_interne_dateien(inhalt):
        return Analyse(OrdnerArt.VORHANDEN, ordner, info)
    return Analyse(OrdnerArt.DB_FEHLT, ordner, info)


def pruefe_beschreibbar(ordner: Path) -> None:
    """Legt den Ordner bei Bedarf an. Löst OSError aus, wenn nicht geschrieben werden kann."""
    ordner.mkdir(parents=True, exist_ok=True)
    probe = ordner / f".schreibtest_{secrets.token_hex(4)}"
    probe.write_bytes(b"")
    probe.unlink()


def merke_einsatz(data_dir: Path, kennung: str, ordner: Path, bezeichnung: str, beginn: datetime | None) -> None:
    verzeichnis = einsatz_verzeichnis(data_dir, kennung)
    verzeichnis.mkdir(parents=True, exist_ok=True)
    daten = {
        "ordner": str(ordner),
        "bezeichnung": bezeichnung,
        "beginn": beginn.isoformat() if beginn else None,
        "zuletzt": datetime.now(UTC).isoformat(),
    }
    _schreibe_atomar(verzeichnis / _STARTER_DATEI, json.dumps(daten, ensure_ascii=False, indent=2))


def _lies_starter(verzeichnis: Path) -> dict | None:
    try:
        daten = json.loads((verzeichnis / _STARTER_DATEI).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return daten if isinstance(daten, dict) else None


def bekannte_einsaetze(data_dir: Path) -> list[EinsatzInfo]:
    """Alle Einsätze mit lokalen Daten, zuletzt verwendete zuerst."""
    try:
        verzeichnisse = list((data_dir / "einsaetze").iterdir())
    except OSError:
        return []
    einsaetze = []
    for verzeichnis in verzeichnisse:
        if not _KENNUNG.fullmatch(verzeichnis.name):
            continue
        starter = _lies_starter(verzeichnis)
        aus_db = _lies_db(verzeichnis / _DB_DATEI)
        if starter is None and aus_db is None:
            continue
        starter = starter or {}
        ordner_text = starter.get("ordner")
        ordner = Path(ordner_text) if isinstance(ordner_text, str) else None
        bezeichnung, beginn, nachrichten = aus_db or (str(starter.get("bezeichnung") or "ohne Namen"), None, 0)
        einsaetze.append(EinsatzInfo(
            kennung=verzeichnis.name,
            bezeichnung=bezeichnung,
            beginn=beginn or _zeit(starter.get("beginn")),
            nachrichten=nachrichten,
            ordner=ordner,
            ordner_fehlt=ordner is None or not kennung_vorhanden(ordner, verzeichnis.name),
            zuletzt=_zeit(starter.get("zuletzt")),
        ))
    minimum = datetime.min.replace(tzinfo=UTC)
    return sorted(einsaetze, key=lambda e: e.zuletzt or e.beginn or minimum, reverse=True)


def _pruefe_bezeichnung(bezeichnung: str) -> str:
    bezeichnung = bezeichnung.strip()
    if not bezeichnung:
        raise ValueError("Bitte einen Einsatznamen eingeben.")
    if len(bezeichnung) > MAX_BEZEICHNUNG:
        raise ValueError(f"Der Einsatzname darf höchstens {MAX_BEZEICHNUNG} Zeichen lang sein.")
    return bezeichnung


def neuer_einsatz(data_dir: Path, ordner: Path, bezeichnung: str) -> Startauftrag:
    bezeichnung = _pruefe_bezeichnung(bezeichnung)
    pruefe_beschreibbar(ordner)
    kennung = uuid.uuid4().hex
    beginn = datetime.now(UTC)
    merke_einsatz(data_dir, kennung, ordner, bezeichnung, beginn)
    schreibe_kennung(ordner, kennung, bezeichnung, beginn)
    return Startauftrag(kennung, bezeichnung, ordner)


def einsatz_fortsetzen(data_dir: Path, analyse: Analyse) -> Startauftrag:
    if analyse.art != OrdnerArt.VORHANDEN or analyse.einsatz is None:
        raise ValueError("Dieser Ordner enthält keinen Einsatz, der fortgesetzt werden kann.")
    einsatz = analyse.einsatz
    pruefe_beschreibbar(analyse.ordner)
    merke_einsatz(data_dir, einsatz.kennung, analyse.ordner, einsatz.bezeichnung, einsatz.beginn)
    return Startauftrag(einsatz.kennung, einsatz.bezeichnung, analyse.ordner)


def in_neuem_ordner_fortsetzen(data_dir: Path, einsatz: EinsatzInfo, ordner: Path) -> Startauftrag:
    """Der Ordner eines bekannten Einsatzes fehlt: neu anlegen, der Server baut die Ablage aus der Datenbank auf."""
    vorhanden = lies_kennung(ordner) if ordner.is_dir() else None
    if vorhanden is not None and vorhanden.kennung != einsatz.kennung:
        raise ValueError("Dieser Ordner gehört zu einem anderen Einsatz.")
    pruefe_beschreibbar(ordner)
    beginn = einsatz.beginn or datetime.now(UTC)
    merke_einsatz(data_dir, einsatz.kennung, ordner, einsatz.bezeichnung, beginn)
    schreibe_kennung(ordner, einsatz.kennung, einsatz.bezeichnung, beginn)
    return Startauftrag(einsatz.kennung, einsatz.bezeichnung, ordner, neu_aufbauen=True)


def _ist_umzug(analyse: Analyse, umzug: EinsatzInfo | None) -> bool:
    return umzug is not None and analyse.art in (OrdnerArt.NEU, OrdnerArt.FREMD)


def vorbereiten(data_dir: Path, analyse: Analyse, umzug: EinsatzInfo | None, bezeichnung: str) -> Startauftrag:
    """Führt aus, was `vorschlag()` für dieselbe Analyse angeboten hat."""
    if umzug is not None and _ist_umzug(analyse, umzug):
        return in_neuem_ordner_fortsetzen(data_dir, umzug, analyse.ordner)
    if analyse.art == OrdnerArt.VORHANDEN:
        return einsatz_fortsetzen(data_dir, analyse)
    if umzug is None and analyse.art in (OrdnerArt.NEU, OrdnerArt.FREMD):
        return neuer_einsatz(data_dir, analyse.ordner, bezeichnung)
    raise ValueError(analyse.fehler or "Dieser Ordner kann nicht verwendet werden.")


_FREMD_RUECKFRAGE = "Der Ordner enthält bereits andere Dateien. Trotzdem für diesen Einsatz verwenden?"


def beschreibe_einsatz(einsatz: EinsatzInfo) -> str:
    beginn = f"{einsatz.beginn.astimezone():%d.%m.%Y %H:%M}" if einsatz.beginn else "unbekannt"
    return f"„{einsatz.bezeichnung}“, begonnen {beginn}, {einsatz.nachrichten} Nachrichten"


def vorschlag(analyse: Analyse, umzug: EinsatzInfo | None) -> Vorschlag:
    if analyse.art == OrdnerArt.UNBRAUCHBAR:
        return Vorschlag("Einsatz starten", False, False, analyse.fehler or "Dieser Ordner kann nicht verwendet werden.")
    if analyse.art == OrdnerArt.VORHANDEN and analyse.einsatz is not None:
        if umzug is None or analyse.einsatz.kennung == umzug.kennung:
            hinweis = f"Vorhandener Einsatz: {beschreibe_einsatz(analyse.einsatz)}"
            return Vorschlag("Einsatz fortsetzen", True, True, hinweis, analyse.einsatz.bezeichnung)
    if umzug is not None:
        if _ist_umzug(analyse, umzug):
            hinweis = (
                "Nachrichten und Protokoll werden aus der Datenbank neu geschrieben. "
                "Audio und Fotos aus dem alten Ordner fehlen und werden vermerkt."
            )
            rueckfrage = _FREMD_RUECKFRAGE if analyse.art == OrdnerArt.FREMD else None
            return Vorschlag("In neuem Ordner fortsetzen", True, True, hinweis, umzug.bezeichnung, rueckfrage)
        return Vorschlag("In neuem Ordner fortsetzen", False, True, "Dieser Ordner gehört zu einem anderen Einsatz.",
                         umzug.bezeichnung)
    if analyse.art == OrdnerArt.DB_FEHLT:
        return Vorschlag(
            "Einsatz fortsetzen", False, True,
            "Zu diesem Ordner gehört ein Einsatz, dessen Datenbank auf diesem Rechner fehlt. Bitte anderen Ordner wählen.",
            analyse.einsatz.bezeichnung if analyse.einsatz else None,
        )
    if analyse.art == OrdnerArt.FREMD:
        return Vorschlag("Einsatz starten", True, False, "Neuer Einsatz in einem Ordner mit anderen Dateien.",
                         rueckfrage=_FREMD_RUECKFRAGE)
    return Vorschlag("Einsatz starten", True, False, "Neuer Einsatz.")
