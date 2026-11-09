# Review-Findings

Stand: 08.11.2026 · Entstanden bei der Planung der [Teststrategie](teststrategy.md)

Alle Punkte stammen zunächst aus dem Lesen des Codes. Jeder Fund bekam vor der Korrektur einen Test, und jeder dieser
Tests schlug gegen den alten Code fehl. Damit sind alle sieben bestätigt und behoben.

| Nr. | Fund | Einstufung | Status | Test |
|---|---|---|---|---|
| F1 | Live-Kanal bleibt nach Abmeldung offen | hoch | ✅ behoben | `test_rechte.py`: `test_live_kanal_endet_*` |
| F2 | Abgelaufene Sitzung führt im ELW nicht zum Login | mittel | ✅ behoben | `ui/test_elw.py`: `test_abgelaufene_sitzung_*` |
| F3 | Audit ist nur per Konvention append-only | mittel | ✅ behoben (Migration 0005) | `test_migrations.py`: `test_audit_ist_append_only` |
| F4 | CSP erlaubt WebSockets zu beliebigen Hosts | mittel | ✅ behoben, echtes iPhone offen | `test_regeln.py`: `test_csp_*` |
| F5 | Absenden während der Erkennung verliert das Ergebnis | mittel | ✅ behoben | `ui/test_sprache.py`: `test_absenden_gesperrt_*` |
| F6 | Unlesbares Foto sperrt das Absenden ohne Hinweis am Knopf | niedrig | ✅ behoben | `ui/test_fotos.py`: `test_kaputte_datei_*` |
| F7 | Abgelaufene Sitzung wird im Melder uneinheitlich behandelt | niedrig | ✅ behoben | `ui/test_melden.py`: `test_sitzung_*` |

**Abweichung bei F4:** Statt `connect-src 'self'` steht der eigene Host ausdrücklich in der CSP
(`connect-src 'self' ws://<host> wss://<host>`). `'self'` deckt `wss:` nicht in jedem Safari ab, so hängt der Live-Kanal
nicht davon ab. Fremde Hosts bleiben gesperrt. Ein Test auf einem echten iPhone steht trotzdem noch aus.

**Weitere Funde beim Umsetzen**, ebenfalls behoben:

- Touch-Ziele unter 44 px: Abmelden (Melder), Chips, „OK“, Links wie „Inhalt leeren“
- Lange Wörter ohne Umbruchmöglichkeit erzeugten eine horizontale Scrollleiste (Detail, Beobachter-Karte)
- Validierungsfehler (422) erschienen als rohes JSON auf Englisch, jetzt „Eingabe ungültig …“
- Nach einem Rollenwechsel im zweiten Tab versuchte der Live-Kanal der ersten Ansicht endlos die Neuverbindung
- Die Liste „Gesendet“ blieb nach einer neuen Anmeldung auf dem Stand der vorherigen Person stehen

Die Abschnitte unten beschreiben den Ausgangszustand vor der Korrektur.

---

## F1: Live-Kanal bleibt nach Abmeldung offen

**Stellen:** `backend/app/api/ws.py:11`, `backend/app/services/notifier.py`, `backend/app/api/auth.py:55`

Die Sitzung wird nur beim Verbindungsaufbau des WebSockets geprüft. `logout` und die neue Anmeldung in `login` beenden
die `Anmeldung`, entfernen die Verbindung aber nicht aus dem `Notifier`. Auch beim Ablauf von `gueltig_bis` passiert
nichts.

**Folge:** Ein bereits offener WebSocket erhält weiter alle Nachrichten des Einsatzes, obwohl die Anmeldung nicht mehr
gilt. Das Frontend trennt beim normalen Abmelden im selben Tab selbst. Betroffen sind daher zweite Tabs, abgelaufene
Sitzungen und Clients, die den Kanal absichtlich offen halten. Das widerspricht der Regel, Rechte serverseitig zu
prüfen.

**Vorschlag:** Verbindungen der `Anmeldung` zuordnen, beim Abmelden schließen und vor dem Versand beziehungsweise
regelmäßig die Gültigkeit prüfen.

**Test:** API-Test mit offenem WebSocket: Abmelden oder Ablauf, danach darf keine neue Nachricht mehr ankommen.

## F2: Abgelaufene Sitzung führt im ELW nicht zum Login

**Stellen:** `frontend/src/shared/useLiveFeed.ts:30`, `frontend/src/shared/useEingang.ts:70`

Ist die Sitzung ungültig, lehnt der Server den WebSocket ab. `onclose` versucht es unbegrenzt erneut, die Ansicht
zeigt dauerhaft „getrennt“. `useEingang` fängt Fehler beim ersten Laden nicht ab (`onMounted(laden)`).

