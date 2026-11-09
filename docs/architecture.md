# Meldi – Architektur

Gliederung angelehnt an arc42. Verwandte Dokumente:
[Betrieb & Installation](betrieb.md) · [Messergebnisse Spracherkennung](spracherkennung-messung.md) · [Roadmap](../ROADMAP.md)

---

## 1. Ziel und Rahmenbedingungen

Meldi ersetzt den papiergebundenen **Vierfachvordruck** für Nachrichten zwischen Einsatzabschnitten und
Einsatzleitwagen (ELW). Melder erfassen Nachrichten auf dem Smartphone – vorrangig **per Sprache** –, das
ELW-Personal sieht sie sofort.

| Anforderung | Umsetzung |
|---|---|
| Nachvollziehbar: *wer → an wen → was → wann* | `Nachricht` mit Von/An/Inhalt, laufender Nummer pro Einsatz, Server-Zeitstempel, append-only Audit-Protokoll |
| Eingabe per Smartphone, vor allem per Sprache | Web-App (kein App-Store), Mikrofon-Taste pro Feld, Erkennung auf dem ELW-Rechner |
| Selbstgehostet auf Standard-Office-PC mit Windows | Python + SQLite, kein Docker, keine GPU nötig, Betrieb als Windows-Dienst |
| **Sensible Daten dürfen nur im ELW ankommen** | Keine Cloud-Dienste, keine CDNs, keine Browser-Spracherkennung, Offline-Betrieb |
| Melder nutzen **private Handys** | Nichts installieren außer ggf. Zertifikat/VPN; keine Daten auf dem Gerät speichern |

**Qualitätsziele (Priorität absteigend):**
1. **Datenschutz** – kein Datenabfluss außerhalb des ELW.
2. **Verlässlichkeit/Nachvollziehbarkeit** – keine Nachricht geht verloren, nichts wird spurlos verändert.
3. **Bedienbarkeit unter Einsatzbedingungen** – große Bedienelemente, Sprache statt Tippen, wenige Schritte.
4. **Einfacher Betrieb** – ein Rechner, wenige Komponenten, von Feuerwehr-IT wartbar.

---

## 2. Systemkontext

```
                 ┌────────────────────────── Einsatzstelle ──────────────────────────┐
                 │                                                                   │
  Melder ──▶ Smartphone (Browser) ──HTTPS──┐                                         │
  (privat)       │                         │   ELW-WLAN oder VPN                     │
                 │                         ▼                                         │
                 │          ┌──────────────────────────────┐                         │
  ELW-Personal ──┼─Browser─▶│  ELW-Rechner (Windows)       │                         │
  Beobachter ────┼─Handy───▶│                              │                         │
                 │          │  Meldi + Spracherkennung     │   ✗ kein Internet nötig │
                 │          └──────────────────────────────┘   ✗ keine Cloud         │
                 └───────────────────────────────────────────────────────────────────┘
```

