"""Einsatzablage: jede Nachricht mit Aufnahmen und Fotos menschenlesbar im Dateisystem.

Aufbau (Wurzel = `MELDI_ABLAGE_DIR`, wird beim Serverstart festgelegt):

    <wurzel>/2026-11-07_1432_Übung_E3/
        einsatz.json
        0007_EA-Brand/
            nachricht.txt     wie der Vordruck, zum Lesen
            nachricht.json    vollständig, inkl. Prüfsummen der Anhänge
            protokoll.jsonl   Audit, append-only
            an_1.webm  inhalt_1.webm  foto_1.jpg

Uploads (Aufnahmen, Fotos) entstehen, bevor die Nachricht existiert. Sie liegen bis zum Absenden lokal unter
`vorlaeufig/<anmeldung_id>/` (`Settings.vorlaeufig_dir`) und werden gelöscht, wenn sie nie in einer Nachricht landen
(nach dem Absenden, beim Abmelden, spätestens beim nächsten Serverstart).
"""

import hashlib
import json
import os
import re
import secrets
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.db import utcnow
from app.models import Anhang, AuditEvent, Einsatz, Nachricht

# Dateien einer Nachricht, die gerade abgesendet wird. In der Ablage, damit das Umbenennen auf demselben Laufwerk bleibt.
SENDEN = "_senden"
_ID = re.compile(r"[0-9a-f]{32}")
# Der MIME-Typ folgt aus der Endung, nie aus Angaben des Handys – sonst ließe sich z.B. HTML einschleusen.
MIME = {
    "webm": "audio/webm",
    "m4a": "audio/mp4",
    "ogg": "audio/ogg",
    "wav": "audio/wav",
    "jpg": "image/jpeg",
    "bin": "application/octet-stream",
}
# Zeichen, die unter Windows in Dateinamen verboten sind
_UNERLAUBT = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
# Windows: Virenscanner und Indexdienst öffnen frisch geschriebene Dateien kurz, dann scheitern Umbenennen und Ersetzen.
_SPERRE_WARTEN = (0.05, 0.1, 0.2, 0.4, 0.8)


def wurzel() -> Path:
    return get_settings().ablage_root


def pfad(relativ: str) -> Path:
    return wurzel() / relativ


def _trotz_sperre[T](aktion: Callable[[], T]) -> T:
    """Wiederholt `aktion`, solange eine Datei gesperrt ist. Bleibt sie gesperrt, kommt der Fehler durch."""
    for warten in _SPERRE_WARTEN:
        try:
            return aktion()
        except PermissionError:
            time.sleep(warten)
    return aktion()


def ordnername(text: str, max_len: int = 40) -> str:
    s = re.sub(r"\s+", "-", _UNERLAUBT.sub("", text).strip())[:max_len].strip(".-")
    return s or "ohne-Namen"


def lokal(dt: datetime) -> datetime:
    """Zeitzone des ELW-Rechners – so liest man die Zeiten auch im Vordruck."""
    return dt.astimezone()


def einsatz_ordnername(einsatz: Einsatz) -> str:
    return f"{lokal(einsatz.beginn):%Y-%m-%d_%H%M}_{ordnername(einsatz.bezeichnung)}_E{einsatz.id}"


def nachricht_ordnername(nachricht: Nachricht) -> str:
    return f"{nachricht.lfd_nr:04d}_{ordnername(nachricht.von_funktion)}"


# --- Vorläufige Uploads -------------------------------------------------------------------------------------


@dataclass
class Vorgemerkt:
    id: str
    datei: Path
    art: str
    feld: str | None
    ext: str
    hochgeladen_at: datetime
    meta: dict

    @property
    def mime(self) -> str:
        return MIME[self.ext]


def _vorlaeufig_dir(anmeldung_id: int) -> Path:
    return get_settings().vorlaeufig_dir / str(anmeldung_id)


