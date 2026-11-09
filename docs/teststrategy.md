# Teststrategie

Stand: 08.11.2026 · Umgesetzt bis auf den Lauf unter Windows · Roadmap: [ROADMAP.md](../ROADMAP.md) · Funde: [review-findings.md](review-findings.md)

Ziel: Erweiterungen schnell und verlässlich gegen Regressionen prüfen, von der Fachlogik bis zur Bedienung im echten
Browser, einschließlich Edge Cases.

## Ausgangslage

| Ebene | Umfang | Laufzeit (gemessen unter Linux) |
|---|---|---|
| Backend (pytest) | 245 Tests, 2 echte Whisper-Tests standardmäßig übersprungen | rund 15 s |
| Frontend-Logik (Vitest) | 75 Tests | rund 1 s |
| UI (Playwright, Chromium) | 90 Tests | rund 70 s |
| WebKit-Smoke | 1 Test, in der CI Pflicht, lokal übersprungen, wenn WebKit nicht startet | rund 2 s |

`tools/regression.py voll` dauert insgesamt rund 95 s. **Windows:** läuft über [GitHub Actions](#github-actions), der erste
Lauf steht noch aus.

## Testebenen

Drei Ebenen, die ein gemeinsamer Befehl startet: `tools/regression.py <stufe>`. Das Skript nutzt nur die
Python-Standardbibliothek und läuft damit unter Linux und Windows.

| Stufe | Inhalt | Zielzeit | Wann |
|---|---|---|---|
| `schnell` | pytest, Vitest, `vue-tsc` | < 30 s | bei jeder Änderung, optional als pre-push |
| `voll` | zusätzlich Frontend-Build und UI-Tests | < 5 min | vor jedem Merge |
| `whisper` | zusätzlich echtes Modell (`-m slow`) | Minuten | bei STT- oder Prompt-Änderungen |

`uv run pytest` bleibt durch `-m "not ui"` schnell. Ist die Gruppe `ui` nicht installiert, wird `tests/ui/` gar nicht erst
eingesammelt.

## UI-Tests

Ablage: `backend/tests/ui/`, Marker `ui`, Werkzeug: Playwright für Python.

**Warum Python statt Node:** Der Server läuft im selben Prozess wie der Test. Der vorhandene Fixture `db_url` liefert
so jedem Test eine eigene Datenbank und Ablage, der Test steuert `FakeSTT` direkt und prüft Datenbank, Audit und
Ablage-Dateien unmittelbar. Test-Endpunkte in der App sind dadurch nicht nötig. Nachteil: Playwright für Python hat
keinen Screenshot-Vergleich, der zwischen Linux und Windows ohnehin unzuverlässig wäre.

### Aufbau

- **Server:** echter uvicorn auf freiem Port mit gebautem Frontend, über `create_app(stt=...)`. Er lässt sich im Test
  stoppen und auf demselben Port neu starten. Ist `frontend/dist` älter als `frontend/src`, bricht der Lauf mit klarer
  Meldung ab.
- **`FakeSTT` erweitern:** Antwortliste, Fehler, leeres Ergebnis und ein Halten-Signal für den Zustand „Erkenne …“.
- **Mikrofon:** Chromium mit Fake-Gerät und synthetischer WAV-Datei, also echter `MediaRecorder` und echter Upload.
  Echte Aufnahmen aus `data/` werden in UI-Tests nie verwendet.
- **Stabilität:** Warten nur über Playwright-Bedingungen, kein `sleep`, keine automatischen Wiederholungen, damit
  unzuverlässige Tests auffallen. `pytest-timeout` begrenzt hängende Tests.
- **Fehlersuche:** Bei Fehlschlag werden Trace und Screenshot in `test-results/` gespeichert (gitignored).

### Browser-Profile

| Profil | Abdeckung |
|---|---|
| Chromium Desktop (unter Windows optional Edge) | ELW, voller Umfang |
| Chromium mit Pixel-Emulation | Melder und Beobachter, voller Umfang |
| WebKit mit iPhone-Emulation | Smoke ohne Mikrofon, ersetzt kein echtes iPhone |

### Wächter in jedem UI-Test

Ein automatischer Fixture sichert die Datenschutz- und Bedienregeln aus `CLAUDE.md` ab:

- Einzige Ausnahme von der CSP-Prüfung: Mit aktivem Tracing holt sich Playwright selbst Blob-Bilder per `fetch`. Nur dann
  ist genau dieser Fall erlaubt.
- Der Test schlägt fehl bei Requests an fremde Hosts, CSP-Verletzungen, unerwarteten Konsolenfehlern oder einem Aufruf
  von `SpeechRecognition`. Erwartete Fehler, etwa der 401 vor der Anmeldung, stehen in einer Ausnahmeliste.
- Nach dem Test müssen localStorage, sessionStorage, IndexedDB, Cache Storage und Service Worker leer sein.
- Auf Handygröße gelten: keine horizontale Scrollleiste, Touch-Ziele ≥ 44 px, Eingabefelder ≥ 16 px.

### Katalog (rund 70 Fälle)

**Anmeldung und Rollen**

- Die drei Kacheln führen zur richtigen Ansicht. Reload hält die Anmeldung. Zurück-Taste nach dem Abmelden.
- Name nur aus Leerzeichen, Umlaute, sehr lange Namen, frei getippte Funktion, kein aktiver Einsatz.
- Rollenwechsel im selben Browser beendet die alte Anmeldung. Der Beobachter landet auf `/melder/` beim Login.

**Melden per Text**

- Absenden erst bei gültigen Feldern, Enter-Taste, Doppelklick ergibt genau eine Nachricht.
- Bestätigung mit Nummer, Formular wird geleert, Empfänger-Chip erscheint, die eigene Funktion nicht.
- Netzfehler und NAS-Fehler: Text bleibt stehen, erneutes Senden klappt.
- Antwort geht verloren, der Server hat aber gespeichert: Erneutes Senden erzeugt keine Dublette (`sende_id`).
- HTML oder Script als Inhalt wird nur als Text angezeigt. Emoji, Zeilenumbrüche, Maximallänge.
- Sitzung läuft beim Tippen ab ([F7](review-findings.md#f7-abgelaufene-sitzung-wird-im-melder-uneinheitlich-behandelt)).

**Sprache**

- Ablauf Aufnahme → „Erkenne …“ → Text, Empfänger mit hoher Übereinstimmung, „Meinten Sie“ bei niedriger.
- Inhalt in Etappen: Text wird angehängt, alle Aufnahmen landen in der Ablage. „Inhalt leeren“ verwirft die Aufnahmen.
- Nichts erkannt, STT-Ausfall (Tippen geht weiter), Mikrofon verweigert oder nicht vorhanden, Auto-Stopp bei Stille.
- Beide Mikrofon-Knöpfe gleichzeitig, Absenden während Aufnahme oder Erkennung
  ([F5](review-findings.md#f5-absenden-während-der-erkennung-verliert-das-ergebnis)).
- Abmelden während der Aufnahme gibt das Mikrofon frei.

**Fotos**

- GPS kommt an, Verkleinerung auf 2560 px, Hochkant-Fotos, Limit von 5.
- Kaputte Datei ([F6](review-findings.md#f6-unlesbares-foto-sperrt-das-absenden-ohne-hinweis-am-knopf)), Upload-Fehler
  mit „erneut“, Entfernen während des Uploads, Absenden gesperrt, solange ein Foto lädt.

**ELW**

- Nachricht erscheint ohne Reload, Zähler „neu“ und Tab-Titel, Lesen setzt den Zähler zurück.
- Status live in zweitem ELW und beim Beobachter, Protokoll mit Name, Status-Fehler wird angezeigt.
- Auswahl bleibt bei Live-Updates, Textmarkieren wechselt die Nachricht nicht, Audio und Foto laden trotz CSP.
- Filter-Kombinationen, neue Nachricht bei aktivem Filter, kein Treffer, Zurücksetzen.
- 500 Nachrichten, sehr langer Inhalt, mehrere Melder gleichzeitig.
- Server-Neustart: „getrennt“ → „live“, verpasste Nachrichten sind da und als neu markiert.
- Abgelaufene Sitzung ([F2](review-findings.md#f2-abgelaufene-sitzung-führt-im-elw-nicht-zum-login)).

**Beobachter**

- Keine Status- und Erfassen-Funktion, Live-Updates, Filter, Scrollposition bleibt bei neuen Nachrichten erhalten.

## Frontend-Logik mit Vitest

Fälle, die im Browser langsam oder unzuverlässig wären:

- Filtergrenzen, etwa „bis 14:30“ schließt 14:30:59 ein, Groß- und Kleinschreibung, Umlaute.
- Schwellen 80/50/40 bei den Empfänger-Vorschlägen.
- `useRecorder` mit Fake-`MediaRecorder`: Stille-Stopp, Maximaldauer, Abbruch, Unmount, MIME-Auswahl für iOS, unsicherer
  Kontext.
- `useLiveFeed`: Reconnect-Backoff mit Fake-Timern.

## Backend-Ergänzungen

- **Rechtematrix:** wird aus `app.routes` erzeugt, Endpunkt × 4 Rollen (ohne Anmeldung, Melder, ELW, Beobachter). Ein
  neuer Endpunkt ohne Eintrag lässt den Test scheitern.
- **Bisher ungetestet:** Zugriff über Einsatzgrenzen hinweg, abgelaufene Sitzung, parallele `lfd_nr` und `sende_id`,
  offener WebSocket nach Abmeldung ([F1](review-findings.md#f1-live-kanal-bleibt-nach-abmeldung-offen)).
- **`test_regeln.py`:** CSP exakt festschreiben, keine externen URLs in `frontend/dist`, Importverbot für `stt`, kein
  `SpeechRecognition` im Quellcode.
- **Migrationen:** Prüfung auf Abweichung zwischen Modellen und Alembic.

## Nötige Source-Änderungen

- Etwa 10 `data-testid` an Stellen ohne Rolle oder Label: Tabellenzeile, Status, Verbindung, Foto-Kachel. Alles andere
  wird über Rolle und Label angesprochen.
- `passt` aus `frontend/src/shared/useEingang.ts` exportieren.
- Testkonfiguration in `vite.config.ts`, `package.json`, `pyproject.toml` und `.gitignore`.
- Erweiterter `FakeSTT` in `backend/tests/conftest.py`.

Korrekturen aus den [Review-Findings](review-findings.md) sind davon getrennt.

## Zusatztools

Alle sind reine Entwicklungsabhängigkeiten. Sie werden nicht mit Meldi ausgeliefert und schränken die Lizenz
(AGPL-3.0) nicht ein. Lizenzen geprüft am 08.11.2026 in den Registern von npm und PyPI.

| Tool | Lizenz |
|---|---|
| `playwright`, `pytest-playwright` | Apache-2.0 |
| `pytest-cov`, `pytest-timeout` | MIT |
| `vitest`, `@vitest/coverage-v8`, `@vue/test-utils`, `happy-dom` | MIT |

Playwright kommt in eine eigene uv-Gruppe `ui`: Das normale `uv sync` installiert die Gruppe `dev` mit und würde es
sonst auf den ELW-Rechner bringen. Vitest 5.1 passt zu Vite 6.4 und Node 22. Playwright bietet Chromium und WebKit für
Ubuntu 26.04 an. Die Browser selbst lädt Playwright einmalig aus dem Internet, das betrifft nur Entwicklungsrechner.

`pytest-xdist` wurde wieder entfernt: Bei rund 70 s für die UI-Tests lohnt paralleles Ausführen nicht.

## Umsetzung

1. ✅ **Durchstich:** ein Test Melder → Sprache → ELW live, inklusive Wächter und Runner.
2. ✅ **Backend-Lücken:** Rechtematrix, `test_regeln.py`, Nebenläufigkeit.
3. ✅ **Vitest:** Einrichtung und Logiktests.
4. ✅ **UI-Katalog:** Hauptabläufe und Edge Cases.
5. 🔶 **Abschluss:** Neue Regel in `CLAUDE.md` ✅, Workflow für Ubuntu und Windows ✅. Der erste Windows-Lauf steht noch aus.

## Bleibt manuell

- Echte Handys (Android, iPhone), besonders Mikrofon, Kamera und Bildschirm-aus
- Caddy, Zertifikate und HTTPS im Fahrzeugnetz
- Startfenster, Kindprozesse und Job-Objekt unter Windows
- NAS-Pfade (UNC und verbundenes Laufwerk)
- Erkennungsqualität über `tools/stt_bench`

## GitHub Actions

`.github/workflows/tests.yml` führt die Stufe `voll` bei jedem Push auf Ubuntu und Windows aus, die Stufe `whisper` nie:
Die Tests nutzen `FakeSTT` und synthetische Daten, `HF_HUB_OFFLINE` lässt jeden Modell-Download scheitern. Mit Blick auf
das öffentliche Repository hat der Workflow nur Leserechte, keine Secrets und auf Commits gepinnte Actions. Bei einem
Fehlschlag liegen Traces und Screenshots 7 Tage als Artefakt bereit.
