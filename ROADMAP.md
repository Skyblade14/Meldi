# Roadmap

Stand: 08.11.2026 (Phase 5 geplant) · Architektur: [docs/architecture.md](docs/architecture.md)

Legende: ✅ erledigt · 🔶 begonnen bzw. ungetestet · ⬜ offen

---

## Phase 1 – Architektur und Sprach-PoC ✅

Ziel: tragfähige Struktur und die Antwort auf die Frage *„Funktioniert lokale Spracherkennung auf einem Office-PC?“*

- ✅ Projektstruktur Backend (FastAPI, SQLite, Alembic) und Frontend (Vue 3, zwei Ansichten)
- ✅ Datenmodell: Einsatz, Funktion, User, Anmeldung, Nachricht, append-only Audit
- ✅ Anmeldung mit Name, PIN und Funktion. Session-Cookie, Sperre nach Fehlversuchen
- ✅ Melder-Formular: Von (automatisch), An, Inhalt, Priorität. Jedes Feld per Mikrofon einsprechbar
- ✅ Lokale Spracherkennung (faster-whisper) mit feldspezifischem Vokabular, Halluzinationsfilter und
  Empfänger-Zuordnung
- ✅ ELW-Ansicht: Live-Eingang per WebSocket, Detailansicht, Rohtext der Erkennung, Protokoll
- ✅ Benchmark-Werkzeug mit synthetischen Testaufnahmen. Ergebnis: **Idee trägt**
  ([Messergebnisse](docs/spracherkennung-messung.md))
- ✅ Browser-Durchstich mit simuliertem Mikrofon
- 🔶 Deployment: Caddyfile, Windows-Dienste und Startskripte geschrieben, **noch nicht auf Windows bzw. mit
  echten Handys über HTTPS getestet**

---

## Phase 2 – Praxistest Spracherkennung ⬜

Ziel: Die Messwerte von synthetischen Stimmen durch echte ersetzen und Modell und Vokabular final festlegen.
**Sollte vor dem großen Ausbau passieren**, weil die Ergebnisse die Bedienung beeinflussen.

- ⬜ Auf dem echten ELW-Rechner installieren (Startfenster, Caddy) und `stt_bench` dort laufen lassen
- 🔶 Test mit echten Handys über HTTPS mit lokaler CA: erstes Android-Handy ✅ (`deploy/start-lan-test.sh`), iPhone/Safari offen
- ⬜ Echte Aufnahmen von 5–10 Kameraden sammeln: drinnen, draußen, neben laufender Pumpe, mit Handschuhen
  und Helm
- 🔶 Audio-Verarbeitung des Browsers: schadet in ruhiger Umgebung deutlich (Telefonie-Bandbreite), daher jetzt aus.
  Offen: Gegenprobe neben laufender Pumpe (`?audio=verarbeitet`)
- ⬜ Vokabular-Prompt anhand echter Meldungen erweitern und gegenmessen
- ⬜ Schwelle für die automatische Empfänger-Übernahme (derzeit 80 %) anhand der Daten prüfen
- ✅ Entscheidung Modell: `large-v3-turbo`. Mindestanforderung: 8 CPU-Threads
- ✅ Benchmark mit echten Aufnahmen aus der App (`tools/stt_bench/import_app.py`)
- ⬜ Übungseinsatz mit Meldi parallel zum Papiervordruck und Rückmeldung der Melder einholen

---

## Phase 3 – Melder-Formular und lückenlose Dokumentation 🔶

Ziel: Formular verschlanken, Fotos ermöglichen und jede Meldung vollständig nachvollziehbar ablegen.
Kann parallel zu Phase 2 laufen.

- ⬜ Repo bereinigen: nur behalten, was gebraucht wird (alte Experimente, ungenutzte Skripte und Doku entfernen).
  Zurückgestellt. Backend und Skripte am 08.11.2026 geprüft: bis auf `backend/alembic/README` nichts Überflüssiges,
  Frontend noch nicht geprüft
