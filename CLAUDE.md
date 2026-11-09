# CLAUDE.md

Meldi ist eine Melder-Software für die Feuerwehr. Sie ersetzt den Vierfachvordruck. Melder erfassen Nachrichten
per Sprache auf dem Smartphone, das ELW-Personal sieht sie live. Alles läuft selbstgehostet auf einem
Windows-Office-PC im Einsatzleitwagen.

Architektur: `docs/architecture.md` · Betrieb: `docs/betrieb.md` · Roadmap: `ROADMAP.md`

## Unverhandelbare Regeln (Datenschutz)

Die Daten sind sensibel und dürfen **nur auf dem ELW-Rechner und der NAS daneben** ankommen. Daraus folgt:

- **Keine externen Requests** aus App oder Frontend: keine CDNs, Google Fonts, Analytics oder externen APIs.
  Alle Assets werden gebündelt. Die CSP `default-src 'self'` in `backend/app/main.py` nicht aufweichen.
- **Niemals die Web Speech API** (`SpeechRecognition`) verwenden. Sie schickt Audio an Google bzw. Apple.
  Spracherkennung läuft ausschließlich serverseitig in `backend/app/stt/`.
- **Keine sensiblen Daten auf dem Handy:** keine Nachrichten in localStorage, IndexedDB oder Service-Worker-Caches.
  API-Antworten bleiben `Cache-Control: no-store`.
- Audio und Fotos werden **nur in der Einsatzablage** gespeichert (`services/ablage.py`, `MELDI_ABLAGE_DIR`, im
  Betrieb ein Ordner auf der NAS). Vorläufige Uploads bleiben lokal. Nie abgesendete Uploads werden gelöscht
  (nach dem Absenden, beim Abmelden, spätestens beim Serverstart). `MELDI_STT_KEEP_AUDIO` ist nur für die Testphase.
- **Rechte serverseitig prüfen** (`api/deps.py`: `CurrentAnmeldung`, `ElwAnmeldung`, `LeseAnmeldung` für ELW und
  Beobachter, `MeldeAnmeldung` für Melder und ELW), nie nur im Frontend. Seit Phase 5 gibt es keine PIN: Die Rolle wählt man
  selbst, die Prüfung schützt nur vor Fehlbedienung. Vor dem ersten echten Einsatz muss der Zugriff geklärt sein.
- **Nachvollziehbarkeit:** `audit_event` ist append-only. Jede Änderung an einer Nachricht erzeugt einen
  Audit-Eintrag mit alt/neu. Maßgeblicher Zeitstempel ist die Serverzeit (`eingang_at`).

## Befehle

```bash
# Alle Regressionstests (aus dem Projektordner, unter Linux und Windows)
python tools/regression.py schnell                     # pytest, Vitest, vue-tsc (~20 s)
python tools/regression.py voll                        # zusätzlich Build und UI-Tests im Browser (~2 min), vor jedem Merge
python tools/regression.py whisper                     # zusätzlich echtes Modell, bei STT- oder Prompt-Änderungen, nur lokal

# Leak-Schutz (pre-commit und gitleaks müssen installiert sein)
pre-commit install                                     # einmalig pro Klon
pre-commit run --all-files                             # alle Prüfungen von Hand

# Backend (aus backend/)
uv sync --all-groups                                   # Abhängigkeiten inkl. dev + bench
uv run pytest                                          # schnelle Tests (FakeSTT, ~5 s)
MELDI_TEST_WHISPER=1 uv run pytest -m slow             # mit echtem Whisper-Modell
uv run --group ui playwright install chromium webkit   # einmalig für die UI-Tests
uv run --group ui pytest -m ui                         # UI-Tests, braucht ein aktuelles frontend/dist
uv run meldi demo                                      # Übungseinsatz anlegen
MELDI_COOKIE_SECURE=false uv run uvicorn --factory app.main:create_app --port 8000
uv run alembic revision --autogenerate --rev-id 0002 -m "beschreibung"   # neue Migration

# Frontend (aus frontend/)
npm run build                                          # vue-tsc + vite → frontend/dist (vom Backend ausgeliefert)
npm test                                               # Vitest (Logik ohne Browser), mit Coverage: npm run test:cov
npm run dev                                            # Hot-Reload auf :5173, leitet /api an :8000 weiter

# Spracherkennung messen (aus backend/)
uv run python ../tools/stt_bench/synth.py              # synthetische Testaufnahmen (lokal, Piper)
uv run python ../tools/stt_bench/import_app.py <sprecher>   # App-Aufnahmen (data/audio) als echtes Testmaterial
uv run python ../tools/stt_bench/run.py --threads 8 [--audio ../tools/stt_bench/audio/real] [--feld an|inhalt]
```

