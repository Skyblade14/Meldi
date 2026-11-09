"""Verwaltung per Kommandozeile: `uv run meldi --help`."""

import argparse
import sys

from app.config import get_settings
from app.db import init_engine, new_session
from app.migrations import upgrade_database
from app.services.auth_service import aktiver_einsatz
from app.services.seed import neuer_einsatz


def cmd_einsatz(args: argparse.Namespace) -> None:
    with new_session() as db:
        e = neuer_einsatz(db, args.bezeichnung)
        print(f"Einsatz #{e.id} „{e.bezeichnung}“ angelegt ({len(e.funktionen)} Funktionen). Vorherige beendet.")


def cmd_demo(_: argparse.Namespace) -> None:
    with new_session() as db:
        if aktiver_einsatz(db) is None:
            neuer_einsatz(db, "Übung")
    print("Demo-Daten: Einsatz „Übung“.")


def cmd_download_model(args: argparse.Namespace) -> None:
    from faster_whisper import WhisperModel

    settings = get_settings()
    for model in args.models or [settings.stt_model]:
        print(f"Lade {model} nach {settings.models_dir} …")
        WhisperModel(model, device="cpu", compute_type="int8", download_root=str(settings.models_dir))
    print("Fertig. Für den Einsatzbetrieb MELDI_STT_LOCAL_FILES_ONLY=true setzen.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="meldi")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("einsatz-neu", help="Neuen Einsatz anlegen (beendet den aktuellen)")
    p.add_argument("bezeichnung")
    p.set_defaults(func=cmd_einsatz)

    p = sub.add_parser("demo", help="Übungseinsatz anlegen")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("download-model", help="Whisper-Modell(e) für den Offline-Betrieb herunterladen")
    p.add_argument("models", nargs="*", help="Standard: das konfigurierte Modell (MELDI_STT_MODEL)")
    p.set_defaults(func=cmd_download_model)

    args = parser.parse_args(argv)
    if args.func is not cmd_download_model:
        init_engine()
        upgrade_database()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