- ✅ Priorität entfernen: Feld im Formular, API, Datenmodell (Alembic-Migration) und Doku
  (`docs/architecture.md`)
- ✅ Empfänger-Vorschläge kürzen: nur Empfänger anzeigen, an die in dieser Anmeldung schon gesendet wurde
- 🔶 Foto-Funktion: bis zu 5 Fotos pro Nachricht, auf dem Handy auf 2560 px verkleinert, GPS und Aufnahmezeit
  bleiben erhalten (falls das Handy sie mitliefert). Im Desktop-Browser getestet, **auf echten Handys
  (Android/iPhone) noch nicht**. Offen: Landen Kamerafotos auf den Handys wirklich nicht in der Galerie? Liefern
  die Handys GPS mit? Falls nicht: Standort optional über den Browser abfragen
- 🔶 Einsatzablage: Alle Daten des Melders (Nachrichten, Audio, Fotos, Erkennungs-Rohtext) an einem Ort,
  menschenlesbar (z.B. ein Ordner pro Einsatz mit JSON/Text und den Originaldateien). Ablageort wird beim
  Serverstart festgelegt (die PCs werden nach jedem Einsatz heruntergefahren). Aufnahmen, die nie abgesendet
  werden, werden gelöscht. Ziel: lückenlose Dokumentation. **Ersetzt die Regel „Audio wird nicht gespeichert“** in
  `CLAUDE.md`, Datenschutz-Abstimmung siehe Phase 6. Umgesetzt (`MELDI_ABLAGE_DIR`, Default `data/ablage`), mit
  Wiederholung bei Dateisperren und Prüfung beim Serverstart. **Unter Windows noch nicht getestet**

---

## Phase 4 – ELW-Ansicht und Beobachter 🔶

Ziel: Das ELW sieht, sichtet und überträgt die Nachrichten. Die Hauptanwendung im ELW ist **EDP Web**, Meldi
liefert zu. Bewusst schlanker als der Vierfachvordruck (kein Weiterleiten, keine Rückmeldung an den Melder).

- ✅ Status per Klick: neu → gesichtet → erledigt, live für alle, im Protokoll mit Name (ersetzt den Sichtvermerk)
- ✅ Filtern und Suchen: nach Status, Absender, Empfänger, Zeitraum, Freitext (im Browser, live)
- 🔶 Markieren und Kopieren für EDP Web: jedes Feld per Maus markierbar (Strg+C) ✅, Fotos per Rechtsklick →
  „Bild kopieren“ (am ELW-Rechner mit Edge und EDP Web prüfen)
- ✅ ELW-Ansicht für den Desktop
- 🔶 Beobachter-Ansicht für das Handy (`/beobachter/`, Rolle `beobachter`): alle Nachrichten live lesen, filtern,
  suchen. Kein Status, kein Erfassen. Im simulierten Handy getestet (Live-Status, Filter, Suche, Scrollposition).
  Echtes Handy offen, vor allem: Ist die Liste nach Bildschirm-aus oder App-Wechsel wieder aktuell?
- ✅ ELW erfasst selbst (Funk, Telefon) über die Melder-Ansicht: Link „Nachricht erfassen“

---

## Phase 5 – Start im ELW und Zugang ohne PIN 🔶

Ziel: Im Einsatz keine Kommandozeile mehr. Der Server wird im ELW über ein kleines Startfenster gestartet und läuft,
solange es offen ist. Im ersten Schritt zählt die Dokumentation, wer was geschrieben hat: keine Passwörter, keine
Benutzerverwaltung.

- ✅ Anmeldung ohne PIN: Name und Funktion, die Rolle ergibt sich aus der gewählten Ansicht und gehört zur
  `Anmeldung` statt zum `User` (Migration). Beobachter geben nur den Namen ein. PIN-Prüfung, Sperre, argon2 und
  `meldi user` entfallen
