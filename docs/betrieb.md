# Meldi – Betrieb und Installation

Architektur: [architecture.md](architecture.md)

> **Stand:** Startfenster, Windows-Skripte und Caddy-Konfiguration sind noch nicht auf einem Windows-Rechner
> getestet.

> **Achtung:** Es gibt derzeit keine Passwörter. Jedes Gerät im WLAN oder VPN kann die ELW-Ansicht öffnen und alle
> Nachrichten, Aufnahmen und Fotos lesen. Vor dem ersten Einsatz mit echten Daten muss der Zugriff geklärt sein.

## Installation unter Windows

**Voraussetzungen:** Windows 10 oder 11 (64 Bit) und Internet während der Installation. Python, uv, Caddy und Node.js
müssen nicht vorhanden sein.

1. Unter [Releases](https://github.com/Skyblade14/Meldi/releases) `meldi-<Version>-windows-x64.zip` laden und entpacken.
   Prüfsumme vergleichen: `Get-FileHash <Datei>` gegen `SHA256SUMS`.
2. `installieren.cmd` doppelklicken. Windows kann davor warnen, weil das Paket nicht signiert ist. Der Installer
   - legt `C:\Meldi` an (anderer Ort: `installieren.cmd -Ziel D:\Meldi`),
   - lädt Python 3.12 und die Bibliotheken, geprüft gegen die Hashes aus `uv.lock`,
   - lädt das Sprachmodell (`large-v3-turbo`, ~1,6 GB),
   - legt die Verknüpfung „Meldi“ auf dem Desktop an,
   - fragt nach der Firewall-Regel: eingehend TCP 443 und 80, **nur für das private Netz**.
3. Wird der Rechner unter einer anderen Adresse erreicht als seiner ersten IP, die Umgebungsvariable `MELDI_HOST` setzen.
4. NAS einrichten (siehe [NAS](#nas)).

**Ablage auf dem Rechner:**

| Ordner | Inhalt |
|---|---|
| `C:\Meldi\versionen\<Version>\` | App mit eigenem `.venv`. Die letzten drei Versionen bleiben erhalten |
| `C:\Meldi\aktiv` | Verweis auf die laufende Version |
| `C:\Meldi\data\` | Datenbanken, Modelle, Logs, Sicherungen. `data\` meint unten immer diesen Ordner |
| `C:\Meldi\python\`, `C:\Meldi\uv-cache\` | Python und Paket-Zwischenspeicher, lassen sich neu herunterladen |

**Modell ohne Internet:** Den Ordner `data\models\` eines anderen Rechners vor der Installation nach `C:\Meldi\data\models\`
kopieren. Der Installer lädt dann nichts nach.

### Update

Startfenster schließen, das neue ZIP entpacken und dessen `installieren.cmd` starten. Das braucht wieder Internet, im
Einsatz wird keines gebraucht. Erst wenn die neue Version vollständig installiert ist, sichert der Installer die
Datenbanken nach `data\sicherung\<alte Version>\` und stellt um. Bricht der Download ab, bleibt die alte Version aktiv.
Datenbank-Migrationen laufen beim ersten Öffnen eines Einsatzes.

### Zurück zur vorigen Version

`C:\Meldi\versionen\<Version>\installieren.cmd -Zurueck` braucht kein Internet. Hat das Update das Datenbankschema
geändert, gehen die Datenbanken auf den Stand vor dem Update zurück, denn alte Software versteht neuere nicht. Der neuere
Stand bleibt unter `data\sicherung\vor-rueckweg-<Zeit>\` liegen.

### Aus dem Quellcode (Entwicklung)

Braucht uv und Node.js: `npm ci; npm run build` in `frontend\`, `uv sync` und `uv run meldi download-model` in `backend\`,
`caddy.exe` nach `deploy\bin\`. Gestartet wird über `backend\.venv\Scripts\meldi-start.exe`.

## Einsatz starten

`meldi-start` öffnet das Startfenster. Dort den Einsatzordner auf der NAS wählen (`\\nas\…` oder verbundenes
Laufwerk) und den Einsatznamen eintragen.

- **Neuer Ordner:** Es entsteht ein neuer Einsatz mit den Standard-Funktionen.
- **Ordner mit vorhandenem Einsatz:** Das Fenster zeigt Name, Beginn und Nachrichtenzahl und bietet „Einsatz
  fortsetzen“ an.
- **Das Fenster bleibt offen**, solange der Server laufen soll. Schließen geht nur nach Rückfrage und stoppt Server
  und HTTPS. Der Einsatz bleibt dabei offen und lässt sich wieder öffnen.
- **NAS ausgefallen:** Das Absenden schlägt mit einer Fehlermeldung fehl. Einen neuen Einsatz in einem lokalen Ordner
  öffnen und dort weiterarbeiten.
- **Einsatzordner gelöscht:** Das Fenster zeigt eine rote Warnung. Unter den bekannten Einsätzen „In neuem Ordner
  fortsetzen“ wählen. Nachrichten und Protokolle werden aus der Datenbank neu geschrieben und die Nummerierung läuft
  weiter. Audio und Fotos sind nur über Snapshots oder den Papierkorb der NAS zu retten.

**Aufrufen:** `https://<Adresse>/` zeigt die Kacheln Melder, ELW und Beobachter. Danach trägt man Name und Funktion
ein. Die Namen sind nur Angaben der Person, sie werden nicht geprüft. Wer gerade angemeldet ist, zeigt in der
ELW-Ansicht die Schaltfläche „Angemeldet“.

**Meldungen per Funk oder Telefon** erfasst das ELW über „Nachricht erfassen“. Der Link öffnet die
Melder-Ansicht im selben Browser, angemeldet mit der ELW-Funktion. Achtung: „Abmelden“ dort meldet auch die
ELW-Ansicht ab (gemeinsame Sitzung). Den Melder-Tab einfach schließen.

**Zum Testen ohne Dienste:** `deploy\start-dev.ps1 -HostName <IP>`

## NAS

Die NAS steht neben dem ELW-Rechner und ist per Kabel verbunden. Auf ihr liegt die Einsatzablage, die Datenbank
bleibt lokal.

- Schreiben und Löschen im Freigabeordner nur für das Windows-Konto des ELW-Rechners, alle anderen höchstens lesen.
- Snapshots oder Papierkorb für den Freigabeordner aktivieren. Nur das rettet gelöschte Aufnahmen und Fotos.
- Das Laufwerk unter demselben Konto verbinden, unter dem `meldi-start` läuft.

## Netzwerk

| Variante | Bewertung |
|---|---|
| **ELW-WLAN** (Router oder Access Point am Fahrzeug) | Einfach, kein Internet nötig, aber begrenzte Reichweite. **Empfohlen für den PoC.** |
| **WireGuard-VPN** über Mobilfunk | Für Melder außerhalb der WLAN-Reichweite. Braucht einen erreichbaren VPN-Endpunkt: am Feuerwehrhaus (Festnetz + DynDNS) oder ein LTE-Tarif mit fester öffentlicher IP (Business/M2M-APN). Auf den Handys: WireGuard-App + QR-Code. |
| Port öffnen, Zugriff über IP | **Nicht empfohlen.** Mobilfunk-Router haben meist keine feste und oft keine öffentliche IP (Carrier-NAT), dann funktioniert es gar nicht. Wenn doch, stünde die App mit sensiblen Daten offen im Internet. |

## HTTPS-Zertifikat

Browser geben das Mikrofon nur über HTTPS frei.

### Variante A: lokale Zertifizierungsstelle (PoC, Testgeräte)

`deploy/Caddyfile` nutzt `tls internal`. Caddy erzeugt dabei eine eigene Zertifizierungsstelle. Deren
Root-Zertifikat muss einmalig auf jedem Gerät installiert werden.

**Wo das Root-Zertifikat liegt:**
- Windows: `%AppData%\Caddy\pki\authorities\local\root.crt`
- Linux: `~/.local/share/caddy/pki/authorities/local/root.crt`

**Installation auf Android:** *Einstellungen → Sicherheit → Verschlüsselung & Anmeldedaten → Zertifikat
installieren → CA-Zertifikat*

**Installation auf iOS:**
1. Datei öffnen und das Profil installieren.
2. Unter *Einstellungen → Allgemein → Info → Zertifikatsvertrauenseinstellungen* das Vertrauen aktivieren.

Für Privathandys im Dauerbetrieb ist das unpraktisch.

### Variante B: eigene Subdomain + Let's Encrypt (empfohlen für Privathandys)

**Prinzip:**
- Beispiel: `melder.ff-beispiel.de`. Der DNS-Eintrag zeigt auf die **private** IP des ELW-Rechners,
  also seine Adresse im WLAN bzw. VPN.
- Das Zertifikat wird per DNS-API bestätigt. Dafür muss **kein Port geöffnet** werden.
- Handys vertrauen dem Zertifikat ohne jede Installation.

**Voraussetzungen und Einschränkungen:**
- Caddy braucht ein Build mit dem DNS-Modul des eigenen Anbieters (z.B. Hetzner, Cloudflare, IONOS). Das
  Build gibt es auf caddyserver.com/download mit dem passenden Plugin.
- Die Erneuerung alle ~60 Tage braucht kurz Internet.
- Router mit DNS-Rebind-Schutz (z.B. FritzBox) brauchen eine Ausnahme für die Domain.
- Ohne Internet im Einsatz muss der ELW-Router den Namen lokal auflösen (lokaler DNS-Eintrag).

**Umstellung:** Im `Caddyfile` die `tls internal`-Zeile durch den auskommentierten `tls { dns … }`-Block ersetzen.

## Einsatzbetrieb

- Offline-Betrieb stellt das Startfenster selbst ein: `MELDI_STT_LOCAL_FILES_ONLY=true`, `HF_HUB_OFFLINE=1`,
  `HF_HUB_DISABLE_TELEMETRY=1`.
- Die Logs liegen unter `data\logs\`.
- Ob das Modell geladen ist, zeigt das Startfenster.

## Datenschutz im Betrieb

- **BitLocker** auf dem ELW-Rechner aktivieren: `data\einsaetze\` enthält die Datenbanken mit allen Einsatztexten.
- **NAS verschlüsseln.** BitLocker schützt sie nicht, und die Einsatzablage enthält Sprachaufnahmen und Fotos (ggf.
  mit GPS).
- Eigenes WLAN-Passwort, regelmäßig gewechselt. Kein Gastzugang.
- **Aufbewahrungs- und Löschfristen** für `data\einsaetze\`, `data\sicherung\` und die Einsatzablage mit der/dem
  Datenschutzbeauftragten festlegen. Bis es eine Exportfunktion gibt, wird die Datei manuell gesichert bzw. gelöscht.
- `data\sicherung\` enthält nach jedem Update Kopien aller Einsatz-Datenbanken. Wer einen Einsatz löscht, muss ihn auch dort
  löschen.
- `MELDI_STT_KEEP_AUDIO` im Einsatz **niemals** aktivieren. Testaufnahmen in `data\audio\` nach der
  Auswertung löschen.

## Einsatzablage

Den Ablageort legt das Startfenster fest. Ist er nicht beschreibbar, startet der Server nicht (Ursache in
`data\logs\`). Dateien der Ablage während des Einsatzes nicht in Word oder Excel öffnen, solange die Nachricht
noch bearbeitet wird: Das sperrt sie, und die Statusänderung schlägt dann fehl. Der Editor sperrt nicht.

## Datensicherung

Die Einsatzablage (ein Ordner pro Einsatz, siehe [architecture.md, 8.6](architecture.md)) ist die lesbare
Dokumentation und lässt sich einfach kopieren, z.B. nach dem Einsatz auf einen verschlüsselten Datenträger.

Die Datenbank eines Einsatzes ist `data\einsaetze\<kennung>\meldi.db`. Zusammen mit `-wal` und `-shm` sichern, oder
bei geschlossenem Startfenster kopieren. Die Modelle in `data\models\` lassen sich jederzeit neu herunterladen.
