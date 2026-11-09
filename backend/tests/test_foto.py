import io
import json

import pytest
from PIL import ExifTags, Image

from app.config import get_settings
from app.services import ablage


def jpeg(breite: int = 300, hoehe: int = 200, *, exif: Image.Exif | None = None) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (breite, hoehe), "orange").save(buf, "JPEG", **({"exif": exif} if exif else {}))
    return buf.getvalue()


def lade_hoch(client, data: bytes, **form):
    return client.post("/api/uploads/foto", data=form, files={"datei": ("foto.jpg", data, "image/jpeg")})


def sende(client, anhaenge):
    return client.post("/api/messages", json={"an": "Einsatzleitung", "inhalt": "Lagebild", "anhaenge": anhaenge})


def test_foto_mit_gps_landet_in_der_ablage(melder, elw):
    r = lade_hoch(melder, jpeg(), gps_lat="50.110924", gps_lon="-8.682127", aufgenommen_at="2026-11-07T14:31:40+01:00")
    assert r.status_code == 201, r.text
    assert r.json()["breite"] == 300
    n = sende(melder, [r.json()["foto_id"]]).json()

    (a,) = n["anhaenge"]
    assert a["art"] == "foto" and a["dateiname"] == "foto_1.jpg" and a["mime"] == "image/jpeg"
    assert a["meta"]["gps"] == {"lat": 50.110924, "lon": -8.682127}

    bild = elw.get(f"/api/messages/{n['id']}/anhaenge/{a['id']}")
    assert bild.status_code == 200 and bild.headers["content-type"] == "image/jpeg"
    gps = Image.open(io.BytesIO(bild.content)).getexif().get_ifd(ExifTags.IFD.GPSInfo)
    assert gps[ExifTags.GPS.GPSLatitudeRef] == "N" and gps[ExifTags.GPS.GPSLongitudeRef] == "W"
    grad, minuten, sekunden = (float(x) for x in gps[ExifTags.GPS.GPSLatitude])
    assert grad + minuten / 60 + sekunden / 3600 == pytest.approx(50.110924, abs=1e-6)

    (ordner,) = [p for p in get_settings().ablage_root.iterdir() if p.name != ablage.SENDEN]
    txt = (ordner / "0001_EA-Brand" / "nachricht.txt").read_text(encoding="utf-8")
    assert "foto_1.jpg" in txt and "GPS 50.110924, -8.682127" in txt
    daten = json.loads((ordner / "0001_EA-Brand" / "nachricht.json").read_text(encoding="utf-8"))
    assert daten["anhaenge"][0]["meta"]["aufgenommen_at"] == "2026-11-07T14:31:40+01:00"


def test_foto_ohne_gps(melder):
    r = lade_hoch(melder, jpeg())
    n = sende(melder, [r.json()["foto_id"]]).json()
    assert "gps" not in n["anhaenge"][0]["meta"]


def test_fremde_metadaten_werden_entfernt(melder, elw):
    exif = Image.Exif()
    exif[ExifTags.Base.Make] = "Geheim-Handy"
    r = lade_hoch(melder, jpeg(exif=exif))
    n = sende(melder, [r.json()["foto_id"]]).json()
    bild = elw.get(f"/api/messages/{n['id']}/anhaenge/{n['anhaenge'][0]['id']}").content
    assert ExifTags.Base.Make not in Image.open(io.BytesIO(bild)).getexif()


def test_grosse_fotos_werden_begrenzt(melder):
    r = lade_hoch(melder, jpeg(5000, 1000))
    assert (r.json()["breite"], r.json()["hoehe"]) == (4096, 819)


@pytest.mark.parametrize("data", [b"kein bild", b""])
def test_kein_bild_wird_abgewiesen(melder, data):
    assert lade_hoch(melder, data).status_code == 400


@pytest.mark.filterwarnings("ignore::PIL.Image.DecompressionBombWarning")
@pytest.mark.parametrize("groesse", [(6000, 5000), (12000, 12000)])
def test_riesige_aufloesung_wird_vor_dem_dekodieren_abgewiesen(melder, groesse):
    buf = io.BytesIO()
    Image.new("1", groesse).save(buf, "PNG")  # wenige KB, aber 30 bzw. 144 MP
    r = lade_hoch(melder, buf.getvalue())
    assert r.status_code == 400


def test_gif_wird_abgewiesen(melder):
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, "GIF")
    assert lade_hoch(melder, buf.getvalue()).status_code == 400


def test_ungueltige_koordinaten(melder):
    assert lade_hoch(melder, jpeg(), gps_lat="91", gps_lon="0").status_code == 422
    assert lade_hoch(melder, jpeg(), aufgenommen_at="2026-11-07T14:31:40").status_code == 422  # ohne Zeitzone


def test_zu_grosses_foto(melder, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_foto_bytes", 100)
    assert lade_hoch(melder, jpeg()).status_code == 413


def test_hoechstens_fuenf_fotos(melder):
    ids = [lade_hoch(melder, jpeg()).json()["foto_id"] for _ in range(6)]
    r = sende(melder, ids)
    assert r.status_code == 400 and "5 Fotos" in r.json()["detail"]
    assert sende(melder, ids[:5]).status_code == 201


def test_upload_nur_angemeldet(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        assert lade_hoch(c, jpeg()).status_code == 401


def test_csp_erlaubt_vorschaubilder(melder):
    assert "img-src 'self' data: blob:" in melder.get("/api/auth/me").headers["content-security-policy"]
