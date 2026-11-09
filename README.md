# Meldi

Digitale Melder-Software für die Feuerwehr – ersetzt den Vierfachvordruck. Läuft komplett lokal auf einem
Rechner im Einsatzleitwagen (ELW); Nachrichten werden auf dem Smartphone **per Sprache** erfasst.

- **Melder** (`/melder/`): Anmeldung mit Name + Funktion, Nachricht erfassen (An, Inhalt, Fotos) –
  jedes Feld per Mikrofon-Taste einsprechbar.
- **ELW** (`/elw/`, Desktop): Live-Eingang aller Nachrichten mit Status (neu → gesichtet → erledigt), Filter,
  Suche und Protokoll. Felder und Fotos lassen sich zum Übertragen nach EDP Web markieren und kopieren.
- **Beobachter** (`/beobachter/`, Handy): alle Nachrichten live mitlesen, filtern und suchen, ohne Änderungen.
- **Datenschutz:** Spracherkennung (Whisper) läuft auf dem ELW-Rechner. Keine Cloud, keine CDNs,
  keine Browser-Spracherkennung.

## Dokumentation

| Dokument | Inhalt |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Architektur: Bausteine, Abläufe, API, Datenmodell, Spracherkennung, Sicherheit, Entscheidungen |
| [docs/betrieb.md](docs/betrieb.md) | Installation unter Windows, Netzwerk, HTTPS-Zertifikat, Datenschutz im Betrieb |
| [docs/spracherkennung-messung.md](docs/spracherkennung-messung.md) | Messergebnisse und Modellempfehlung |
| [ROADMAP.md](ROADMAP.md) | Offene Themen |
| [CLAUDE.md](CLAUDE.md) | Hinweise für die Entwicklung mit Claude Code (Regeln, Befehle, Konventionen) |

## Schnellstart (Entwicklung)

Voraussetzungen: [uv](https://docs.astral.sh/uv/), Node.js ≥ 20.

```bash
cd frontend && npm ci && npm run build && cd ..
cd backend
uv sync
uv run meldi download-model            # einmalig, large-v3-turbo, ~1,6 GB
uv run meldi demo                      # Übungseinsatz anlegen
MELDI_COOKIE_SECURE=false uv run uvicorn --factory app.main:create_app --port 8000
```
Dann `http://localhost:8000/` öffnen und die Ansicht wählen. Über `localhost` erlaubt der
Browser das Mikrofon auch ohne HTTPS. **Handys brauchen HTTPS** → mit Caddy starten:
`deploy/start-dev.sh` (Linux) bzw. `deploy\start-dev.ps1 -HostName <IP>` (Windows).
Schneller Handytest unter Linux ohne Caddy: `./deploy/start-lan-test.sh` → `https://<LAN-IP>:8443/melder/`
(Firewall-Port 8443 freigeben, Zertifikatswarnung wegklicken oder `data/tls/ca.crt` installieren).

Frontend mit Hot-Reload: Backend wie oben starten, dann `cd frontend && npm run dev` (Port 5173, leitet `/api` weiter).

## Einsatzbetrieb

Im ELW startet `meldi-start` ein kleines Fenster, das nach Einsatzordner und Einsatznamen fragt. Der Server läuft,
solange das Fenster offen ist (siehe [docs/betrieb.md](docs/betrieb.md)). Zugang ohne Passwörter: Startseite öffnen,
Ansicht wählen, Name und Funktion eintragen.

## Tests

```bash
cd backend
uv run pytest                                          # schnell, ohne Whisper
MELDI_TEST_WHISPER=1 uv run pytest -m slow             # mit echtem Modell (synth. Audio nötig, s.u.)
```

## Spracherkennung messen

Siehe [tools/stt_bench/README.md](tools/stt_bench/README.md) – Modellvergleich mit synthetischen und echten
Aufnahmen (Fehlerrate, Fachbegriffe, Empfänger-Zuordnung, Geschwindigkeit).

## Projektstruktur

```
backend/   FastAPI-App: api/ (HTTP+WebSocket), services/ (Fachlogik), stt/ (Spracherkennung), models/ (DB)
frontend/  Vue 3: src/melder (Handy), src/elw (Leitstelle), src/shared (API, Aufnahme, Komponenten)
tools/     stt_bench – Benchmark der Spracherkennung
deploy/    Caddyfile (HTTPS), Startskripte
docs/      Architektur und Betriebskonzept
```

## Lizenz

GNU Affero General Public License v3.0, siehe [LICENSE](LICENSE).
