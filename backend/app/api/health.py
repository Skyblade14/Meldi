from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["health"])


class HealthOut(BaseModel):
    ok: bool
    stt_bereit: bool


@router.get("/health", response_model=HealthOut)
def health(request: Request) -> HealthOut:
    """Für das Startfenster. Ohne Anmeldung, deshalb nichts über den Einsatz."""
    stt = request.app.state.stt
    return HealthOut(ok=True, stt_bereit=stt is not None and stt.ready)
