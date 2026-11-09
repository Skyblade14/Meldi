"""Das Startfenster. Nur Anzeige: Fachliches liegt in ordner.py, Prozesse in prozesse.py.

Alles, was auf der NAS oder am Netz hängen kann, läuft in Hintergrund-Threads. Tk selbst wird nur im Hauptthread
angefasst, Ergebnisse kommen über eine Queue zurück.
"""

import logging
import queue
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from app.config import Settings
from app.starter import farben, prozesse
from app.starter import ordner as ordner_modul
from app.starter.ordner import Analyse, EinsatzInfo, Startauftrag

log = logging.getLogger("meldi.starter")

_TAKT_MS = 2000
_KENNUNG_TAKT_MS = 5000
_KEIN_ORDNER = "Bitte einen Ordner wählen."
_FELD_HOEHE = 40
_TEXTBREITE = 680
_GROESSE_START = "780x580"
_GROESSE_BETRIEB = "780x480"


class Fenster:
    def __init__(self, root: ctk.CTk, data_dir: Path) -> None:
        self.root = root
        self.data_dir = data_dir
        self.dienste: prozesse.Dienste | None = None
        self.auftrag: Startauftrag | None = None
        self.analyse: Analyse | None = None
        self.umzug: EinsatzInfo | None = None
        self.bekannte: dict[str, EinsatzInfo] = {}
        self._generation = 0  # Ergebnisse älterer Ordnerprüfungen verwerfen
        self._startet = False
        self._wird_beendet = False
        self._health: dict | None = None
        self._health_laeuft = False
        self._kennung_laeuft = False
        self._titel_schrift = ctk.CTkFont(size=22, weight="bold")
        self._feld_schrift = ctk.CTkFont(weight="bold")

        root.title("Meldi")
        root.minsize(680, 460)
        root.protocol("WM_DELETE_WINDOW", self.schliessen)
        root.report_callback_exception = self._unerwartet
        farben.liste_faerben(root, ctk.get_appearance_mode())
        ctk.AppearanceModeTracker.add(lambda modus: farben.liste_faerben(root, modus), root)
        karte = ctk.CTkFrame(root, border_width=1)
        karte.pack(fill="both", expand=True, padx=16, pady=16)
        self.rahmen = ctk.CTkFrame(karte, fg_color="transparent", border_width=0)
        self.rahmen.pack(fill="both", expand=True, padx=20, pady=20)
        self.zeige_start()

    def _unerwartet(self, typ, wert, spur) -> None:
        log.error("Fehler im Startfenster", exc_info=(typ, wert, spur))
        messagebox.showerror("Meldi", f"Unerwarteter Fehler: {wert}", parent=self.root)

    def _im_hintergrund(
        self, arbeit: Callable[[], object], fertig: Callable[[object], None], fehler: Callable[[Exception], None]
    ) -> None:
        ergebnisse: queue.SimpleQueue = queue.SimpleQueue()

        def lauf() -> None:
            try:
                ergebnisse.put((True, arbeit()))
            except Exception as exc:
                log.exception("Hintergrundarbeit fehlgeschlagen")
                ergebnisse.put((False, exc))

        def abholen() -> None:
            try:
                ok, wert = ergebnisse.get_nowait()
            except queue.Empty:
                self.root.after(50, abholen)
                return
            (fertig if ok else fehler)(wert)

        threading.Thread(target=lauf, daemon=True).start()
        self.root.after(50, abholen)

    def _leeren(self) -> None:
        for kind in self.rahmen.winfo_children():
            kind.destroy()

    def _feld_titel(self, eltern: ctk.CTkFrame, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(eltern, text=text, font=self._feld_schrift)

    def _knopf(self, eltern: ctk.CTkFrame, text: str, befehl: Callable[[], None]) -> ctk.CTkButton:
        return ctk.CTkButton(eltern, text=text, command=befehl, height=_FELD_HOEHE)

    # --- Vor dem Start --------------------------------------------------------------------------------------

    def zeige_start(self) -> None:
        self._leeren()
        self.root.geometry(_GROESSE_START)
        rahmen = self.rahmen
        rahmen.columnconfigure(1, weight=1)
        ctk.CTkLabel(rahmen, text="Meldi starten", font=self._titel_schrift).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12)
        )

        self._feld_titel(rahmen, "Bekannte Einsätze").grid(row=1, column=0, columnspan=3, sticky="w")
        spalten = {"einsatz": "Einsatz", "beginn": "Beginn", "nachrichten": "Nachr.", "ordner": "Ordner"}
        self.liste = ttk.Treeview(rahmen, columns=tuple(spalten), show="headings", height=5, selectmode="browse")
        for schluessel, titel in spalten.items():
            self.liste.heading(schluessel, text=titel, anchor="w")
        # Aus der Schrift berechnet: Feste Pixel schneiden bei hoher Bildschirmskalierung ab.
        schrift = farben.listen_schrift(self.root)
        self.liste.column("nachrichten", width=schrift.measure("Nachr.") + 24, stretch=False)
        self.liste.column("beginn", width=schrift.measure("00.00.0000 00:00") + 24, stretch=False)
        self.liste.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=(2, 4))
        self.liste.bind("<<TreeviewSelect>>", lambda _: self._einsatz_gewaehlt())
        self._knopf(rahmen, "Auswahl aufheben", self._auswahl_aufheben).grid(
            row=3, column=2, sticky="e", pady=(0, 12)
        )

        self.ordner_var = tk.StringVar()
        self._feld_titel(rahmen, "Datenpfad").grid(row=4, column=0, sticky="w", padx=(0, 12))
        eingabe = ctk.CTkEntry(rahmen, textvariable=self.ordner_var, height=_FELD_HOEHE)
        eingabe.grid(row=4, column=1, sticky="ew")
        eingabe.bind("<FocusOut>", lambda _: self._pruefe_ordner())
        eingabe.bind("<Return>", lambda _: self._pruefe_ordner())
        self._knopf(rahmen, "Wählen…", self._ordner_waehlen).grid(row=4, column=2, padx=(8, 0))

        self.name_var = tk.StringVar()
        self._feld_titel(rahmen, "Einsatzname").grid(row=5, column=0, sticky="w", padx=(0, 12), pady=(8, 0))
        self.name_eingabe = ctk.CTkEntry(rahmen, textvariable=self.name_var, height=_FELD_HOEHE)
        self.name_eingabe.grid(row=5, column=1, columnspan=2, sticky="ew", pady=(8, 0))

        self.hinweis_var = tk.StringVar(value=_KEIN_ORDNER)
        ctk.CTkLabel(
            rahmen, textvariable=self.hinweis_var, wraplength=_TEXTBREITE, justify="left", text_color=farben.MUTED
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(12, 12))
        self.start_knopf = farben.HauptKnopf(
            rahmen, text="Einsatz starten", command=self._starten_klick, state="disabled"
        )
        self.start_knopf.grid(row=7, column=1, columnspan=2, sticky="e")
        self._im_hintergrund(
            lambda: ordner_modul.bekannte_einsaetze(self.data_dir), self._zeige_bekannte, lambda _: None
        )

    def _zeige_bekannte(self, einsaetze: object) -> None:
        self.bekannte = {e.kennung: e for e in einsaetze}  # type: ignore[attr-defined]
        for e in self.bekannte.values():
            beginn = f"{e.beginn.astimezone():%d.%m.%Y %H:%M}" if e.beginn else "–"
            ordner = "Ordner fehlt" if e.ordner_fehlt else str(e.ordner)
            self.liste.insert("", "end", iid=e.kennung, values=(e.bezeichnung, beginn, e.nachrichten, ordner))

    def _auswahl_aufheben(self) -> None:
        self.liste.selection_set(())
        self._setze_name(False, "" if self.umzug else None)
        self.umzug = None
        self._pruefe_ordner()

    def _einsatz_gewaehlt(self) -> None:
        auswahl = self.liste.selection()
        if not auswahl:
            return
        einsatz = self.bekannte[auswahl[0]]
        if einsatz.ordner_fehlt:
            self.umzug = einsatz
            self.ordner_var.set("")
            self._setze_name(True, einsatz.bezeichnung)
            self.start_knopf.configure(text="In neuem Ordner fortsetzen", state="disabled")
            self.hinweis_var.set("Der Ordner dieses Einsatzes fehlt. Bitte einen neuen Ordner wählen.")
            return
        self.umzug = None
        self.ordner_var.set(str(einsatz.ordner))
        self._pruefe_ordner()

    def _ordner_waehlen(self) -> None:
        gewaehlt = filedialog.askdirectory(parent=self.root, title="Datenpfad wählen", mustexist=False)
        if gewaehlt:
            self.ordner_var.set(gewaehlt)
            self._pruefe_ordner()

    def _setze_name(self, gesperrt: bool, bezeichnung: str | None = None) -> None:
        self.name_eingabe.configure(state="normal")
        if bezeichnung is not None:
            self.name_var.set(bezeichnung)
        elif gesperrt is False and self.analyse is not None and self.analyse.einsatz is not None:
            self.name_var.set("")  # Name des zuvor angezeigten Einsatzes nicht übernehmen
        self.name_eingabe.configure(
            state="disabled" if gesperrt else "normal", text_color=farben.MUTED if gesperrt else farben.TEXT
        )

    def _pruefe_ordner(self) -> None:
        text = self.ordner_var.get().strip()
        self._generation += 1
        if not text:
            self.analyse = None
            if self.umzug is None:
                self.hinweis_var.set(_KEIN_ORDNER)
                self.start_knopf.configure(text="Einsatz starten", state="disabled")
            return
        generation = self._generation
        pfad = Path(text)

        def fertig(analyse: object) -> None:
            if generation == self._generation:
                self._zeige_analyse(analyse)  # type: ignore[arg-type]

        self._im_hintergrund(
            lambda: ordner_modul.analysiere(self.data_dir, pfad), fertig, lambda exc: self.hinweis_var.set(str(exc))
        )

    def _zeige_analyse(self, analyse: Analyse) -> ordner_modul.Vorschlag:
        vorschlag = ordner_modul.vorschlag(analyse, self.umzug)
        self._setze_name(vorschlag.name_gesperrt, vorschlag.bezeichnung)
        self.analyse = analyse
        self.hinweis_var.set(vorschlag.hinweis)
        self.start_knopf.configure(text=vorschlag.knopf, state="normal" if vorschlag.erlaubt else "disabled")
        return vorschlag

    def _start_abbrechen(self) -> None:
        self._startet = False
        self.start_knopf.configure(state="normal")

    def _start_fehler(self, exc: Exception) -> None:
        self.dienste = None
        self._start_abbrechen()
        messagebox.showerror("Meldi", str(exc), parent=self.root)

    def _starten_klick(self) -> None:
        text = self.ordner_var.get().strip()
        if not text:
            messagebox.showwarning("Meldi", _KEIN_ORDNER, parent=self.root)
            return
        self._startet = True
        self.start_knopf.configure(state="disabled")
        self._generation += 1
        pfad = Path(text)
        # Frisch prüfen: Das Feld kann seit der Anzeige getippt worden sein, der Ordner sich geändert haben.
        self._im_hintergrund(
            lambda: ordner_modul.analysiere(self.data_dir, pfad), self._nach_analyse, self._start_fehler
        )

    def _nach_analyse(self, ergebnis: object) -> None:
        analyse: Analyse = ergebnis  # type: ignore[assignment]
        vorschlag = self._zeige_analyse(analyse)
        if not vorschlag.erlaubt:
            self._startet = False
            return
        if vorschlag.rueckfrage and not messagebox.askyesno("Meldi", vorschlag.rueckfrage, parent=self.root):
            self._start_abbrechen()
            return
        umzug, bezeichnung = self.umzug, self.name_var.get()

        def arbeit() -> tuple[Startauftrag, prozesse.Dienste]:
            auftrag = ordner_modul.vorbereiten(self.data_dir, analyse, umzug, bezeichnung)
            dienste = prozesse.dienste_fuer(self.data_dir, auftrag)
            dienste.starten()
            return auftrag, dienste

        self._im_hintergrund(arbeit, self._gestartet, self._start_fehler)

    def _gestartet(self, ergebnis: object) -> None:
        self.auftrag, self.dienste = ergebnis  # type: ignore[misc]
        self._startet = False
        prozesse.standby_verhindern()  # Hauptthread: Der Zustand gilt nur für den aufrufenden Thread
        self.zeige_betrieb()

    # --- Laufender Betrieb ----------------------------------------------------------------------------------

    def zeige_betrieb(self) -> None:
        assert self.auftrag is not None and self.dienste is not None
        self._leeren()
        self.root.geometry(_GROESSE_BETRIEB)
        rahmen = self.rahmen
        rahmen.columnconfigure(1, weight=1)
        ctk.CTkLabel(rahmen, text=self.auftrag.bezeichnung, font=self._titel_schrift).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12)
        )
        self.server_var, self.stt_var, self.caddy_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        # Am Objekt halten: Tk hält keine Referenz, eine eingesammelte StringVar leert ihr Feld.
        self.adresse_var = tk.StringVar(value=self.dienste.adresse)
        self.datenpfad_var = tk.StringVar(value=str(self.auftrag.ordner))
        zeilen: list[tuple[str, tk.StringVar]] = [
            ("Adresse", self.adresse_var), ("Datenpfad", self.datenpfad_var), ("Server", self.server_var),
            ("Spracherkennung", self.stt_var), ("HTTPS (Caddy)", self.caddy_var),
        ]
        for i, (titel, variable) in enumerate(zeilen, start=1):
            self._feld_titel(rahmen, titel).grid(row=i, column=0, sticky="w", padx=(0, 12), pady=4)
            # Schreibgeschützte Felder, damit Adresse und Pfad markiert und kopiert werden können.
            feld = ctk.CTkEntry(rahmen, textvariable=variable, state="readonly", height=_FELD_HOEHE)
            feld.grid(row=i, column=1, columnspan=1 if variable is self.adresse_var else 2, sticky="ew", pady=4)
        farben.HauptKnopf(rahmen, text="Im Browser öffnen", command=self._browser_oeffnen, width=170).grid(
            row=1, column=2, padx=(8, 0), pady=4
        )

        self.warnung = ctk.CTkLabel(
            rahmen, text="", text_color=farben.DANGER, font=self._feld_schrift, wraplength=_TEXTBREITE, justify="left"
        )
        self.warnung.grid(row=6, column=0, columnspan=3, sticky="w", pady=(12, 12))
        knoepfe = ctk.CTkFrame(rahmen, fg_color="transparent", border_width=0)
        knoepfe.grid(row=7, column=0, columnspan=3, sticky="e")
        self.neu_knopf = self._knopf(knoepfe, "Neu starten", self._neu_starten)
        self.beenden_knopf = self._knopf(knoepfe, "Server beenden", self.schliessen)
        self.beenden_knopf.pack(side="right")
        self._ordner_fehlt = False
        self._takt()
        self._kennung_takt()

    def _browser_oeffnen(self) -> None:
        assert self.dienste is not None
        if not webbrowser.open(self.dienste.adresse):
            messagebox.showerror("Meldi", "Der Browser konnte nicht geöffnet werden.", parent=self.root)

    def _takt(self) -> None:
        if self._wird_beendet or self.dienste is None:
            return
        self._hole_health()
        self._aktualisiere()
        self.root.after(_TAKT_MS, self._takt)

    def _hole_health(self) -> None:
        if self._health_laeuft or self.dienste is None or not self.dienste.server.laeuft:
            return
        self._health_laeuft = True

        def fertig(wert: object) -> None:
            self._health_laeuft = False
            self._health = wert  # type: ignore[assignment]

        def fehler(_: Exception) -> None:
            self._health_laeuft = False
            self._health = None

        self._im_hintergrund(prozesse.health, fertig, fehler)

    def _aktualisiere(self) -> None:
        dienste = self.dienste
        assert dienste is not None
        if self.adresse_var.get() != dienste.adresse:  # nur bei Änderung, sonst stört es beim Markieren
            self.adresse_var.set(dienste.adresse)
        server = dienste.server
        if server.laeuft:
            self.server_var.set("läuft" if self._health else "startet…")
        else:
            self._health = None
            self.server_var.set(f"abgestürzt (Code {server.exitcode}), Log: {server.logdatei}")
        if self._health is None:
            self.stt_var.set("–" if not server.laeuft else "wartet auf Server…")
        else:
            self.stt_var.set("bereit" if self._health.get("stt_bereit") else "Modell lädt…")
        if dienste.caddy_fehler:
            self.caddy_var.set(f"{dienste.caddy_fehler}: Handys erreichen den Server nicht")
        elif dienste.caddy is not None and not dienste.caddy.laeuft:
            self.caddy_var.set(f"abgestürzt (Code {dienste.caddy.exitcode}), Log: {dienste.caddy.logdatei}")
        else:
            self.caddy_var.set("läuft")

        warnungen = []
        if self._ordner_fehlt:
            warnungen.append("Einsatzordner fehlt oder ist nicht erreichbar! Neue Nachrichten sind gefährdet.")
        if dienste.abgestuerzt:
            warnungen.append("Ein Dienst ist abgestürzt.")
        self.warnung.configure(text="\n".join(warnungen))
        if dienste.abgestuerzt:
            self.neu_knopf.pack(side="right", padx=(0, 8))
        else:
            self.neu_knopf.pack_forget()

    def _kennung_takt(self) -> None:
        if self._wird_beendet or self.auftrag is None:
            return
        self.root.after(_KENNUNG_TAKT_MS, self._kennung_takt)
        if self._kennung_laeuft:  # hängende NAS: keine Threads aufstauen
            return
        self._kennung_laeuft = True
        auftrag = self.auftrag

        def fertig(vorhanden: object) -> None:
            self._kennung_laeuft = False
            self._ordner_fehlt = not vorhanden
            self._aktualisiere()

        def fehler(_: Exception) -> None:
            self._kennung_laeuft = False
            self._ordner_fehlt = True

        self._im_hintergrund(lambda: ordner_modul.kennung_vorhanden(auftrag.ordner, auftrag.kennung), fertig, fehler)

    def _neu_starten(self) -> None:
        assert self.dienste is not None
        self.neu_knopf.configure(state="disabled")

        def fertig(_: object) -> None:
            self.neu_knopf.configure(state="normal")
            self._aktualisiere()

        def fehler(exc: Exception) -> None:
            self.neu_knopf.configure(state="normal")
            messagebox.showerror("Meldi", f"Neustart fehlgeschlagen: {exc}", parent=self.root)

        self._im_hintergrund(self.dienste.neu_starten, fertig, fehler)

    def schliessen(self) -> None:
        if self._startet or self._wird_beendet:
            return
        if self.dienste is None:
            self.root.destroy()
            return
        if not messagebox.askyesno(
            "Server beenden?",
            "Server wirklich beenden?\n\nDie Handys verlieren die Verbindung. Der Einsatz bleibt offen und kann "
            "später mit demselben Datenpfad fortgesetzt werden.",
            icon="warning",
            default="no",
            parent=self.root,
        ):
            return
        self._wird_beendet = True
        self.beenden_knopf.configure(state="disabled", text="Wird beendet…")
        self.neu_knopf.pack_forget()
        self._im_hintergrund(self.dienste.stoppen, lambda _: self._beendet(), lambda _: self._beendet())

    def _beendet(self) -> None:
        prozesse.standby_erlauben()
        self.root.destroy()


def starte() -> None:
    data_dir = Settings().data_dir
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    # Unter pythonw.exe gibt es keine Konsole, Fehler wären sonst unsichtbar.
    logging.basicConfig(
        filename=data_dir / "logs" / "starter.log",
        encoding="utf-8",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    farben.anwenden()
    root = ctk.CTk()
    sperre = prozesse.StarterSperre(data_dir)
    if not sperre.erwerben():
        root.withdraw()
        messagebox.showerror("Meldi", "Meldi läuft auf diesem Rechner bereits.", parent=root)
        root.destroy()
        return
    try:
        Fenster(root, data_dir)
        root.mainloop()
    finally:
        sperre.freigeben()