- ✅ Startseite unter `/` mit drei Kacheln: ELW, Melder, Beobachter
- ✅ Einsatz öffnen: Ein Ordner auf der NAS ist ein Einsatz (Audio, Fotos, lesbare Einträge) und trägt eine
  Kennung des Einsatzes. Die Datenbank liegt lokal im globalen Datenordner, eine Datei pro Einsatz, nie auf der NAS
  (SQLite im WAL-Modus). Der Serverstart legt den Einsatz nur an, wenn es ihn noch nicht gibt
- 🔶 Ablage direkt auf der NAS (steht neben dem Rechner, per Kabel), bewusst ohne Puffer: Fällt sie aus, schlägt das
  Absenden fehl, und im Einsatz wird ein neuer Einsatz auf dem Rechner geöffnet. Vorläufige Uploads bleiben lokal,
  damit nie abgesendete Aufnahmen gar nicht erst auf die NAS kommen
- 🔶 Startfenster (CustomTkinter): fragt Datenpfad (auch `\\nas\…` oder verbundenes Laufwerk) und Einsatznamen ab. Bei einem
  Ordner mit vorhandenem Einsatz zeigt es Name, Beginn und Nachrichtenzahl und bietet „Einsatz fortsetzen“ an. Server
  und Caddy laufen als Kindprozesse, Whisper-Modelle bleiben am festen Ort. Doppeltes Öffnen und Standby werden
  verhindert
- 🔶 Fenster schließen nur mit Bestätigung. Das stoppt Server und Caddy, beendet aber nicht den Einsatz (`ende`
  bleibt leer)
- ✅ Übersicht über die aktiven Anmeldungen in der ELW-Ansicht: Name, Rolle, Funktion, seit wann (nur Anzeige, nur
  Rolle ELW). Ohne PIN sieht das ELW nur so, wer gerade drin ist
- 🔶 Gelöschter Einsatzordner, Warnung: Das Startfenster prüft im laufenden Betrieb regelmäßig die Kennungsdatei und
  zeigt rot an, wenn der Ordner weg ist
- 🔶 Gelöschter Einsatzordner, Wiederherstellung (nach dem Startfenster): Das Startfenster zeigt die bekannten Einsätze
  aus den lokalen Datenbanken und bietet bei fehlendem Ordner „In neuem Ordner fortsetzen“ an. `nachricht.txt`,
  `nachricht.json`, `protokoll.jsonl` und `einsatz.json` werden aus der Datenbank neu geschrieben, die Nummerierung
  läuft weiter. Fehlende Audios und Fotos werden vermerkt, der Neuaufbau wird protokolliert
- ✅ Deployment und Doku: Dienst `meldi-api` entfällt, `start-dev.ps1`, `betrieb.md`, `architecture.md` und
  `CLAUDE.md` anpassen. NAS-Einrichtung in `betrieb.md`: Schreiben und Löschen nur für das Konto des ELW-Rechners,
  Snapshots oder Papierkorb für den Freigabeordner (nur das rettet gelöschte Audios und Fotos)
- ⬜ Test auf dem Windows-Rechner: CustomTkinter im uv-Python (Aussehen, Skalierung, Hell/Dunkel), Kindprozesse und Job-Objekt, Absturz, Herunterfahren, Standby,
  NAS-Pfade (UNC und verbundenes Laufwerk), Adresse bei zwei Netzwerkkarten. Offen auch: Oberflächen im Browser anklicken

**Bedingung vor dem ersten echten Einsatz:** Zugriff klären. Ohne PIN kann jedes Gerät im WLAN oder VPN die
ELW-Ansicht öffnen und alle Nachrichten, Aufnahmen und Fotos lesen. Für Tests und Übungen ohne echte Daten ist das
in Ordnung.

Zurückgestellt:

- ⬜ Funktionen des Einsatzes bearbeiten: hinzufügen, umbenennen, Aliase pflegen (die Aliase verbessern die
  Erkennung). Kein Löschen, alte Nachrichten behalten den alten Namen
