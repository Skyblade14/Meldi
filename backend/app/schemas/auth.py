from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints, model_validator

from app.models import Rolle

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
FunktionName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class LoginRequest(BaseModel):
    name: Name
    rolle: Rolle
    funktion: FunktionName | None = None  # nur Beobachter dürfen sie weglassen

    @model_validator(mode="after")
    def _funktion_setzen(self) -> "LoginRequest":
        if self.funktion is None:
            if self.rolle != Rolle.BEOBACHTER:
                raise ValueError("Funktion fehlt")
            self.funktion = "Beobachter"
        return self


class FunktionOut(BaseModel):
    id: int
    name: str


class MeOut(BaseModel):
    name: str
    rolle: Rolle
    funktion: str
    einsatz: str


class AnmeldungOut(BaseModel):
    name: str
    rolle: Rolle
    funktion: str
    angemeldet_at: datetime
