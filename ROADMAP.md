# Roadmap

Stand: 09.11.2026 · Architektur: [docs/architecture.md](docs/architecture.md) · Betrieb: [docs/betrieb.md](docs/betrieb.md)

Hier stehen nur offene Themen. Was fertig ist, steht im Code, in der Doku und in der Git-Historie.

---

## Bedingungen für den ersten echten Einsatz

Für Tests und Übungen ohne echte Daten gelten sie noch nicht. Testserver trotzdem nur im VPN oder ELW-WLAN betreiben,
denn der öffentliche Code zeigt, dass es keine Zugangsprüfung gibt.

- **Zugriff regeln:** Ohne PIN kann jedes Gerät im WLAN oder VPN die ELW-Ansicht öffnen und alle Nachrichten, Aufnahmen
  und Fotos lesen. Zur Wahl stehen eine feste Benutzerliste mit PIN oder die Anmeldung per Einsatz-Code, den das ELW
  ausgibt. Bei einer Benutzerliste kommt eine Benutzerverwaltung dazu (anlegen, PIN zurücksetzen, deaktivieren).
- **Datenschutz-Dokumentation** mit der/dem Datenschutzbeauftragten abstimmen: Verzeichnis von Verarbeitungstätigkeiten,
  TOMs, ggf. DSFA. Die Speicherung von Audio und Fotos auf der NAS sowie das Mitlesen auf Privathandys (Beobachter)
  ausdrücklich aufnehmen.