def vormerken(anmeldung_id: int, *, art: str, feld: str | None, ext: str, data: bytes, meta: dict) -> str:
    """Legt einen Upload vorläufig ab und gibt seine ID zurück, die beim Absenden mitgeschickt wird."""
    if ext not in MIME:
        raise ValueError(f"Ungültige Dateiendung: {ext!r}")
    d = _vorlaeufig_dir(anmeldung_id)
    d.mkdir(parents=True, exist_ok=True)
    upload_id = secrets.token_hex(16)
    (d / f"{upload_id}.{ext}").write_bytes(data)
    info = {"art": art, "feld": feld, "ext": ext, "hochgeladen_at": utcnow().isoformat(), "meta": meta}
    # Die JSON-Datei zuletzt schreiben: Erst wenn sie existiert, gilt der Upload als vollständig.
    (d / f"{upload_id}.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    return upload_id


def _lies(info_datei: Path) -> Vorgemerkt | None:
    try:
        info = json.loads(info_datei.read_text(encoding="utf-8"))
        datei = info_datei.with_suffix(f".{info['ext']}")
        if info["ext"] not in MIME or not datei.is_file():
            return None
        return Vorgemerkt(
            id=info_datei.stem, datei=datei, art=info["art"], feld=info["feld"], ext=info["ext"],
            hochgeladen_at=datetime.fromisoformat(info["hochgeladen_at"]), meta=info["meta"],
        )
    except (OSError, ValueError, KeyError):
        return None


def hole(anmeldung_id: int, upload_id: str) -> Vorgemerkt | None:
    """Nur Uploads derselben Anmeldung – eine fremde ID ergibt None."""
    if not _ID.fullmatch(upload_id):
        return None
    return _lies(_vorlaeufig_dir(anmeldung_id) / f"{upload_id}.json")


def _loesche(*dateien: Path) -> None:
    for f in dateien:
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass  # z.B. gerade vom Virenscanner geöffnet – spätestens der Serverstart räumt auf


def verwerfen(anmeldung_id: int, *, ids: list[str] | None = None, bis: datetime | None = None) -> None:
    """Löscht vorläufige Uploads der Anmeldung.

    Ohne Angaben alle. Sonst die genannten `ids` und alle, die laut Server-Zeitstempel vor `bis` hochgeladen
    wurden. Ein Upload, der parallel zum Absenden noch läuft, bleibt so erhalten.
    """
    d = _vorlaeufig_dir(anmeldung_id)
    if not d.is_dir():
        return
    if ids is None and bis is None:
        shutil.rmtree(d, ignore_errors=True)
        return
    weg = set(ids or [])
    for info_datei in d.glob("*.json"):
        v = _lies(info_datei)
        if v is None:
            continue
        if v.id in weg or (bis is not None and v.hochgeladen_at < bis):
            _loesche(v.datei, info_datei)
    try:
        d.rmdir()  # nur wenn leer
    except OSError:
        pass


def aufraeumen() -> None:
    """Beim Serverstart: Uploads aus früheren Läufen gehören zu keiner gültigen Anmeldung mehr."""
    shutil.rmtree(get_settings().vorlaeufig_dir, ignore_errors=True)
    shutil.rmtree(wurzel() / SENDEN, ignore_errors=True)


def pruefe_schreibbar() -> None:
    """Beim Serverstart: Ein fehlender Datenträger soll sofort auffallen, nicht erst beim ersten Absenden."""
    wurzel().mkdir(parents=True, exist_ok=True)
    probe = wurzel() / f".schreibtest_{secrets.token_hex(4)}"
    probe.write_bytes(b"")
    _loesche(probe)


# --- Absenden -----------------------------------------------------------------------------------------------


@dataclass
class Bereitgestellt:
    """Dateien einer Nachricht, schon unter ihrem endgültigen Namen, aber noch im Bereitstellungsordner."""

    ordner: Path
    dateien: list[tuple[Vorgemerkt, str, int, str]] = field(default_factory=list)  # (Upload, Name, Größe, SHA-256)


def bereitstellen(vorgemerkt: list[Vorgemerkt]) -> Bereitgestellt:
    """Kopiert die Uploads in einen eigenen Ordner, bevor die Datenbank gesperrt wird.

    So hält das Absenden die SQLite-Schreibsperre nur für einen Ordner-Umbenennen und wenige kleine Dateien.
    """
    b = Bereitgestellt(ordner=wurzel() / SENDEN / secrets.token_hex(8))
    b.ordner.mkdir(parents=True)
    nummer: dict[str, int] = {}
    for v in vorgemerkt:
        praefix = v.feld if v.art == "audio" and v.feld else v.art
        nummer[praefix] = nummer.get(praefix, 0) + 1
        name = f"{praefix}_{nummer[praefix]}.{v.ext}"
        data = v.datei.read_bytes()
        (b.ordner / name).write_bytes(data)
        b.dateien.append((v, name, len(data), hashlib.sha256(data).hexdigest()))
    return b


def platz_schaffen(ordner: Path) -> None:
    """Ein vorhandener Ordner (Rest eines abgebrochenen Absendens o.ä.) wird umbenannt – nie überschrieben."""
    if not ordner.exists():
        return
    stempel = f"{datetime.now():%Y%m%d-%H%M%S}"
    ziel = ordner.with_name(f"{ordner.name}_alt_{stempel}")
    n = 1
    while ziel.exists():
        n += 1
        ziel = ordner.with_name(f"{ordner.name}_alt_{stempel}_{n}")
    verschiebe(ordner, ziel)


def verschiebe(quelle: Path, ziel: Path) -> None:
    _trotz_sperre(lambda: quelle.rename(ziel))


# --- Dokumente ----------------------------------------------------------------------------------------------


def _schreibe_atomar(datei: Path, text: str) -> None:
    tmp = datei.with_name(f".{datei.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    _trotz_sperre(lambda: os.replace(tmp, datei))


def schreibe_einsatz(ordner: Path, einsatz: Einsatz) -> None:
    """Nur bei Änderungen schreiben: unter Windows kann eine geöffnete Datei das Ersetzen verhindern."""
    ordner.mkdir(parents=True, exist_ok=True)
    daten = {
        "id": einsatz.id,
        "bezeichnung": einsatz.bezeichnung,
        "beginn": einsatz.beginn.isoformat(),
        "ende": einsatz.ende.isoformat() if einsatz.ende else None,
        "funktionen": [{"name": f.name, "aliase": f.alias_liste} for f in einsatz.funktionen],
    }
    text = json.dumps(daten, ensure_ascii=False, indent=2)
    datei = ordner / "einsatz.json"
    try:
        if datei.read_text(encoding="utf-8") == text:
            return
    except OSError:
        pass
    _schreibe_atomar(datei, text)


def _anhang_dict(a: Anhang) -> dict:
    return {
        "datei": a.dateiname, "art": a.art.value, "feld": a.feld, "mime": a.mime, "groesse": a.groesse,
        "sha256": a.sha256, "hochgeladen_at": a.hochgeladen_at.isoformat(), "meta": a.meta,
    }


def _zeit(dt: datetime | None) -> str:
    return f"{lokal(dt):%d.%m.%Y %H:%M:%S}" if dt else "–"


def _anhang_zeile(a: Anhang) -> str:
    m = a.meta
    if a.art == "audio":
        teile = [f"Sprachaufnahme {a.feld}"]
        if "audio_sekunden" in m:
            teile.append(f"{m['audio_sekunden']:.1f} s".replace(".", ","))
        if m.get("rohtext"):
            teile.append(f"erkannt: „{m['rohtext']}“")
    else:
        teile = ["Foto"]
        if m.get("aufgenommen_at"):
            teile.append(f"aufgenommen {_zeit(datetime.fromisoformat(m['aufgenommen_at']))}")
        if m.get("gps"):
            teile.append(f"GPS {m['gps']['lat']:.6f}, {m['gps']['lon']:.6f}")
    return f"  {a.dateiname:<16} {' · '.join(teile)}\n  {'':<16} SHA-256 {a.sha256}"


def nachricht_text(
    n: Nachricht, von_name: str, fehlende_anhaenge: int = 0, fehlende_dateien: list[str] | None = None
) -> str:
    def art(feld: str) -> str:
        e = n.eingabe.get(feld) or {}
        return f"Sprache (Modell {e.get('modell', '?')})" if e.get("art") == "sprache" else "Tastatur"

    zeilen = [
        f"Nachricht Nr. {n.lfd_nr}",
        f"Einsatz:          {n.einsatz.bezeichnung}",
        "",
        f"Von:              {n.von_funktion} ({von_name})",
        f"An:               {n.an}",
        f"Eingang ELW:      {_zeit(n.eingang_at)}",
        f"Erfasst (Handy):  {_zeit(n.erfasst_at)}",
        f"Eingabe An:       {art('an')}",
        f"Eingabe Inhalt:   {art('inhalt')}",
        "",
        "Inhalt:",
        n.inhalt,
    ]
    roh = {f: (n.eingabe.get(f) or {}).get("rohtext") for f in ("an", "inhalt")}
    if any(roh.values()):
        zeilen += ["", "Spracherkennung (Rohtext):"]
        zeilen += [f"  {f.capitalize()}: {t}" for f, t in roh.items() if t]
    if n.anhaenge:
        zeilen += ["", "Anhänge:"] + [_anhang_zeile(a) for a in n.anhaenge]
    if fehlende_anhaenge:
        zeilen += ["", f"Hinweis: {fehlende_anhaenge} Anhang/Anhänge kamen nicht an (z.B. Serverneustart vor dem Absenden)."]
    if fehlende_dateien:
        zeilen += ["", f"Hinweis: Diese Dateien fehlen im Ordner (Einsatzordner wurde gelöscht): {', '.join(fehlende_dateien)}"]
    return "\n".join(zeilen) + "\n"


def schreibe_nachricht(ordner: Path, n: Nachricht, von_name: str, fehlende_anhaenge: int = 0) -> None:
    # Aus dem Ordner bestimmt, nicht gespeichert: So geht der Hinweis auch bei späteren Statuswechseln nicht verloren.
    fehlende_dateien = [a.dateiname for a in n.anhaenge if not (ordner / a.dateiname).is_file()]
    daten = {
        "einsatz": {"id": n.einsatz_id, "bezeichnung": n.einsatz.bezeichnung},
        "lfd_nr": n.lfd_nr,
        "von_funktion": n.von_funktion,
        "von_name": von_name,
        "an": n.an,
        "inhalt": n.inhalt,
        "status": n.status.value,
        "erfasst_at": n.erfasst_at.isoformat() if n.erfasst_at else None,
        "eingang_at": n.eingang_at.isoformat(),
        "eingabe": n.eingabe,
        "anhaenge": [_anhang_dict(a) for a in n.anhaenge],
        "fehlende_anhaenge": fehlende_anhaenge,
        "fehlende_dateien": fehlende_dateien,
    }
    _schreibe_atomar(ordner / "nachricht.json", json.dumps(daten, ensure_ascii=False, indent=2))
    _schreibe_atomar(ordner / "nachricht.txt", nachricht_text(n, von_name, fehlende_anhaenge, fehlende_dateien))


def _protokoll_zeile(zeitpunkt: datetime, aktion: str, funktion: str, name: str, aenderungen: dict) -> str:
    eintrag = {
        "zeitpunkt": zeitpunkt.isoformat(), "aktion": aktion, "funktion": funktion, "name": name,
        "aenderungen": aenderungen,
    }
    return json.dumps(eintrag, ensure_ascii=False) + "\n"


def protokolliere(ordner: Path, a: AuditEvent, von_name: str) -> None:
    zeile = _protokoll_zeile(a.zeitpunkt, a.aktion, a.funktion, von_name, a.aenderungen)

    def anhaengen() -> None:
        with (ordner / "protokoll.jsonl").open("a", encoding="utf-8") as f:
            f.write(zeile)

    _trotz_sperre(anhaengen)


def baue_nachricht_neu(n: Nachricht, audits: list[AuditEvent], fehlende_anhaenge: int) -> bool:
    """Schreibt die lesbaren Einträge einer Nachricht aus der Datenbank neu. Audio und Fotos sind damit nicht zurück.

    `protokoll.jsonl` entsteht zuletzt und markiert die Nachricht als fertig. So läuft ein abgebrochener oder
    wiederholter Neuaufbau gefahrlos noch einmal, ohne vorhandene Einträge anzufassen.
    """
    ordner = pfad(n.ablage_ordner)
    if (ordner / "protokoll.jsonl").exists():
        return False
    ordner.mkdir(parents=True, exist_ok=True)
    schreibe_nachricht(ordner, n, n.von_user.name, fehlende_anhaenge)
    zeilen = [_protokoll_zeile(a.zeitpunkt, a.aktion, a.funktion, a.user.name, a.aenderungen) for a in audits]
    fehlend = [a.dateiname for a in n.anhaenge if not (ordner / a.dateiname).is_file()]
    zeilen.append(_protokoll_zeile(
        utcnow(), "ablage_neu_aufgebaut", "System", "Meldi", {"fehlende_dateien": {"alt": None, "neu": fehlend}}
    ))
    _schreibe_atomar(ordner / "protokoll.jsonl", "".join(zeilen))
    return True
