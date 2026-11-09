"""Fotos prüfen und vereinheitlichen, bevor sie in die Einsatzablage gehen."""

import io
import threading
from dataclasses import dataclass
from datetime import datetime

from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError

MAX_KANTE = 4096  # das Handy verkleinert schon auf 2560 px, das hier ist nur die Obergrenze
# Schutz vor „Dekompressionsbomben“ (kleine Datei, riesiges Bild): Abmessungen prüfen, bevor dekodiert wird.
# 25 MP entsprechen ~75 MB im Speicher; Fotos vom Handy haben nach dem Verkleinern höchstens ~6,5 MP.
MAX_PIXEL = 25_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXEL  # zusätzliche Sicherung in Pillow selbst
ERLAUBTE_FORMATE = ["JPEG", "PNG", "WEBP"]
# Höchstens zwei Fotos gleichzeitig dekodieren – begrenzt den Speicherbedarf auf dem ELW-Rechner.
_dekodieren = threading.BoundedSemaphore(2)


class FotoFehler(ValueError):
    pass


@dataclass
class Gps:
    lat: float
    lon: float


@dataclass
class Foto:
    data: bytes
    breite: int
    hoehe: int


def _dms(wert: float) -> tuple[float, float, float]:
    wert = abs(wert)
    grad = int(wert)
    minuten = int((wert - grad) * 60)
    sekunden = round(((wert - grad) * 60 - minuten) * 60, 4)
    return float(grad), float(minuten), sekunden


def _exif(gps: Gps | None, aufgenommen_at: datetime | None) -> Image.Exif:
    exif = Image.Exif()
    if gps:
        exif[ExifTags.IFD.GPSInfo] = {
            ExifTags.GPS.GPSLatitudeRef: "N" if gps.lat >= 0 else "S",
            ExifTags.GPS.GPSLatitude: _dms(gps.lat),
            ExifTags.GPS.GPSLongitudeRef: "E" if gps.lon >= 0 else "W",
            ExifTags.GPS.GPSLongitude: _dms(gps.lon),
        }
    if aufgenommen_at:
        # EXIF kennt keine Zeitzone – Ortszeit des ELW-Rechners, wie im Vordruck.
        exif[ExifTags.IFD.Exif] = {ExifTags.Base.DateTimeOriginal: f"{aufgenommen_at.astimezone():%Y:%m:%d %H:%M:%S}"}
    return exif


def normalisiere(data: bytes, gps: Gps | None, aufgenommen_at: datetime | None) -> Foto:
    """Dekodiert das Bild vollständig und speichert es neu als JPEG.

    So landet nur, was wirklich ein Bild ist, in der Ablage – ohne fremde Metadaten. GPS und Aufnahmezeit
    hat das Handy vor dem Verkleinern ausgelesen; sie kommen hier wieder in die EXIF-Daten.
    """
    with _dekodieren:
        try:
            with Image.open(io.BytesIO(data), formats=ERLAUBTE_FORMATE) as quelle:
                breite, hoehe = quelle.size  # nur der Header ist gelesen, noch nichts dekodiert
                if breite * hoehe > MAX_PIXEL:
                    raise FotoFehler(f"Foto hat zu viele Bildpunkte ({breite}×{hoehe})")
                bild = ImageOps.exif_transpose(quelle).convert("RGB")
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError):
            raise FotoFehler("Foto nicht lesbar – nur JPEG, PNG oder WebP") from None
        bild.thumbnail((MAX_KANTE, MAX_KANTE))
        buf = io.BytesIO()
        bild.save(buf, "JPEG", quality=90, exif=_exif(gps, aufgenommen_at))
    return Foto(data=buf.getvalue(), breite=bild.width, hoehe=bild.height)