**Folge:** Das ELW-Personal sieht eine vermeintliche Netzstörung und bekommt keinen Hinweis, sich neu anzumelden.

**Vorschlag:** Beim Wiederverbinden die Sitzung prüfen (`/api/auth/me`) und bei 401 zum Login wechseln.

**Test:** UI-Test: Sitzung serverseitig beenden, Verbindung trennen, die Ansicht muss zum Login führen.

## F3: Audit ist nur per Konvention append-only

**Stellen:** `backend/alembic/versions/`, `backend/app/models/audit.py`

Laut `CLAUDE.md` ist `audit_event` append-only. In den Migrationen und im Modell gibt es aber keinen Trigger und keine
andere Sperre gegen `UPDATE` oder `DELETE`.

**Folge:** Ein Programmfehler oder eine künftige Änderung könnte das Protokoll unbemerkt verändern.

**Vorschlag:** SQLite-Trigger per Alembic-Migration, die `UPDATE` und `DELETE` auf `audit_event` abweisen.

**Test:** `UPDATE` und `DELETE` auf `audit_event` müssen fehlschlagen.

## F4: CSP erlaubt WebSockets zu beliebigen Hosts

**Stelle:** `backend/app/main.py:24`

`connect-src 'self' wss: ws:` lässt WebSocket-Verbindungen zu jedem Host zu. Das schwächt die Regel „keine externen
Requests“: Eingeschleuster Code könnte Daten über einen fremden WebSocket abfließen lassen.

**Vorschlag:** Auf `connect-src 'self'` reduzieren. Vorher auf einem echten iPhone prüfen, ob der eigene `wss:`-Kanal
damit weiter funktioniert.

**Test:** Der Wert der CSP wird in `test_regeln.py` exakt festgeschrieben. Im UI-Test läuft der Live-Kanal weiter.

## F5: Absenden während der Erkennung verliert das Ergebnis

**Stelle:** `frontend/src/melder/MessageForm.vue:49`

`sendebereit` berücksichtigt nur Formularfelder, Fotos und den Sendevorgang, nicht laufende Aufnahmen oder Erkennungen.
Nach dem Absenden erzwingt `formNr` neue Mikrofon-Knöpfe.

**Folge:** Wer absendet, während eine weitere Etappe noch erkannt wird, verliert diesen Text ohne Hinweis. Die
vorgemerkte Aufnahme bleibt bis zum Abmelden oder Serverstart liegen.

**Vorschlag:** Absenden sperren, solange aufgenommen oder erkannt wird, und den Grund anzeigen.

**Test:** UI-Test mit angehaltener `FakeSTT`: Der Knopf ist gesperrt, oder der Text geht nicht verloren.

## F6: Unlesbares Foto sperrt das Absenden ohne Hinweis am Knopf

**Stellen:** `frontend/src/melder/MessageForm.vue:48`, `frontend/src/melder/MessageForm.vue:98`

Ein Foto, das nicht vorbereitet werden kann, bleibt ohne `id` in der Liste. Damit ist `fotosFertig` falsch und
„Absenden“ gesperrt. „erneut“ gibt es dafür nicht, weil `f.foto` fehlt. Der Fehlertext steht nur an der Foto-Kachel.

**Folge:** Unter Stress ist nicht erkennbar, dass man das Foto entfernen muss, um die Nachricht senden zu können.

**Vorschlag:** Beim gesperrten Knopf den Grund anzeigen.

**Test:** UI-Test mit kaputter Bilddatei: Hinweis sichtbar, nach dem Entfernen ist Absenden möglich.

## F7: Abgelaufene Sitzung wird im Melder uneinheitlich behandelt

**Stellen:** `frontend/src/melder/MessageForm.vue:52`, `frontend/src/melder/MessageForm.vue:162`,
`frontend/src/shared/RecordButton.vue:44`

- Das Laden der gesendeten Nachrichten beim Öffnen hat keine Fehlerbehandlung, ein 401 führt dort nicht zum Login.
- Ein 401 bei der Spracherkennung zeigt nur einen Fehler am Mikrofon-Knopf.
- Ein 401 beim Absenden wechselt sofort zum Login. Das Formular wird dabei entfernt, der Text ist weg.

**Vorschlag:** 401 zentral behandeln und den Formularinhalt bis zur erneuten Anmeldung im Arbeitsspeicher behalten,
nicht im Browser-Speicher (Datenschutzregel).

**Test:** UI-Test: Sitzung beim Tippen beenden, absenden, neu anmelden, der Text ist noch da.