- ⬜ Benutzerverwaltung (anlegen, PIN zurücksetzen, deaktivieren): abhängig davon, wie der Zugriff geregelt wird

---

## Teststrategie – Regressionstests 🔶

Ziel: Erweiterungen schnell und verlässlich absichern, von der Fachlogik bis zur Bedienung im echten Browser,
einschließlich Edge Cases. Details: [docs/teststrategy.md](docs/teststrategy.md) · Funde aus der Planung:
[docs/review-findings.md](docs/review-findings.md)

- ✅ Durchstich: ein UI-Test Melder → Sprache → ELW live, mit Wächtern und Runner `tools/regression.py`
- ✅ Backend-Lücken schließen: Rechtematrix, `test_regeln.py`, Nebenläufigkeit
- ✅ Frontend-Logik mit Vitest testen
- ✅ UI-Katalog mit Playwright umsetzen: Hauptabläufe und Edge Cases (91 Fälle, Lauf rund 70 s)
- ✅ Neue Testregel in `CLAUDE.md`, WebKit-Smoke-Test läuft
- 🔶 GitHub Actions für Ubuntu und Windows ohne Whisper (`.github/workflows/tests.yml`). **Erster Lauf unter Windows offen**
- ✅ Review-Findings F1–F7 behoben, jeweils mit Test. Auf einem echten iPhone offen: Live-Kanal unter der neuen CSP (F4)

---

## Phase 6 – Betriebsreife ⬜

- ⬜ HTTPS ohne Zertifikatsinstallation: Subdomain + Let's Encrypt per DNS-Challenge, Caddy-Build mit DNS-Modul
- ⬜ Netzwerk festlegen: ELW-WLAN und/oder VPN, mit Anleitung für die Handys (QR-Code). Bevorzugt
  **Tailscale**, sofern die Lizenz die Nutzung durch die Feuerwehr erlaubt (Nutzungsbedingungen prüfen).
  Sonst WireGuard direkt oder Headscale (selbstgehosteter Koordinationsserver)
- ⬜ Mit Tailscale prüfen: HTTPS-Zertifikate über `tailscale cert` statt eigener Domain
- ⬜ Einfache Installation: Installationsskript bzw. Paket für Windows, Update-Prozess
- ⬜ Export pro Einsatz: PDF im Layout des Vierfachvordrucks, Einsatztagebuch, CSV
- ⬜ „Einsatz abschließen“ zusammen mit dem Export (setzt `ende`)
- ⬜ Archivierung und Löschfristen (inkl. Einsatzablage aus Phase 3): abgeschlossene Einsätze exportieren und danach löschen bzw. anonymisieren
- ⬜ Datensicherung (automatische Kopie der Datenbank)
- ⬜ Datenschutz-Dokumentation mit der/dem Datenschutzbeauftragten: Verzeichnis von Verarbeitungstätigkeiten,
  TOMs, ggf. DSFA. Speicherung von Audio und Fotos auf der NAS sowie das Mitlesen auf Privathandys (Beobachter) ausdrücklich
  aufnehmen
- ⬜ Statusseite bzw. Health-Check für die Technik im ELW (Modell geladen, Warteschlange, Speicherplatz)

---

## Phase 7 – Repository veröffentlichen ✅

Ziel: Das GitHub-Repository öffentlich schalten, ohne Geheimnisse oder personenbezogene Daten preiszugeben und mit
klaren Nutzungsrechten. Unabhängig von den anderen Phasen.

- ✅ Prüfung der Git-Historie am 08.11.2026: keine Schlüssel oder Passwörter, keine Datenbanken, Aufnahmen, Fotos oder
  Zertifikate. Die PINs in der Historie sind nur Testdaten
- ✅ Prüfung der Abhängigkeiten am 08.11.2026: kein Lizenzverstoß. `piper-tts` (GPL-3.0) wird nur vom Benchmark
  importiert und nicht mitgeliefert. `customtkinter` steht unter MIT (Lizenzdatei im Paket), das Lizenzfeld auf PyPI
  nennt fälschlich CC0