Externe Verbindungen gibt es **nur zur Einrichtung**: Whisper-Modelle herunterladen (`meldi download-model`)
und ggf. Zertifikatserneuerung (Let's Encrypt). Im Einsatzbetrieb ist das System vollständig offline-fähig.

---

## 3. Bausteinsicht

### 3.1 Gesamtsystem

```
┌────────────────────────── ELW-Rechner ──────────────────────────┐
│                                                                 │
│  Caddy  :443  ── TLS, Reverse Proxy, HTTP→HTTPS                 │
│    │                                                            │
│    ▼                                                            │
│  uvicorn 127.0.0.1:8000                                         │
│  ┌───────────────────────── FastAPI (backend/app) ───────────┐  │
│  │  api/        HTTP + WebSocket, Rechteprüfung              │  │
│  │    │                                                      │  │
│  │    ▼                                                      │  │
│  │  services/   Fachlogik ───────────┐                       │  │
│  │    │                              │                       │  │
│  │    ▼                              ▼                       │  │
│  │  models/ ── SQLAlchemy ──▶ SQLite  stt/  faster-whisper   │  │
│  │              data/einsaetze/<kennung>/   (Worker-Thread)  │  │
│  │                                                           │  │
│  │  StaticFiles ─▶ frontend/dist (Vue-Build)                 │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Backend (`backend/app/`)

| Modul | Verantwortung | Wichtige Dateien |
|---|---|---|
| `api/` | Ein-/Ausgabe: Request-Validierung, Rechteprüfung, Umwandlung in Schemas. **Keine Fachlogik.** | `deps.py` (Session aus Cookie, Rollen: `ElwAnmeldung`, `LeseAnmeldung`, `MeldeAnmeldung`), `auth.py`, `messages.py`, `speech.py`, `uploads.py`, `ws.py` |
| `services/` | Fachlogik und Transaktionen | `auth_service.py` (Login, Sessions), `message_service.py` (lfd. Nr., Audit, Anhänge), `ablage.py` (Einsatzablage im Dateisystem), `foto.py` (Fotos prüfen, neu kodieren, GPS in EXIF), `notifier.py` (WebSocket-Verteilung), `seed.py` (Standard-Funktionen) |
| `stt/` | Spracherkennung hinter einer Schnittstelle, unabhängig von Web und Datenbank | `base.py` (`SpeechToText`-Protokoll, `Transcript`), `whisper.py` (Engine, Audio-Dekodierung), `vocabulary.py` (Prompts), `postprocess.py` (Filter, Empfänger-Zuordnung) |
| `models/` | Datenbankmodelle | `einsatz.py`, `user.py`, `message.py`, `anhang.py`, `audit.py` |
| `schemas/` | Pydantic-Modelle der API (Ein-/Ausgabe) | `auth.py`, `message.py`, `speech.py` |
| `starter/` | Startfenster (CustomTkinter): Einsatzordner wählen, Server und Caddy als Kindprozesse, Bestätigung beim Schließen. Kennt weder FastAPI noch die Datenbankmodelle | `ordner.py`, `prozesse.py`, `fenster.py`, `farben.py` |
| Querschnitt | Konfiguration, DB-Setup, App-Fabrik, CLI | `config.py`, `db.py`, `main.py` (`create_app`), `migrations.py`, `cli.py` |

**Abhängigkeitsregel:** `api → services → models`; `api → stt`. `stt/` kennt weder FastAPI noch die Datenbank,
`services/` kennt kein HTTP. Dadurch ist `stt/` auch vom Benchmark-Werkzeug (`tools/stt_bench`) direkt nutzbar
und in Tests durch eine Fake-Implementierung ersetzbar.

**App-Fabrik:** `create_app(settings, stt)` erlaubt, Konfiguration und Spracherkennung zu injizieren
(Tests nutzen `FakeSTT`). Start: `uvicorn --factory app.main:create_app`.

### 3.3 Frontend (`frontend/src/`)

Vue 3 + TypeScript, mit Vite gebaut. Getrennte Einstiegspunkte (`/` mit drei Kacheln, `/melder/`, `/elw/`, `/beobachter/`), damit das Melder-Bundle auf dem Handy klein bleibt.

| Ordner | Inhalt |
|---|---|
| `start/` | `App.vue` (Startseite mit den Kacheln Melder, ELW, Beobachter) |
| `melder/` | `App.vue` (Anmeldung/Abmeldung), `MessageForm.vue` (Formular, Empfänger-Vorschläge, gesendete Nachrichten) |
| `elw/` | Desktop. `App.vue` (Anmeldung), `Eingang.vue` (Tabelle mit Filter, Detail rechts, Status setzen, Link „Nachricht erfassen“ → `/melder/`), `Anmeldungen.vue` (wer gerade angemeldet ist) |
| `beobachter/` | Handy, nur lesen. `App.vue` (Anmeldung für Beobachter und ELW), `Lage.vue` (Kartenliste mit Filter, Detail im Vollbild, Zurück-Taste) |
| `shared/` | `useEingang.ts` (Nachrichtenliste live, Filter und Suche im Browser), `useLiveFeed.ts` (WebSocket mit Reconnect), `NachrichtDetail.vue` (Detail, Fotos, Aufnahmen, Protokoll, Status-Buttons), `FilterLeiste.vue`, `api.ts` (fetch-Client), `types.ts`, `useRecorder.ts` (MediaRecorder, Pegel, Stille-Stopp), `RecordButton.vue`, `LoginForm.vue`, `format.ts`, `style.css` (Farbvariablen, Dark Mode) |

Kein Router, kein State-Management-Framework – bewusst klein gehalten.

### 3.4 Werkzeuge

| Pfad | Zweck |
|---|---|
| `tools/stt_bench/` | Benchmark der Spracherkennung: synthetische Testaufnahmen (`synth.py`, lokale Piper-TTS) und Auswertung (`run.py`: Fehlerrate, Fachbegriffe, Empfänger-Zuordnung, Tempo) |
| `deploy/` | `Caddyfile`, Startskripte für die Entwicklung (`start-dev.ps1`, `start-dev.sh`) |

---

## 4. Laufzeitsicht

### 4.1 Anmeldung

```
Handy                         Backend                                   DB
  │ GET /api/auth/funktionen    │                                        │
  │────────────────────────────▶│ aktiver Einsatz → Funktionen           │
  │◀──── [Einsatzleitung, …] ───│                                        │
  │ POST /api/auth/login        │                                        │
  │ {name, rolle, funktion}     │ Person zum Namen suchen oder anlegen   │
  │────────────────────────────▶│ Anmeldung(user, einsatz, rolle,        │
  │                             │   funktion, sha256(token), 24 h) ─────▶│
  │◀── Set-Cookie meldi_session (HttpOnly, Secure, SameSite=Strict) ─────│
```

Es gibt keine Passwörter: Name und Rolle sind Angaben der Person und dokumentieren, wer was geschrieben hat. Die
Rolle ergibt sich aus der gewählten Ansicht. Eine neue Anmeldung im selben Browser beendet die bisherige.

Die **Funktion** („EA Brand“) und die **Rolle** gehören zur Anmeldung, nicht zum Benutzer – dieselbe Person kann im nächsten
Einsatz eine andere Funktion haben. Sie wird später automatisch zum „Von“ jeder Nachricht.

### 4.2 Spracheingabe für ein Feld

```
Handy                                   Backend                        STT-Worker (1 Thread)
  │ Tipp auf 🎤                            │                                    │
  │ getUserMedia + MediaRecorder           │                                    │
  │ … spricht … (Stopp: Tipp / 2,5 s       │                                    │
  │   Stille / 10 s bei „An“, 60 s Inhalt) │                                    │
  │ POST /api/speech/transcribe            │                                    │
  │ multipart: audio (webm|mp4), field ───▶│ Größe prüfen (≤ 10 MB)             │
  │                                        │ Prompt für Feld bauen:             │
  │                                        │  an: Funktionen + Aliase           │
  │                                        │  inhalt: Fachvokabular             │
  │                                        │ ── Audio + Prompt ────────────────▶│ PyAV → 16 kHz mono
  │                                        │                                    │ Whisper (de, VAD)
  │                                        │                                    │ Halluzinationen filtern
  │                                        │◀── Transcript (Text, Zeiten) ──────│ Abkürzungen korrigieren
  │                                        │ field=an: Fuzzy-Match auf Funktionen│
  │◀── {text, rohtext, vorschlaege,        │ Audio vorläufig ablegen            │
  │     aufnahme_id, …} ───────────────────│ (nur wenn Text erkannt)            │
  │ Feld befüllen (editierbar)             │                                    │
  │  an: Score ≥ 80 → übernehmen, sonst Vorschläge anzeigen                     │
  │  inhalt: an vorhandenen Text anhängen                                       │
```

Erkennungen laufen **nacheinander** in einem Worker-Thread: Auf der CPU bremsen sich parallele Läufe nur
gegenseitig aus. Wartende Anfragen liegen in der Queue des Thread-Pools. Die Antwort enthält Rechen- und
Wartezeit, das UI zeigt sie an.

### 4.3 Nachricht senden und Live-Verteilung

```
Handy (Melder)              Backend                                     ELW-Browser
  │ POST /api/messages        │                                            │ WS /api/ws/elw
  │ {an, inhalt, erfasst_at,  │ Sende-ID schon bekannt? → 200, fertig      │ (offen, Ping 20 s)
  │  eingabe, anhaenge,       │ Uploads in Bereitstellungsordner kopieren  │
  │  sende_id} ──────────────▶│ BEGIN                    (im Thread-Pool)  │
  │                           │  UPDATE einsatz SET naechste_lfd_nr+=1     │
  │                           │    RETURNING …          (atomar)           │
  │                           │  INSERT nachricht (eingang_at = jetzt)     │
  │                           │  INSERT anhang …, audit_event „erstellt“   │
  │                           │  Ordner → Einsatzablage, nachricht.txt/json│
  │                           │ COMMIT                                     │
  │                           │ übrige vorläufige Uploads löschen          │
  │                           │ notifier.broadcast(einsatz_id, …) ────────▶│ Zeile oben einfügen,
  │◀── 201 {lfd_nr, eingang_at}                                            │ als „neu“ markieren,
  │ „Nachricht Nr. 7 übermittelt“                                          │ Zähler im Tab-Titel
```

Bricht die WebSocket-Verbindung ab, verbindet sich das ELW mit exponentiellem Backoff neu und lädt die Liste
vollständig nach – verpasste Nachrichten gehen dadurch nicht verloren.

Setzt ein ELW-Platz den Status (`PUT /api/messages/{id}/status`), entsteht ein Audit-Eintrag
(`aktion = "status"`, alt/neu), die Einsatzablage wird aktualisiert, und alle ELW- und Beobachter-Bildschirme
bekommen `{"type": "nachricht.geaendert", "nachricht": …}`.

Filter und Suche laufen im Browser über die geladene Liste (ein Einsatz hat wenige hundert Nachrichten). So
fallen live eintreffende Nachrichten sofort in den Filter. Der Filterzustand liegt nur im Speicher.

---

## 5. Schnittstellen (HTTP-API)

Alle Endpunkte unter `/api`. OpenAPI-Dokumentation: `/api/docs`. Authentifizierung über das Session-Cookie.

| Methode & Pfad | Rolle | Zweck |
|---|---|---|
| `GET /auth/funktionen` | – | Funktionsnamen des aktiven Einsatzes (für Login, ohne Einsatzdetails) |
| `GET /health` | – | Für das Startfenster: `{ok, stt_bereit}`, nichts über den Einsatz |
| `POST /auth/login` | – | Anmeldung `{name, rolle, funktion}` → Cookie. Beobachter ohne Funktion |
| `GET /auth/anmeldungen` | elw | Aktive Anmeldungen des Einsatzes: Name, Rolle, Funktion, seit wann |
| `GET /auth/me` | alle | eigene Anmeldung (Name, Rolle, Funktion, Einsatz) |
| `POST /auth/logout` | alle | Session serverseitig beenden |
| `GET /speech/status` | alle | Modell, bereit, Länge der Warteschlange |
| `POST /speech/transcribe` | melder, elw | Audio + `field` (`an`/`inhalt`) → Text, Rohtext, Zeiten, Empfänger-Vorschläge |
| `POST /uploads/foto` | melder, elw | Foto (+ optional `gps_lat`, `gps_lon`, `aufgenommen_at`) vorläufig ablegen → `foto_id` |
| `POST /messages` | melder, elw | Nachricht anlegen (`201`), `anhaenge` = IDs vorläufig abgelegter Aufnahmen/Fotos. Bekannte `sende_id` → `200` mit der vorhandenen Nachricht |
| `GET /messages` | alle | ELW und Beobachter: alle des Einsatzes · Melder: nur eigene der aktuellen Anmeldung. `?nur_eigene=true`: für alle nur die eigenen (Melder-Ansicht) |
| `GET /messages/{id}` | elw, beobachter | Einzelne Nachricht |
| `GET /messages/{id}/audit` | elw, beobachter | Änderungsprotokoll, mit Name |
| `GET /messages/{id}/anhaenge/{anhang_id}` | elw, beobachter | Datei eines Anhangs aus der Einsatzablage |
| `PUT /messages/{id}/status` | elw | `{status}` = `neu` / `gesichtet` / `erledigt`. Mit Audit, gleicher Status ändert nichts |
| `WS /ws/elw` | elw, beobachter | Ereignisse `nachricht.neu` und `nachricht.geaendert`, jeweils `{"type": …, "nachricht": …}` |

Rollen: **melder** erfasst und sieht nur eigene Nachrichten. **elw** sieht alles, setzt den Status und erfasst
selbst über die Melder-Ansicht (Funk, Telefon). **beobachter** sieht alles (z.B. Einsatzleiter am Handy),
erfasst und ändert nichts.

Fehlercodes: `401` nicht angemeldet, `403` falsche Rolle, `400` kein lesbares Foto, mehr als 5 Fotos, `413` Aufnahme bzw. Foto zu groß,
`422` Validierung, `503` Spracherkennung nicht verfügbar (UI: „bitte tippen“).

---

## 6. Datenmodell

```
einsatz 1───* funktion
   │ 1
   ├───* anmeldung *───1 user
   │        │ 1
   └───* nachricht *───────┘ (von_user)
            │ 1      └──0..1 funktion (an_funktion)
            ├───* anhang
            └───* audit_event
```

| Tabelle | Wesentliche Felder | Hinweise |
|---|---|---|
| `einsatz` | `bezeichnung`, `beginn`, `ende`, `naechste_lfd_nr`, `ablage_ordner` | Im Betrieb eine Datenbank pro Einsatz. Genau ein Einsatz mit `ende = NULL` ist aktiv. `ablage_ordner` wird bei der ersten Nachricht festgelegt. |
| `funktion` | `einsatz_id`, `name`, `aliase`, `sortierung` | Je Einsatz. `aliase` = gesprochene Varianten („Einsatzleitwagen“ für „ELW“). Dient als Schnellauswahl, Empfänger-Zuordnung und STT-Vokabular. |
| `user` | `name` | Nur der selbst angegebene Name. Wird bei der ersten Anmeldung angelegt. |
| `anmeldung` | `user_id`, `einsatz_id`, `rolle` (`melder`/`elw`/`beobachter`), `funktion`, `token_hash`, `gueltig_bis`, `abgemeldet_at` | = Session. Token nur im Cookie, in der DB nur SHA-256. |
| `nachricht` | `lfd_nr`, `von_funktion`, `von_user_id`, `anmeldung_id`, `an`, `an_funktion_id`, `inhalt`, `status`, `erfasst_at`, `eingang_at`, `eingabe` (JSON), `sende_id`, `ablage_ordner` | `(einsatz_id, lfd_nr)` und `(anmeldung_id, sende_id)` eindeutig. `ablage_ordner` relativ zu `MELDI_ABLAGE_DIR`, gespeichert statt berechnet. `eingabe` hält je Feld Art (Sprache/Text), STT-Rohtext und Modell – Grundlage für die Auswertung der Erkennung im Echtbetrieb. |
| `anhang` | `nachricht_id`, `art` (`audio`/`foto`), `feld`, `dateiname`, `mime`, `groesse`, `sha256`, `hochgeladen_at`, `meta` (JSON) | Die Datei liegt in der Einsatzablage (Abschnitt 8.6). `meta`: bei Audio Rohtext, Modell, Dauer; bei Fotos Abmessungen, ggf. GPS und Aufnahmezeit. |
| `audit_event` | `nachricht_id`, `user_id`, `funktion`, `aktion`, `zeitpunkt`, `aenderungen` (JSON alt/neu) | **Append-only**, wird nie geändert oder gelöscht. |

Enums: `status` = `neu` · `gesichtet` · `erledigt`. Das ELW setzt ihn per Klick, jeder Wechsel steht mit
Name im `audit_event` (ersetzt den Sichtvermerk des Vordrucks).

Schema-Änderungen nur per **Alembic-Migration** (`backend/alembic/versions/`); sie laufen beim App-Start
automatisch (`upgrade_database()`).

---

## 7. Spracherkennung

### 7.1 Konzept

- **Push-to-Talk pro Feld** statt freiem Gesamtdiktat: Die Zuordnung zu Von/An/Inhalt ist eindeutig, der Prompt
  kann je Feld passen, Fehler bleiben lokal. „Von“ ergibt sich aus der Anmeldung. Eine Priorität gibt es bewusst nicht (entfallen in Phase 3).
- **Mensch bestätigt immer:** Der erkannte Text landet editierbar im Feld, erst „Absenden“ erzeugt die Nachricht.
- **Lokal:** faster-whisper (CTranslate2, int8 auf der CPU). Modell `large-v3-turbo`.

### 7.2 Pipeline (`stt/`)

| Schritt | Umsetzung |
|---|---|
| Aufnahme | `MediaRecorder` im Browser, mono, **ohne** Echo-/Rauschunterdrückung und AGC (Rohaudio), 64 kbit/s. Android: webm/opus, iOS: mp4/aac. Stille-Stopp relativ zum Grundrauschen. Zum Vergleich: `?audio=verarbeitet`. |
| Dekodierung | `whisper.decode_audio()` mit PyAV (bringt FFmpeg mit) → 16 kHz mono float32. Eigene Implementierung, weil `faster_whisper.decode_audio` mit PyAV ≥ 15 nicht läuft. |
| Erkennung | `language="de"`, `beam_size=5`, Silero-VAD, `condition_on_previous_text=False`, feldspezifischer `initial_prompt` (+ `hotwords` für „An“) |
| Prompt „An“ | Funktionsnamen **und Aliase** des Einsatzes. Ohne Aliase zieht der Prompt z.B. „Einsatzleitwagen“ zum ähnlichen „Einsatzleitung“. |
| Prompt „Inhalt“ | Beispielmeldung mit Fachbegriffen (PA, C-Rohr, RTW, NEF, DLK, Hydrant …) |
| Halluzinationsfilter | Bekannte Untertitel-Floskeln („Untertitel im Auftrag des ZDF“ …) und Segmente mit hoher No-Speech-Wahrscheinlichkeit bei geringer Konfidenz werden verworfen. |
| Normalisierung | Leerraum, Großschreibung von Abkürzungen (RTW, DLK, HLF …) |
| Wiederholungen („An“) | `entferne_wiederholungen()`: Das Modell wiederholt kurze Eingaben gern („Einsatzabschnitt, Brand, Einsatzabschnitt, Brand.“). Direkt aufeinanderfolgende gleiche Wortfolgen werden reduziert. |
| Empfänger-Zuordnung | `match_funktion()`: Füllwörter entfernen („an die …“), `rapidfuzz.ratio` gegen Name, Aliase und generierte Varianten („EA X“ → „Einsatzabschnitt X“, „Abschnitt X“). Ab 80 % automatisch übernommen. |

### 7.3 Austauschbarkeit

Alles hinter dem Protokoll `SpeechToText` (`load()`, `transcribe(audio, hint) -> Transcript`). Andere Engines
(whisper.cpp, eigenes Fine-Tuning, GPU-Rechner) lassen sich einsetzen, ohne API oder Frontend zu ändern.

### 7.4 Messung

Ergebnisse und Bewertung: [spracherkennung-messung.md](spracherkennung-messung.md). Kurzfassung: Die Idee
funktioniert. Mit echter Stimme und `large-v3-turbo` liegt die Wortfehlerrate bei 6 %, die Empfänger werden zu
100 % richtig zugeordnet, ca. 3 s pro Meldung bei 8 CPU-Threads. Entscheidend ist unverarbeitetes Audio vom Handy.

---

## 8. Querschnittliche Konzepte

### 8.1 Zeitstempel und Nachvollziehbarkeit

- **Maßgeblich ist `eingang_at`** (Serverzeit beim Speichern). Die Handy-Uhr (`erfasst_at`, Beginn der Erfassung)
  wird nur informativ gespeichert – Handyuhren können abweichen.
- Alle Zeitpunkte werden als UTC gespeichert (`UTCDateTime`) und nur zeitzonenbehaftet angenommen
  (Pydantic `AwareDatetime`); die Anzeige erfolgt in Ortszeit.
- **Laufende Nummer** pro Einsatz, vergeben per atomarem `UPDATE … RETURNING` – auch bei gleichzeitigen Meldungen
  lückenlos und ohne Dubletten.
- Jede Anlage/Änderung erzeugt einen `audit_event` mit alt/neu-Werten.

### 8.2 Datenschutz und Sicherheit

| Thema | Maßnahme |
|---|---|
| Datenfluss | Handy → HTTPS → ELW-Rechner → NAS daneben (Kabel). Sonst nichts. |
| Spracherkennung | Lokal mit Whisper. **Keine Web Speech API** (Chrome/Android sendet an Google, Safari an Apple). |
| Externe Ressourcen | Keine CDNs, Schriften oder Telemetrie; erzwungen per CSP `default-src 'self'`. |
| Offline | `MELDI_STT_LOCAL_FILES_ONLY=true`, `HF_HUB_OFFLINE=1` (in der Dienstkonfiguration gesetzt). |
| Netz | uvicorn nur auf `127.0.0.1`; von außen ausschließlich über Caddy/HTTPS. |
| Anmeldung | **Keine Passwörter (Phase 5):** Jedes Gerät, das den Server erreicht, kann jede Rolle wählen. Geschützt ist der Zugang derzeit nur durch das Netz. Vor dem ersten Einsatz mit echten Daten zu klären. Das ELW sieht unter „Angemeldet“, wer im System ist. |
| Session | Zufallstoken (256 bit) im Cookie `HttpOnly; Secure; SameSite=Strict`; in der DB nur SHA-256; Abmelden beendet serverseitig. |
| Rechte | Schützen ohne Passwörter nur vor Fehlbedienung. Serverseitig je Endpunkt (`ElwAnmeldung`, `LeseAnmeldung`, `MeldeAnmeldung` in `api/deps.py`); WebSocket prüft Rolle beim Verbindungsaufbau. Melder sehen nur eigene Nachrichten der aktuellen Anmeldung. |
| Privathandys | `Cache-Control: no-store` für die API; keine Nachrichten in localStorage/IndexedDB. Die Beobachter-Ansicht zeigt **alle** Nachrichten des Einsatzes auf einem Privathandy: Rolle nur gezielt vergeben, Filter und Liste liegen nur im Speicher, Abmelden leert die Ansicht. |
| Fotos | Vom Handy direkt hochgeladen (Kamera über `<input capture>`). Die App selbst speichert nichts auf dem Handy; ob die Kamera-App zusätzlich in die Galerie speichert, hängt vom Gerät ab (vor dem Einsatz prüfen). Der Server dekodiert und speichert sie neu als JPEG; nur GPS und Aufnahmezeit bleiben als EXIF erhalten. Ablage wie Audio (8.6). |
| Audio | Aufnahmen abgesendeter Nachrichten liegen in der Einsatzablage auf dem ELW-Rechner (8.6). Nie abgesendete Aufnahmen werden nach dem Absenden bzw. Abmelden gelöscht, bei abgelaufenen Anmeldungen spätestens beim nächsten Serverstart. Zusätzlich `MELDI_STT_KEEP_AUDIO=true` (nur Testphase, Benchmark-Material). |
| Header | CSP (`img-src` zusätzlich `blob:` für die Foto-Vorschau), `Permissions-Policy: microphone=(self)`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, `frame-ancestors 'none'` |

Betriebliche Empfehlungen (BitLocker, Firewall, Löschfristen): [betrieb.md](betrieb.md).

### 8.3 Fehlerbehandlung

- Spracherkennung nicht verfügbar (Modell fehlt, Fehler) → `503`, UI zeigt „bitte tippen“. **Tippen geht immer.**
- Modell lädt im Hintergrund beim Start; Ladefehler werden geloggt, der Server bleibt erreichbar.
- Senden fehlgeschlagen (Netz weg) → Formular bleibt erhalten, Hinweis „erneut senden“. Bewusst **kein**
  Offline-Puffer auf dem Handy (Datenschutz; siehe Roadmap).
- Abgelaufene Session → Melder landet auf der Anmeldung.

### 8.4 Konfiguration

Umgebungsvariablen mit Präfix `MELDI_` oder `backend/.env` (Vorlage: `backend/.env.example`), definiert in `app/config.py`.

| Variable | Standard | Bedeutung |
|---|---|---|
| `MELDI_DATA_DIR` | `<repo>/data` | Lokal: Datenbanken, Modelle, Logs, ggf. Testaufnahmen |
| `MELDI_ABLAGE_DIR` | `DATA_DIR/ablage` | Einsatzablage (8.6), vom Startfenster auf den Einsatzordner gesetzt |
| `MELDI_EINSATZ_KENNUNG` | leer | vom Startfenster: Datenbank unter `DATA_DIR/einsaetze/<kennung>/` |
| `MELDI_EINSATZ_BEZEICHNUNG` | leer | vom Startfenster: Name für einen neuen Einsatz |
| `MELDI_ABLAGE_NEU_AUFBAUEN` | `false` | vom Startfenster: Einträge aus der Datenbank neu schreiben (8.6) |
| `MELDI_MAX_FOTOS` / `_MAX_FOTO_BYTES` | `5` / 8 MB | je Nachricht / je Foto (das Frontend nimmt ebenfalls 5 an) |
| `MELDI_DATABASE_URL` | SQLite in `DATA_DIR` | alternative Datenbank |
| `MELDI_COOKIE_SECURE` | `true` | nur für lokale Entwicklung ohne HTTPS `false` |
| `MELDI_SESSION_HOURS` | `24` | Gültigkeit einer Anmeldung |
| `MELDI_STT_ENABLED` | `true` | Spracherkennung an/aus |
| `MELDI_STT_MODEL` | `large-v3-turbo` | Name oder Pfad zu einem CTranslate2-Modell |
| `MELDI_STT_DEVICE` / `_COMPUTE_TYPE` | `cpu` / `int8` | |
| `MELDI_STT_CPU_THREADS` | `0` (alle) | |
| `MELDI_STT_BEAM_SIZE` | `5` | |
| `MELDI_STT_MODEL_DIR` | `DATA_DIR/models` | |
| `MELDI_STT_LOCAL_FILES_ONLY` | `false` | im Einsatzbetrieb `true` |
| `MELDI_STT_MAX_AUDIO_SECONDS` / `_MAX_UPLOAD_BYTES` | `90` / 10 MB | |
| `MELDI_STT_KEEP_AUDIO` | `false` | nur Testphase: Aufnahmen speichern |

### 8.5 Tests

| Ebene | Wo | Inhalt |
|---|---|---|
| Unit | `tests/test_postprocess.py`, `test_audio.py` | Halluzinationsfilter, Empfänger-Zuordnung, Dekodierung von webm/opus, mp4/aac, ogg, wav |
| API | `tests/test_api.py` | Anmeldung, Rechte, lfd. Nr., Audit, WebSocket, Transcribe (mit `FakeSTT`), Header |
| Ablage | `tests/test_ablage.py`, `test_foto.py` | Ordner und Dateien je Nachricht, Übernahme/Löschen vorläufiger Uploads, Rollback, Sende-ID, fehlende Uploads, Fotos (GPS, Metadaten, Grenzen) |
| Startfenster | `tests/test_starter.py` | Ordner analysieren, Kennungsdatei, Kindprozesse (ohne Tk) |
| Migrationen | `tests/test_migrations.py` | Upgrade/Downgrade gegen eine Datenbank mit Daten (Fremdschlüssel bei Batch-Migrationen) |
| Modell (langsam) | `tests/test_whisper.py` | Echte Erkennung + Stille ohne Halluzination (`MELDI_TEST_WHISPER=1`) |
| Qualität | `tools/stt_bench` | Modellvergleich auf Testaufnahmen |

Jeder Test bekommt eine eigene SQLite-Datei mit echten Migrationen und eine eigene Einsatzablage.

### 8.6 Einsatzablage

Ziel ist eine lückenlose Dokumentation, die auch ohne Meldi lesbar bleibt. Jede Nachricht wird beim Absenden
zusätzlich zur Datenbank als Ordner abgelegt (`services/ablage.py`):

```
<MELDI_ABLAGE_DIR>/2026-11-07_1432_Übung_E3/
  einsatz.json
  0007_EA-Brand/
    nachricht.txt      wie der Vordruck: Nr., Von, An, Zeiten, Inhalt, Rohtext, Anhänge
    nachricht.json     vollständig, inkl. SHA-256 der Anhänge
    protokoll.jsonl    Audit, append-only (eine Zeile je Ereignis)
    an_1.webm  inhalt_1.webm  inhalt_2.webm  foto_1.jpg
```

- **NAS:** Im Betrieb ist die Wurzel der Ordner, den das Startfenster festlegt (mit Kennungsdatei
  `meldi-einsatz.json`). Bewusst ohne Puffer: Die Ablage liegt neben dem Rechner, fällt sie aus, schlägt das Absenden
  fehl.
- **Neuaufbau:** Fehlt der Einsatzordner, schreibt `MELDI_ABLAGE_NEU_AUFBAUEN` die lesbaren Einträge aus der
  Datenbank neu in einen neuen Ordner. `protokoll.jsonl` entsteht zuletzt und bekommt einen eigenen Eintrag, fehlende
  Audios und Fotos stehen in `nachricht.txt/json`. Vorhandene Einträge bleiben unberührt, der Vorgang ist wiederholbar.
- **Vorläufige Uploads:** Aufnahmen und Fotos entstehen vor der Nachricht. `transcribe` bzw.
  `uploads/foto` legen sie lokal unter `DATA_DIR/…/vorlaeufig/<anmeldung_id>/` ab und geben eine ID zurück, die das Formular
  beim Absenden in `anhaenge` mitschickt. Der Server prüft, dass die ID zur selben Anmeldung gehört. Der
  MIME-Typ folgt aus einer festen Liste von Endungen, nie aus Angaben des Handys.
- **Fehlende Uploads** (z.B. Serverneustart zwischen Aufnahme und Absenden) blockieren das Absenden nicht. Die
  Nachricht kommt an, das Fehlen steht im Protokoll und in `nachricht.txt`, das Handy zeigt einen Hinweis.
- **Wiederholtes Absenden:** Jedes Formular schickt eine `sende_id`. Kommt sie ein zweites Mal (Antwort ging
  verloren), liefert der Server die schon angelegte Nachricht zurück (`200`) statt einer zweiten.
- **Fotos:** Das Handy liest GPS und Aufnahmezeit aus den EXIF-Daten (`exifr`, gebündelt), verkleinert auf
  2560 px lange Kante (JPEG) und lädt hoch. Der Server dekodiert das Bild vollständig (Pillow, Schutz vor
  Dekompressionsbomben: Abmessungen werden vor dem Dekodieren geprüft, höchstens 25 MP, höchstens zwei
  Fotos gleichzeitig), begrenzt auf 4096 px, speichert es neu als JPEG und schreibt GPS und Aufnahmezeit
  wieder in die EXIF-Daten. Fremde Metadaten (Gerät, Software) fallen dabei weg. Viele Android-Handys geben
  Fotos ohne GPS an den Browser weiter; dann fehlt es.
- **Konsistenz:** Die Uploads werden vor der Datenbanksperre in einen Bereitstellungsordner kopiert und
  gehasht. In der Transaktion wird dieser Ordner nur noch umbenannt und um `nachricht.txt/json` und
  `protokoll.jsonl` ergänzt. Schlägt etwas fehl, wird der Ordner entfernt und die Transaktion zurückgerollt; die
  vorläufigen Uploads bleiben erhalten, erneutes Senden funktioniert.
- **Nie abgesendet:** Übrige vorläufige Uploads der Anmeldung (laut Server-Zeitstempel vor dem Absenden
  hochgeladen) werden nach dem Absenden gelöscht, alle beim Abmelden. Bei abgelaufenen Anmeldungen ohne
  Abmelden bleiben sie bis zum nächsten Serverstart liegen.
- **Dateisperren (Windows):** Virenscanner oder geöffnete Programme sperren Dateien. Umbenennen, Ersetzen und
  Anhängen werden deshalb bis zu ca. 1,5 s wiederholt. Bleibt die Sperre, antwortet der Server mit `503`, die
  Nachricht bzw. der Status wird zurückgerollt, und erneutes Senden funktioniert.
- **Serverstart:** Ist der Ablageort nicht beschreibbar (z.B. Datenträger fehlt), startet der Server nicht.
- **Nie überschreiben:** Existiert der Ordner einer Nachricht schon (Rest eines abgebrochenen Absendens), wird
  er in `…_alt_<Zeitstempel>` umbenannt.
- **Feste Pfade:** Einsatz- und Nachrichtenordner werden einmal festgelegt und in der Datenbank gespeichert.
  Eine geänderte Zeitzone oder Bezeichnung verschiebt nichts.
- `einsatz.json` wird nur geschrieben, wenn sich der Inhalt geändert hat.
- **Zeiten** in `nachricht.txt` in der Zeitzone des ELW-Rechners, in den JSON-Dateien als ISO-8601 mit Offset.

---

## 9. Verteilungssicht

```
┌────────── ELW ──────────────────────────────────────┐
│  LTE-/WLAN-Router ── WLAN ── Handys der Melder      │
│        │                                            │
│        └── LAN ── ELW-Rechner (Windows)             │
│                    ├─ Startfenster (meldi-start)    │
│                    │   ├─ Kind: Caddy   :443/:80      │
│                    │   └─ Kind: uvicorn 127.0.0.1:8000│
│                    ├─ data/ (einsaetze/, models/)     │
│                    └─ Kabel ── NAS (Einsatzablage)    │
└─────────────────────────────────────────────────────┘
         ┆ optional: WireGuard-VPN für Melder außer WLAN-Reichweite
```

**HTTPS ist Pflicht**, weil Browser das Mikrofon nur in sicheren Kontexten freigeben (Ausnahme `localhost`).

| Frage | Empfehlung | Details |
|---|---|---|
| Wie erreichen die Handys den ELW? | PoC: ELW-WLAN. Größere Einsatzstellen: WireGuard-VPN. **Kein offener Port** (Mobilfunk meist ohne feste/öffentliche IP; sonst Daten offen im Internet). | [betrieb.md](betrieb.md#netzwerk) |
| Woher kommt das Zertifikat? | PoC: lokale CA (`tls internal`). Betrieb mit Privathandys: eigene Subdomain + Let's Encrypt per DNS-Challenge (keine Installation auf den Handys). | [betrieb.md](betrieb.md#https-zertifikat) |

---

## 10. Architekturentscheidungen

| # | Entscheidung | Begründung | Verworfen |
|---|---|---|---|
| E1 | **Web-App** statt nativer App | Private Handys, nichts installieren, ein Code für Android/iOS | Native App (Store, Verteilung, zwei Plattformen) |
| E2 | **Spracherkennung auf dem Server (Whisper)** | Datenschutz; einheitliche Qualität unabhängig vom Handy; Vokabular steuerbar | Web Speech API (Audio an Google/Apple); Whisper im Browser (zu langsam/groß auf Handys) |
| E3 | **Push-to-Talk pro Feld** | Eindeutige Feldzuordnung, feldspezifischer Prompt, robuste Fehlerbehandlung | Gesamtdiktat mit Feldextraktion (regelbasiert fehleranfällig, LLM auf CPU langsam) – ggf. später |
| E4 | **faster-whisper `large-v3-turbo`, int8, CPU** | Mit echter Stimme deutlich genauer als kleinere Modelle, ~3 s pro Meldung bei 8 Threads (siehe Messung) | Kleinere Whisper-Modelle (mehr Fehler), `large-v3` (nicht genauer, 50 % langsamer), andere Engines (schwächer bei Fachbegriffen) |
| E5 | **Python/FastAPI + SQLite** | Whisper-Ökosystem in Python; SQLite ohne Serverbetrieb, eine Datei, WAL reicht für einen ELW | PostgreSQL (Betriebsaufwand), Node-Backend (Whisper-Anbindung umständlich) |
| E6 | **Kein Docker**, Start über das Startfenster | Office-PC mit Windows; der Server soll genau so lange laufen, wie das Fenster offen ist | Docker Compose; Windows-Dienste (laufen ohne Fenster weiter) |
| E7 | **Caddy** als TLS-Proxy | Eine Datei, automatisches HTTPS (lokale CA oder Let's Encrypt), auch unter Windows | nginx (Zertifikatsverwaltung manuell), TLS in uvicorn |
| E8 | **Vue 3 ohne UI-Framework** | Kleine Bundles für Handys, keine externen Ressourcen, wenig Abhängigkeiten | React/Komponentenbibliotheken |
| E9 | **Serverzeit maßgeblich**, Handyzeit informativ | Handyuhren weichen ab; eine Zeitquelle für die Dokumentation | Handyzeit als Erfassungszeit |
| E10 | **Audit append-only** statt Überschreiben | Nachvollziehbarkeit wie beim Vordruck (Durchschläge) | Nur „zuletzt geändert“ |
| E11 | **Kein Offline-Puffer auf dem Handy** | Keine sensiblen Daten auf Privatgeräten | Service Worker + IndexedDB (ggf. verschlüsselt, später prüfen) |
| E12 | **Datenbank lokal, Ablage auf der NAS** | SQLite im WAL-Modus braucht ein lokales Laufwerk; die lesbare Einsatzakte gehört auf die NAS | Datenbank auf der NAS |
| E13 | **Ablage ohne Puffer** | Die NAS steht per Kabel neben dem Rechner; bei Ausfall wird ein lokaler Einsatz geöffnet | Erst lokal sichern, dann auf die NAS übertragen |
| E14 | **Vorerst keine Passwörter** | Zuerst dokumentieren, wer was geschrieben hat; der Zugriff wird noch geklärt | PIN je Benutzer (bis Phase 4) |

---

## 11. Risiken und technische Schulden

| Risiko | Auswirkung | Maßnahme |
|---|---|---|
| Fachbegriffe/Dialekt schlecht erkannt | Melder müssen mehr tippen | Echte Aufnahmen sammeln, Vokabular erweitern, ggf. Fine-Tuning |
| ELW-Rechner langsamer als gemessen | Wartezeit > 5 s | Auf Zielhardware messen (≥ 8 Threads); Warteschlange im UI sichtbar |
| Ähnlich klingende Empfänger (Einsatzleitwagen ↔ Einsatzleiter) | Falscher Empfänger übernommen | Melder sieht Ergebnis vor dem Senden; Sprachregelung „ELW“; ggf. höhere Schwelle |
| HTTPS mit Privathandys | Ohne vertrautes Zertifikat kein Mikrofon | Let's-Encrypt-Variante umsetzen |
| Caddy-Konfiguration und Windows-Skripte noch nicht auf Zielsystem getestet | Inbetriebnahme hakt | Test auf ELW-Rechner (Roadmap) |
| Keine Passwörter | Jedes Gerät im Netz kann alles lesen; Namen sind nicht geprüft | Vor dem ersten Einsatz mit echten Daten klären (siehe Roadmap) |
| Gelöschter Einsatzordner | Audio und Fotos verloren, Texte neu schreibbar | NAS-Rechte, Snapshots, Warnung im Startfenster, Neuaufbau |
