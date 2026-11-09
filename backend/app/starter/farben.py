"""Aussehen des Startfensters, abgestimmt auf die Website (`frontend/src/shared/style.css`).

Jede Farbe ist ein Paar (hell, dunkel). Wie die Website folgt das Fenster der Systemeinstellung.
"""

import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

import customtkinter as ctk

Paar = tuple[str, str]

BG: Paar = ("#f4f4f5", "#0c0c0e")
SURFACE: Paar = ("#ffffff", "#18181b")
TEXT: Paar = ("#18181b", "#f4f4f5")
MUTED: Paar = ("#52525b", "#a1a1aa")
BORDER: Paar = ("#d4d4d8", "#3f3f46")
ACCENT: Paar = ("#b91c1c", "#ef4444")
ON_ACCENT: Paar = ("#ffffff", "#0c0c0e")
DANGER: Paar = ("#b91c1c", "#f87171")

# Die Website kennt keine Hover-Farbe für den Hauptknopf, CTkButton braucht eine.
ACCENT_HOVER: Paar = ("#991b1b", "#dc2626")
# Entspricht `.primary:disabled { opacity: 0.5 }` auf --surface.
ACCENT_GESPERRT: Paar = ("#dc8e8e", "#842e30")
ON_ACCENT_GESPERRT: Paar = ("#ffffff", "#121214")

RADIUS = 12
_LISTE_SCHRIFT_PT = 11


def anwenden() -> None:
    """Muss vor dem ersten Widget laufen: CustomTkinter liest das Thema beim Erzeugen."""
    ctk.set_appearance_mode("system")
    thema = ctk.ThemeManager.theme
    thema["CTk"]["fg_color"] = BG
    thema["CTkFrame"].update(fg_color=SURFACE, top_fg_color=SURFACE, border_color=BORDER, corner_radius=RADIUS)
    thema["CTkLabel"]["text_color"] = TEXT
    thema["CTkEntry"].update(
        fg_color=SURFACE, border_color=BORDER, text_color=TEXT, placeholder_text_color=MUTED,
        corner_radius=RADIUS, border_width=1,
    )
    thema["CTkButton"].update(
        fg_color=SURFACE, hover_color=BORDER, border_color=BORDER, text_color=TEXT, text_color_disabled=MUTED,
        corner_radius=RADIUS, border_width=1,
    )
    if sys.platform == "win32":
        thema["CTkFont"]["family"] = "Segoe UI"  # wie `system-ui` der Website unter Windows
    else:
        # Das Tk des uv-Pythons hat unter Linux kein Xft: Über eine Schrift gezeichnete Ecken zerfallen dort, und
        # Roboto oder Noto fielen auf die Bitmap-Schrift `fixed` zurück. Betrifft nur die Entwicklung.
        ctk.DrawEngine.preferred_drawing_method = "polygon_shapes"
        thema["CTkFont"]["family"] = "nimbus sans l"
    thema["CTkFont"]["size"] = 14


def listen_schrift(root: tk.Misc) -> tkfont.Font:
    return tkfont.Font(root=root, family=ctk.ThemeManager.theme["CTkFont"]["family"], size=_LISTE_SCHRIFT_PT)


def liste_faerben(root: tk.Misc, modus: str) -> None:
    """CustomTkinter hat keine Tabelle. `clam`, weil das Windows-Thema von ttk eigene Farben ignoriert."""
    index = 1 if modus == "Dark" else 0
    familie = ctk.ThemeManager.theme["CTkFont"]["family"]
    schrift = listen_schrift(root)
    stil = ttk.Style(root)
    stil.theme_use("clam")
    stil.configure(
        "Treeview",
        background=SURFACE[index], fieldbackground=SURFACE[index], foreground=TEXT[index],
        bordercolor=BORDER[index], lightcolor=SURFACE[index], darkcolor=SURFACE[index],
        # Aus der Schrift berechnet, damit die Zeilen auch bei hoher Bildschirmskalierung passen.
        font=(familie, _LISTE_SCHRIFT_PT), rowheight=schrift.metrics("linespace") + 10,
    )
    stil.map("Treeview", background=[("selected", ACCENT[index])], foreground=[("selected", ON_ACCENT[index])])
    stil.configure(
        "Treeview.Heading",
        background=BG[index], foreground=MUTED[index], bordercolor=BORDER[index],
        lightcolor=BG[index], darkcolor=BG[index], relief="flat", font=(familie, _LISTE_SCHRIFT_PT, "bold"),
    )
    stil.map("Treeview.Heading", background=[("active", BORDER[index])])


def _fuellung(zustand: str) -> Paar:
    return ACCENT if zustand == "normal" else ACCENT_GESPERRT


class HauptKnopf(ctk.CTkButton):
    """Wie `.primary` auf der Website. CTkButton kennt keine eigene Füllfarbe für den gesperrten Zustand."""

    def __init__(self, master: tk.Misc, **kwargs) -> None:
        super().__init__(
            master, height=48, border_width=0, fg_color=_fuellung(kwargs.get("state", "normal")),
            hover_color=ACCENT_HOVER, text_color=ON_ACCENT, text_color_disabled=ON_ACCENT_GESPERRT,
            font=ctk.CTkFont(size=15, weight="bold"), **kwargs,
        )

    def configure(self, require_redraw: bool = False, **kwargs) -> None:
        if "state" in kwargs:
            kwargs["fg_color"] = _fuellung(kwargs["state"])
        super().configure(require_redraw, **kwargs)
