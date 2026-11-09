"""Zentrale Konfiguration. Werte kommen aus Umgebungsvariablen (Präfix MELDI_) oder backend/.env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MELDI_", env_file=BACKEND_DIR / ".env", extra="ignore")

    data_dir: Path = PROJECT_DIR / "data"
    database_url: str = ""  # leer = SQLite in data_dir
    frontend_dist: Path = PROJECT_DIR / "frontend" / "dist"

    # Session-Cookie. secure=False nur für lokale Entwicklung ohne HTTPS.
    cookie_secure: bool = True
    session_hours: int = 24

    # Spracherkennung
    stt_enabled: bool = True
    stt_model: str = "large-v3-turbo"  # Name oder Pfad zu einem CTranslate2-Modell
    stt_device: Literal["cpu", "cuda", "auto"] = "cpu"
    stt_compute_type: str = "int8"
    stt_cpu_threads: int = 0  # 0 = automatisch
    stt_beam_size: int = 5
    stt_model_dir: Path | None = None  # Ablage der heruntergeladenen Modelle (Default: data_dir/models)
    # Im Einsatzbetrieb True: nie versuchen, Modelle aus dem Internet zu laden.
    stt_local_files_only: bool = False
    stt_max_audio_seconds: int = 90
    stt_max_upload_bytes: int = 10 * 1024 * 1024
    # Nur für die Testphase: Aufnahmen + Transkript speichern, um Benchmark-Daten zu sammeln.
    stt_keep_audio: bool = False

    # Einsatzablage: alle Nachrichten mit Aufnahmen und Fotos menschenlesbar, ein Ordner pro Einsatz.
    # Wird beim Serverstart festgelegt (Default: data_dir/ablage).
    ablage_dir: Path | None = None
    max_fotos: int = 5
    max_foto_bytes: int = 8 * 1024 * 1024

    # Vom Startfenster gesetzt: welcher Einsatz läuft. Leer in Entwicklung und Tests.
    einsatz_kennung: str = ""
    einsatz_bezeichnung: str = ""
    # Nach einem gelöschten Einsatzordner: lesbare Einträge aus der Datenbank neu schreiben.
    ablage_neu_aufbauen: bool = False

    @property
    def lokal_dir(self) -> Path:
        """Lokale Daten des Einsatzes. Die Datenbank darf nie auf die NAS: SQLite im WAL-Modus braucht ein lokales Laufwerk."""
        return self.data_dir / "einsaetze" / self.einsatz_kennung if self.einsatz_kennung else self.data_dir

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.lokal_dir / 'meldi.db'}"

    @property
    def vorlaeufig_dir(self) -> Path:
        """Lokal, damit nie abgesendete Aufnahmen nicht auf die NAS (und dort in einen Papierkorb) geraten."""
        return self.lokal_dir / "vorlaeufig"

    @property
    def models_dir(self) -> Path:
        return self.stt_model_dir or self.data_dir / "models"

    @property
    def ablage_root(self) -> Path:
        return self.ablage_dir or self.data_dir / "ablage"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"


@lru_cache
def get_settings() -> Settings:
    return Settings()
