"""Startfenster für den ELW-Rechner: fragt Ordner und Einsatznamen ab und hält den Server am Laufen.

Bewusst ohne FastAPI und Datenbankmodelle, damit das Fenster sofort erscheint und ein Fehler im Server es
nicht mitreißt. Der Server läuft als Kindprozess.
"""


def main() -> None:
    # tkinter erst hier laden: ordner.py und prozesse.py sollen ohne Oberfläche nutzbar und testbar bleiben.
    from app.starter.fenster import starte

    starte()
