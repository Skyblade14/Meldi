# Spracherkennung – Messergebnisse

Werkzeug und Anleitung: [tools/stt_bench/README.md](../tools/stt_bench/README.md) · Architektur: [architecture.md](architecture.md#7-spracherkennung)

Modell: **faster-whisper `large-v3-turbo`**, int8, CPU, Beam 5, mit Feuerwehr-Prompt.

## Echte Stimme (07.11.2026)

**Aufbau:**
- Android-Handy im WLAN, App über `deploy/start-lan-test.sh`, ein Sprecher, ruhige Umgebung.
- Sätze aus `tools/stt_bench/samples.yaml` in der App eingesprochen und mit `import_app.py` übernommen.
- 5 Inhalte und 6 Empfänger. Gemessen mit 8 CPU-Threads, um den ELW-Rechner (~1000 €) nachzustellen.

| WER Inhalt | CER Inhalt | Fachbegriffe¹ | Empfänger richtig | Ø Rechenzeit pro Meldung |
|---|---|---|---|---|
| 6 % | 1 % | 90 % | 100 % | 3,0 s |

WER = Wortfehlerrate, CER = Zeichenfehlerrate ohne Leerzeichen (0 % = perfekt).
¹ Exakt erkannte Fachbegriffe. Getrennt geschriebene zusammengesetzte Wörter zählen als Treffer.

Verbliebene Fehler: „Nachrischarbeiten“ statt „Nachlöscharbeiten“, „über dem Balkon“ statt „über den Balkon“.

### Aufnahme im Browser: roh statt verarbeitet

Mit eingeschalteter Echo-/Rauschunterdrückung und AGC und 32 kbit/s kam das Audio in Telefonqualität an.
Oberhalb von 4 kHz fehlte fast alles, damit gingen die Zischlaute (s, f, sch, z) verloren. Die Erkennung war
entsprechend schlecht. Ursache ist vermutlich der Telefonie-Modus, in den Android mit `echoCancellation` schaltet.

| Aufnahme | Energie 4–6 kHz | Energie 6–8 kHz | Eindruck |
|---|---|---|---|
| verarbeitet, 32 kbit/s | −42 dB | −101 dB | „ziemlich mies“ |
| **roh, 64 kbit/s** | **−27 dB** | **−30 dB** | „deutlich besser“ |

(Anteil an der Gesamtenergie.) Die Aufnahme läuft seitdem roh mit 64 kbit/s (`AUFNAHME_PROFILE` in
`useRecorder.ts`). Ob die Rauschunterdrückung bei starkem Lärm doch hilft, ist noch offen (`?audio=verarbeitet`).

### Modellwahl

Gleiche echte Aufnahmen, 8 Threads:

| Kandidat | WER Inhalt | Fachbegriffe | Ø Rechenzeit | Ergebnis |
|---|---|---|---|---|
| **`large-v3-turbo`** | **6 %** | **90 %** | **3,0 s** | gewählt |
| `large-v3` | 16 %² | 90 % | 4,6 s | nicht genauer, 50 % langsamer |
| kleinere Whisper-Modelle | 16–24 % | 73–83 % | 1–2,5 s | „Friedleiter“, „RCB“ statt RTW |
| Whisper deutsch nachtrainiert, NVIDIA Parakeet | 16–37 % | 43–67 % | 0,2–3,8 s | schwächer bei Fachbegriffen und Abkürzungen |

² Fast nur durch Zusammenschreibung („Feuerunterkontrolle“). Inhaltlich gleichauf.

Die synthetischen Stimmen (s.u.) hatten ein kleineres Modell gleichauf gesehen. Mit echter Stimme ist der
Abstand deutlich. **Für Entscheidungen zählen echte Aufnahmen.**

## Synthetische Stimmen (07.11.2026)

**Aufbau:**
- 30 Meldungen aus `samples.yaml` (10 Empfänger, 20 Inhalte), gesprochen von 3 Piper-TTS-Stimmen
  (thorsten, kerstin, karlsson).
- Jede Meldung ohne Lärm, mit Pumpenlärm (10 dB und 3 dB SNR) und mit Wind (5 dB SNR). Zusammen 360 Aufnahmen,
  dazu 5 Aufnahmen ohne Sprache.
- 4 CPU-Threads.

| WER Inhalt | CER Inhalt | Fachbegriffe | Empfänger richtig | Halluzination bei Stille | Ø Rechenzeit |
|---|---|---|---|---|---|
| 16 % | 4 % | 76 % | 97 % | 0/5 | 3,5 s |

Am häufigsten verfehlt: Nachalarmierung, Rettungsschere, Ölspur, Riegelstellung, Restdruck, Lüfter. Die
synthetischen Stimmen sprechen manche davon unsauber aus.

## Gefundene Probleme

| Problem | Ursache | Status |
|---|---|---|
| Schlechte Erkennung vom Handy | Browser-Audioverarbeitung beschneidet das Frequenzband | **Behoben:** Rohaudio, 64 kbit/s |
| „Einsatzleitwagen“ wurde als „Einsatzleitung“ erkannt | Der Prompt enthielt nur „ELW“, nicht die gesprochene Variante | **Behoben:** Aliase stehen im Prompt |
| Empfänger doppelt („Einsatzabschnitt, Brand, Einsatzabschnitt, Brand.“), bei Lärm Wiederholung der Empfängerliste | Wiederholungsschleife des Modells bei kurzen Eingaben und Listen-Prompts | **Behoben:** `entferne_wiederholungen()` im Feld „An“ |
| „Rettungsdienst“ → „Auf Wiedersehen“ (Stimme kerstin) | Schlechte Qualität dieser TTS-Stimme | Harmlos, Score 47 %, nur Vorschläge |
| Aufnahme endet mitten im Satz (2 von 22 Versuchen) | Unklar: Stille-Stopp bei Sprechpause oder manuell gestoppt | Offen, beobachten |

## Offen

- **Mehr echte Stimmen:** weitere Kameraden, draußen, neben laufender Pumpe, mit Dialekt.
- **Messung auf dem ELW-Rechner** (`run.py --threads 8` bzw. alle Kerne).
- **iPhone/Safari** (mp4/aac) testen.
- **Gegenprobe roh vs. `?audio=verarbeitet`** bei Pumpenlärm.
- **Vokabular erweitern** (z.B. Nachlöscharbeiten). Dafür eigene Testsätze, die nicht im Prompt stehen.