## Struktur

- `backend/app/api/`: HTTP und WebSocket, nur Ein-/Ausgabe und Rechteprüfung
- `backend/app/services/`: Fachlogik und Transaktionen
- `backend/app/starter/`: Startfenster (`meldi-start`, CustomTkinter, Farben in `farben.py` passend zu `shared/style.css`). Kennt weder FastAPI noch die Datenbankmodelle.
- `backend/app/stt/`: Spracherkennung. Kennt weder FastAPI noch die Datenbank. Wird auch von `tools/stt_bench` importiert.
- `backend/app/models/`: SQLAlchemy-Modelle. `backend/app/schemas/`: Pydantic-Modelle der API.
- `frontend/src/start/` (Startseite mit drei Kacheln), `frontend/src/melder/` (Handy), `frontend/src/elw/` (ELW, Desktop), `frontend/src/beobachter/` (Handy, nur lesen),
  `frontend/src/shared/` (API, `useRecorder`, `RecordButton`, `useEingang`, `useSitzung`, `NachrichtDetail`)
- `backend/tests/ui/`: UI-Tests mit Playwright. `backend/tests/test_rechte.py`: Rechtematrix. `backend/tests/test_regeln.py`: die Regeln von oben, maschinell geprüft

Abhängigkeitsrichtung: `api → services → models`, `api → stt`. `stt` darf nichts aus `api`, `services` oder
`models` importieren.

## Konventionen

- **Fachbegriffe auf Deutsch**, wie im Feuerwehralltag: `Einsatz`, `Funktion`, `Anmeldung`, `Nachricht`,
  `lfd_nr`, `eingang_at`, `eingabe`. Technische Begriffe auf Englisch (`create_app`, `transcribe`, `deps`).
  Bestehende Benennung fortführen und nicht mischen.
- UI-Texte, Fehlermeldungen (`HTTPException`-Details), Kommentare und Docstrings auf Deutsch.
  Kommentare erklären das *Warum*, sparsam.
- Enums als `StrEnum` und in der DB per `str_enum()` (`app/db.py`). So werden Werte wie `"melder"` gespeichert, keine Namen.
- Zeitpunkte immer zeitzonenbehaftet: `utcnow()` aus `app/db.py`, Spalten vom Typ `UTCDateTime`, Eingaben als
  `AwareDatetime`.
- Schema-Änderungen nur per Alembic-Migration. Migrationen laufen beim App-Start automatisch.
- Neue Endpunkte bekommen Tests in `backend/tests/test_api.py`, mit den Fixtures `melder`, `melder2`, `elw`
  und `stt` (`FakeSTT`), und einen Eintrag in `MATRIX` in `backend/tests/test_rechte.py`.
- **Ein neuer Ablauf braucht einen UI-Test** in `backend/tests/ui/`. **Jeder Bugfix beginnt mit einem Test**, der den
  Fehler zeigt. Der Fixture `waechter` prüft in jedem UI-Test die Datenschutz- und Bedienregeln. Erwartete
  Konsolenfehler trägt der Test mit `waechter.erlaube(...)` ein. Warten nur über Playwright-Bedingungen, nie per `sleep`.
- Eine abgelaufene Sitzung (401) behandelt `api.ts` zentral (`beiAbgelaufenerSitzung`, gesetzt in `useSitzung`).
- Frontend: Vue 3 `<script setup lang="ts">`, kein UI-Framework, Farben nur über CSS-Variablen in
  `shared/style.css` (Dark Mode). Touch-Ziele mindestens ~44 px. Eingabefelder ≥ 16 px Schrift, sonst zoomt iOS.

## Stolperfallen