- ✅ Lizenz am 09.11.2026 festgelegt: AGPL-3.0, damit Verbesserungen offen bleiben (`LICENSE`)
- ✅ `docs/tester-anleitung.md` am 09.11.2026 bereinigt: Platzhalter statt echter Adresse des Testrechners, keine
  PIN-Schritte mehr
- ✅ `.gitignore` am 09.11.2026 ergänzt: persönliche Notizen, `*.pem`, `*.key`, `*.crt`, Aufnahmen, Fotos. Von `.claude/`
  bleiben nur `skills/` und `agents/` versionierbar
- ✅ Leak-Schutz am 09.11.2026: pre-commit mit gitleaks und `tools/leak_check.py`, dieselben Prüfungen in GitHub Actions
- ✅ Autor-E-Mail am 08.11.2026: Historie zu einem Commit zusammengefasst, Autor ist die GitHub-Noreply-Adresse. Künftige
  Commits nutzen sie über die Git-Konfiguration dieses Repositorys (auf einem neuen Rechner erneut setzen)
- ✅ Vor dem Umschalten am 09.11.2026: gitleaks 8.30.1 über die gesamte Historie ohne Befund. Das GitHub-Repository wurde
  neu angelegt, weil ein alter Commit mit privater E-Mail-Adresse über seinen Hash erreichbar blieb. Es startete mit
  einem einzigen Commit, ohne Issues, Actions-Logs und Wiki
- ✅ Sichtbarkeit am 09.11.2026 auf öffentlich umgestellt, Secret Scanning und Push Protection eingeschaltet
- ✅ Dependabot am 09.11.2026: Warnungen und Sicherheitsupdates aktiv, Routine-Updates gebündelt und monatlich
  (`.github/dependabot.yml`), Merge nur von Hand

**Zu beachten:** Der öffentliche Code zeigt, dass es seit Phase 5 keine Zugangsprüfung gibt. Testserver daher nur im
VPN oder ELW-WLAN betreiben (siehe Bedingung in Phase 5). Die PyAV-Pakete für Linux enthalten GPL-Bibliotheken (x264,
x265). Das betrifft nicht das Repository, muss aber beim Installationspaket aus Phase 6 geprüft werden, auch für die
Windows-Pakete.

---

## Phase 8 – Deployment im ELW ⬜

Ziel: Meldi läuft auf dem echten ELW-Rechner mit NAS, Netz und Handys und ist einsatzbereit. Die Schritte stehen in
[docs/betrieb.md](docs/betrieb.md). Baut auf dem Windows-Test aus Phase 5 und den Festlegungen zu Netzwerk, HTTPS und
Installation aus Phase 6 auf.

