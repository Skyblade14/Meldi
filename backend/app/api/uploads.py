from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import AwareDatetime, BaseModel

from app.api.deps import MeldeAnmeldung
from app.config import get_settings
from app.services import ablage, foto

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


class FotoOut(BaseModel):
    foto_id: str
    breite: int
    hoehe: int


@router.post("/foto", response_model=FotoOut, status_code=201)
def upload_foto(
    anmeldung: MeldeAnmeldung,
    datei: Annotated[UploadFile, File()],
    gps_lat: Annotated[float | None, Form(ge=-90, le=90)] = None,
    gps_lon: Annotated[float | None, Form(ge=-180, le=180)] = None,
    aufgenommen_at: Annotated[AwareDatetime | None, Form()] = None,
) -> FotoOut:
    """Foto vorläufig ablegen. Die ID kommt beim Absenden in `anhaenge` der Nachricht.

    Synchron, damit das Dekodieren im Thread-Pool läuft und den Event-Loop nicht blockiert.
    """
    maximum = get_settings().max_foto_bytes
    data = datei.file.read(maximum + 1)
    if len(data) > maximum:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Foto zu groß")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Leeres Foto")

    gps = foto.Gps(gps_lat, gps_lon) if gps_lat is not None and gps_lon is not None else None
    try:
        f = foto.normalisiere(data, gps, aufgenommen_at)
    except foto.FotoFehler as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None

    meta: dict = {"breite": f.breite, "hoehe": f.hoehe}
    if gps:
        meta["gps"] = {"lat": gps.lat, "lon": gps.lon}
    if aufgenommen_at:
        meta["aufgenommen_at"] = aufgenommen_at.isoformat()
    foto_id = ablage.vormerken(anmeldung.id, art="foto", feld=None, ext="jpg", data=f.data, meta=meta)
    return FotoOut(foto_id=foto_id, breite=f.breite, hoehe=f.hoehe)