- **Leak-Schutz:** `tools/leak_check.py` lehnt Binärdateien, Zertifikate und öffentliche oder Tailscale-Adressen ab. Konkrete
  Namen oder Adressen gehören in die gitignorierte `.leak-begriffe.local`, nie in eine versionierte Datei. In Tests
  Adressen zur Laufzeit zusammensetzen oder private Bereiche verwenden. Treffer nur mit Datei und Zeile melden, denn
  die Actions-Logs sind öffentlich.
- **GitHub Actions** (`.github/workflows/tests.yml`) fährt `voll` auf Ubuntu und Windows, nie Whisper. Das Repository wird
  öffentlich: keine echten Aufnahmen oder Einsatzdaten in Tests, Actions auf Commits pinnen, keine Secrets im Workflow.
- **Audio-Dekodierung:** `faster_whisper.decode_audio` ist mit PyAV ≥ 15 kaputt (`metadata_errors`). Deshalb
  gibt es die eigene `decode_audio()` in `stt/whisper.py`. PyAV nicht auf < 15 pinnen, dafür gibt es keine
  Wheels für Python 3.12.
- **Whisper-Prompts:** Der Prompt für das Feld „An“ muss die **Aliase** der Funktionen enthalten. Sonst zieht
  er ähnlich klingende Wörter zum falschen Namen („Einsatzleitwagen“ → „Einsatzleitung“). Prompt-Änderungen
  immer mit `tools/stt_bench/run.py` gegenmessen. Keine Testsätze aus `samples.yaml` in den Prompt kopieren,
  das verfälscht die Messung.
- **Aufnahme roh lassen:** `echoCancellation`, `noiseSuppression` und `autoGainControl` sind bewusst aus
  (`AUFNAHME_PROFILE` in `useRecorder.ts`). Mit Echounterdrückung liefert Android Telefonie-Audio ohne
  Frequenzen über 4 kHz, und die Erkennung bricht ein (siehe `docs/spracherkennung-messung.md`).
- **`useRecorder.start()`** gibt `{ fertig }` zurück und kein Promise auf ein Promise, weil `await` beide
  auflösen würde.
- **CSP und WebSocket:** `connect-src` nennt den eigenen Host ausdrücklich (`content_security_policy()` in `main.py`),
  weil `'self'` in älteren Safari `wss:` nicht abdeckt. Nicht zurück auf `wss:` allein, das erlaubt jeden Host.
- **`audit_event` ist per Trigger gesperrt.** Eine Migration, die die Tabelle per `batch_alter_table` neu aufbaut, muss
  die Trigger wieder anlegen (`test_audit_ist_append_only` fällt sonst auf).
- Die App wird über eine **Factory** gestartet: `uvicorn --factory app.main:create_app`. Es gibt kein
  modulweites `app`.
- Tests setzen `MELDI_COOKIE_SECURE=false` und `MELDI_STT_ENABLED=false` (in `tests/conftest.py`). Jeder Test
  bekommt eine eigene SQLite-Datei.
- Ein Benchmark über alle synthetischen Aufnahmen dauert ~15 min. Mit `--feld`, `--gruppen` und `--audio`
  eingrenzen.
- `data/` (DB, Modelle, Testaufnahmen) und `tools/stt_bench/{audio,results,voices}/` sind gitignored und
  dürfen nie committet werden.
- Mikrofon im Browser nur über HTTPS oder `localhost`. Handys brauchen Caddy (`deploy/Caddyfile`). Zum schnellen
  Handytest unter Linux ohne Caddy: `MELDI_STT_KEEP_AUDIO=true ./deploy/start-lan-test.sh` (Port 8443, lokale CA in `data/tls/`).
- **Datenbank nie auf die NAS:** SQLite im WAL-Modus braucht ein lokales Laufwerk. Sie liegt unter
  `<MELDI_DATA_DIR>/einsaetze/<kennung>/`, eine Datei pro Einsatz. Auf der NAS liegt nur die Einsatzablage.

## Zielplattform

Windows-Office-PC ohne GPU, ohne Docker: Python 3.12 über `uv`, Start über das Startfenster (Server und Caddy als Kindprozesse), PowerShell 5.1 in
`deploy/*.ps1`. Also keine Features ab PowerShell 7 wie `?.` oder `??`. Code muss unter Windows laufen:
Pfade über `pathlib`, keine Unix-only-Abhängigkeiten.