- ⬜ ELW-Rechner prüfen: mindestens 8 CPU-Threads, genug Speicherplatz, Standby im Einsatz ausgeschlossen
- ⬜ Meldi installieren: Frontend bauen, `uv sync`, Modell laden (einmalig Internet nötig), `caddy.exe` nach
  `deploy\bin\`, Verknüpfung auf `meldi-start` auf dem Desktop
- ⬜ Datenordner festlegen: Die Datenbanken liegen unter `MELDI_DATA_DIR` (Default `<repo>\data`, hängt also vom
  Installationsort ab). Das Startfenster fragt ihn nicht ab und zeigt ihn nicht an. Lokales, von BitLocker erfasstes
  Laufwerk wählen, nie die NAS. Entscheiden, ob das Startfenster den Pfad anzeigen oder wählbar machen soll
- ⬜ Rechner absichern: BitLocker, Windows-Firewall eingehend TCP 443 und 80 nur für das private Netz
- ⬜ NAS einrichten: Freigabe mit Schreiben und Löschen nur für das Konto des ELW-Rechners, Snapshots oder Papierkorb,
  Verschlüsselung, Laufwerk unter demselben Konto wie `meldi-start` verbinden
- ⬜ Netz und HTTPS im Fahrzeug einrichten (eigenes WLAN-Passwort, kein Gastzugang) und mit Android und iPhone prüfen
- ⬜ Offline-Probe: Rechner ohne Internet starten, Modell lädt, Sprachaufnahme, Foto und Absenden funktionieren
- ⬜ Update-Ablauf festlegen und einmal durchspielen: Datenbanken sichern, neue Version einspielen, Migrationen beim
  Start prüfen, Rückweg zur alten Version
- ⬜ Kurzanleitung für das ELW-Personal: Starten, Beenden, Vorgehen bei NAS-Ausfall und gelöschtem Einsatzordner
- ⬜ Generalprobe in einer Übung mit dem kompletten Aufbau. Testaufnahmen löschen, `MELDI_STT_KEEP_AUDIO` ist aus

**Voraussetzung für echte Einsätze:** Zugriff geklärt (Phase 5) und Datenschutz-Dokumentation abgestimmt (Phase 6).

---

## Ideen und spätere Optionen

| Idee | Anmerkung |
|---|---|
| Gesamtdiktat, aus dem die Felder automatisch erkannt werden | Mit kleinem lokalem LLM. Auf der CPU langsam, Nutzen erst nach Phase 2 bewerten |
| Fine-Tuning von Whisper auf eigene Aufnahmen | Lohnt sich, wenn Fachbegriffe bzw. Dialekt in Phase 2 schwach bleiben |
| Live-Transkription während des Sprechens (Streaming) | Komfort. Erhöht Komplexität und CPU-Last |
| Offline-Puffer auf dem Handy bei Funkloch | Steht im Konflikt zum Datenschutz (Daten auf Privatgeräten). Nur verschlüsselt und kurzlebig, Abwägung nötig |
| Installierbare PWA (Homescreen-Icon) | Ohne Offline-Cache für Daten |
| Lagekarte / Abschnittsübersicht | Eigenes Thema, nicht Kern der Melder-Software |
| Mehrere ELW bzw. Abschnittsleitungen synchronisieren | Erst bei Bedarf |
| Schnittstelle zu Einsatzleitsoftware | Abhängig vom eingesetzten System |
| Anbindung an EDP Web | Nachrichten direkt übertragen statt kopieren, ggf. über eine REST-API von EDP Web. Planen, wenn die Schnittstelle bekannt ist |
| Nachricht im ELW korrigieren | Erkennungsfehler berichtigen, Original bleibt im Protokoll. Derzeit nicht nötig, korrigiert wird in EDP Web |
| Rückmeldung an den Melder | „im ELW gelesen“ bzw. „erledigt“. Alternative: Der Melder schickt seine Telefonnummer mit, damit das ELW ihn erreicht |
| Akustische und optische Signale | Bei neuen Nachrichten, konfigurierbar (z.B. nur für bestimmte Empfänger) |

---

## Offene Entscheidungen

- **Netzwerk:** ELW-WLAN, VPN oder beides? Welcher Router bzw. Mobilfunktarif ist im ELW verbaut?
- **Tailscale-Lizenz:** Ist der kostenlose Plan für die Feuerwehr zulässig, oder braucht es einen bezahlten Plan
  bzw. Headscale? Der Koordinationsserver sieht Metadaten (Geräte, IPs), aber keine Inhalte.
- **Domain:** Gibt es eine Feuerwehr-Domain, deren DNS per API verwaltbar ist (für Let's Encrypt)?
- **Hardware:** Welcher Rechner genau? Danach richtet sich die Modellwahl.
- **Zugriff:** Wie wird der Zugang geschützt, sobald echte Daten verarbeitet werden? Feste Benutzerliste mit PIN,
  oder Anmeldung per Einsatz-Code, den das ELW ausgibt? (siehe Bedingung in Phase 5)
- **Aufbewahrung:** Wie lange werden Einsatznachrichten, Audio und Fotos gespeichert? Wer darf exportieren?
