from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import BACKEND_DIR


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(BACKEND_DIR) / "alembic"))
    return cfg


def upgrade_database() -> None:
    command.upgrade(alembic_config(), "head")