- **Aufbewahrung festlegen und umsetzen:** Wie lange werden Einsatznachrichten, Audio und Fotos gespeichert? Wer darf
  exportieren? Danach Archivierung und Löschfristen einschließlich Einsatzablage umsetzen: abgeschlossene Einsätze
  exportieren und danach löschen bzw. anonymisieren. Setzt den Export voraus (siehe [Funktionen](#funktionen)).

---

## Test auf echter Hardware

Die Funktionen sind gebaut und automatisch getestet, aber noch nicht auf den Zielgeräten erprobt.

**Windows-Rechner** (Startfenster, Server und Caddy):

- CustomTkinter im uv-Python: Aussehen, Skalierung, Hell/Dunkel
- Kindprozesse und Job-Objekt, Absturz, Herunterfahren, Standby, doppeltes Öffnen, Schließen mit Bestätigung
- Adresse bei zwei Netzwerkkarten
- NAS-Pfade (UNC und verbundenes Laufwerk), Ablage mit Wiederholung bei Dateisperren und Prüfung beim Serverstart
- NAS-Ausfall: Absenden schlägt fehl, neuer Einsatz auf dem Rechner lässt sich öffnen
- Gelöschter Einsatzordner: rote Warnung im laufenden Betrieb, „In neuem Ordner fortsetzen“ mit Neuaufbau
- Oberflächen im Browser anklicken
- Markieren und Kopieren nach EDP Web mit Edge, vor allem Fotos per Rechtsklick → „Bild kopieren“

**Handys** (Android bestanden: HTTPS mit lokaler CA über `deploy/start-lan-test.sh`):

- iPhone/Safari: HTTPS mit lokaler CA, Live-Kanal unter der CSP (Fund F4 in
  [docs/review-findings.md](docs/review-findings.md))
- Fotos auf Android und iPhone: Landen Kamerafotos wirklich nicht in der Galerie? Liefern die Handys GPS mit? Falls
  nicht: Standort optional über den Browser abfragen
- Beobachter-Ansicht: Ist die Liste nach Bildschirm-aus oder App-Wechsel wieder aktuell?

---

## Praxistest Spracherkennung

Ziel: Die Messwerte synthetischer Stimmen durch echte ersetzen und das Vokabular final festlegen. Sollte vor dem
weiteren Ausbau passieren, weil die Ergebnisse die Bedienung beeinflussen.

- `stt_bench` auf dem echten ELW-Rechner laufen lassen
- Echte Aufnahmen von 5–10 Kameraden sammeln: drinnen, draußen, neben laufender Pumpe, mit Handschuhen und Helm
- Gegenprobe zur Audio-Verarbeitung des Browsers neben laufender Pumpe (`?audio=verarbeitet`). In ruhiger Umgebung
  schadet sie deutlich und ist deshalb aus
- Vokabular-Prompt anhand echter Meldungen erweitern und gegenmessen
- Schwelle für die automatische Empfänger-Übernahme (derzeit 80 %) anhand der Daten prüfen
- Übungseinsatz mit Meldi parallel zum Papiervordruck und Rückmeldung der Melder einholen

---

## Netz und HTTPS

- **Netzwerk festlegen:** ELW-WLAN, VPN oder beides? Welcher Router bzw. Mobilfunktarif ist im ELW verbaut?
- **VPN:** Bevorzugt Tailscale, sofern die Lizenz die Nutzung durch die Feuerwehr erlaubt (Nutzungsbedingungen prüfen,
  ggf. bezahlter Plan). Der Koordinationsserver sieht Metadaten (Geräte, IPs), aber keine Inhalte. Sonst WireGuard direkt
  oder Headscale (selbstgehosteter Koordinationsserver).
- **HTTPS ohne Zertifikatsinstallation:** Entweder Subdomain mit Let's Encrypt per DNS-Challenge und Caddy-Build mit
  DNS-Modul (braucht eine Feuerwehr-Domain, deren DNS per API verwaltbar ist) oder mit Tailscale `tailscale cert` statt
  eigener Domain.
- Anleitung für die Handys (QR-Code)
- Im Fahrzeug einrichten (eigenes WLAN-Passwort, kein Gastzugang) und mit Android und iPhone prüfen

---

## Funktionen

- **Export pro Einsatz:** PDF im Layout des Vierfachvordrucks, Einsatztagebuch, CSV. Dazu „Einsatz abschließen“, das
  `ende` setzt
- **Datensicherung:** automatische Kopie der Datenbank
- **Statusseite bzw. Health-Check** für die Technik im ELW: Modell geladen, Warteschlange, Speicherplatz
- **Funktionen des Einsatzes bearbeiten** (zurückgestellt): hinzufügen, umbenennen, Aliase pflegen, die die Erkennung
  verbessern. Kein Löschen, alte Nachrichten behalten den alten Namen
- **Repo bereinigen** (zurückgestellt): Frontend auf Überflüssiges prüfen. Im Backend und bei den Skripten ist nur noch
  `backend/alembic/README` entbehrlich

---

## Installation im ELW

Ziel: Meldi läuft auf dem echten ELW-Rechner mit NAS, Netz und Handys und ist einsatzbereit. Die Schritte stehen in
[docs/betrieb.md](docs/betrieb.md). Baut auf dem Test auf echter Hardware und den Festlegungen zu Netz und HTTPS auf.

- **Rechner auswählen und prüfen:** Welcher Rechner genau? Mindestens 8 CPU-Threads für `large-v3-turbo` (sonst
  Modellwahl neu bewerten), genug Speicherplatz, Standby im Einsatz ausgeschlossen
- **Update einmal auf dem echten Rechner durchspielen:** Update und Rückweg mit echten Einsatz-Datenbanken, Migrationen
  beim Öffnen eines Einsatzes prüfen
- **Meldi installieren:** Release-Paket laden und `installieren.cmd` ausführen (Internet nötig)
- **Datenordner prüfen:** Der Installer legt die Datenbanken nach `<Zielordner>\data`. Zielordner auf einem lokalen, von
  BitLocker erfassten Laufwerk wählen, nie die NAS. Das Startfenster zeigt den Pfad nicht an. Entscheiden, ob es das
  soll
- **Eigene Caddy-Einstellungen:** `deploy\Caddyfile` und `caddy.exe` liegen im Versionsordner. Eine Umstellung auf Let's
  Encrypt ginge beim nächsten Update verloren. Mit der Festlegung zu Netz und HTTPS lösen
- **Rechner absichern:** BitLocker, Windows-Firewall eingehend TCP 443 und 80 nur für das private Netz
- **NAS einrichten:** Freigabe mit Schreiben und Löschen nur für das Konto des ELW-Rechners, Snapshots oder Papierkorb,
  Verschlüsselung, Laufwerk unter demselben Konto wie `meldi-start` verbinden
- **Offline-Probe:** Rechner ohne Internet starten, Modell lädt, Sprachaufnahme, Foto und Absenden funktionieren
- **Kurzanleitung für das ELW-Personal:** Starten, Beenden, Vorgehen bei NAS-Ausfall und gelöschtem Einsatzordner
- **Generalprobe** in einer Übung mit dem kompletten Aufbau. Testaufnahmen löschen, `MELDI_STT_KEEP_AUDIO` ist aus

---

## Ideen und spätere Optionen

| Idee | Anmerkung |
|---|---|
| Gesamtdiktat, aus dem die Felder automatisch erkannt werden | Mit kleinem lokalem LLM. Auf der CPU langsam, Nutzen erst nach dem Praxistest bewerten |
| Fine-Tuning von Whisper auf eigene Aufnahmen | Lohnt sich, wenn Fachbegriffe bzw. Dialekt im Praxistest schwach bleiben |
| Live-Transkription während des Sprechens (Streaming) | Komfort. Erhöht Komplexität und CPU-Last |
| Offline-Puffer auf dem Handy bei Funkloch | Steht im Konflikt zum Datenschutz (Daten auf Privatgeräten). Nur verschlüsselt und kurzlebig, Abwägung nötig |
| Installierbare PWA (Homescreen-Icon) | Ohne Offline-Cache für Daten |
| Lagekarte / Abschnittsübersicht | Eigenes Thema, nicht Kern der Melder-Software |
| Mehrere ELW bzw. Abschnittsleitungen synchronisieren | Erst bei Bedarf |
| Anbindung an EDP Web oder andere Einsatzleitsoftware | Nachrichten direkt übertragen statt kopieren, ggf. über eine REST-API. Planen, wenn die Schnittstelle bekannt ist |
| Nachricht im ELW korrigieren | Erkennungsfehler berichtigen, Original bleibt im Protokoll. Derzeit nicht nötig, korrigiert wird in EDP Web |
| Rückmeldung an den Melder | „im ELW gelesen“ bzw. „erledigt“. Alternative: Der Melder schickt seine Telefonnummer mit, damit das ELW ihn erreicht |
| Akustische und optische Signale | Bei neuen Nachrichten, konfigurierbar (z.B. nur für bestimmte Empfänger) |
