# STT-Benchmark

Beantwortet die Frage: **Ist die lokale Spracherkennung auf dem ELW-Rechner gut und schnell genug?**

Alle Befehle aus `backend/` ausführen (nutzt dessen Python-Umgebung und exakt denselben Erkennungsweg wie die App).

## 1. Testaufnahmen

### Synthetisch (sofort verfügbar)
```bash
uv run python ../tools/stt_bench/synth.py
```
Erzeugt mit lokaler Sprachsynthese (Piper, 3 Stimmen) alle Sätze aus `samples.yaml` – jeweils sauber, mit
Pumpenlärm (10 dB / 3 dB SNR) und Wind (5 dB SNR), plus Aufnahmen ohne Sprache (Halluzinationstest).
→ `audio/synth/<stimme>_<bedingung>/<id>.wav`

### Echt (aussagekräftiger!)
Kameraden lesen die Sätze aus `samples.yaml` ein – am besten mit dem eigenen Handy, im Freien, gern neben
laufender Pumpe. Dateien benennen nach Sample-ID und in einen Ordner pro Sprecher/Bedingung legen:
```
audio/real/max_draussen/in01.m4a
audio/real/max_draussen/an03.m4a
audio/real/lisa_pumpe/in01.webm
```
Alternativ in der App sammeln: `MELDI_STT_KEEP_AUDIO=true` setzen (z.B. `deploy/start-lan-test.sh`), die Sätze
aus `samples.yaml` in die Felder einsprechen, dann übernehmen:
```bash
uv run python ../tools/stt_bench/import_app.py max_draussen     # → audio/real/max_draussen_roh/…
```
Das Skript ordnet jede Aufnahme anhand des erkannten Textes dem passenden Satz zu und überspringt unklare.
**Nur mit Übungstexten, `data/audio/` danach löschen.**

## 2. Auswerten
```bash
uv run python ../tools/stt_bench/run.py                                    # synthetisch + echt
uv run python ../tools/stt_bench/run.py --audio ../tools/stt_bench/audio/real
uv run python ../tools/stt_bench/run.py --ohne-prompt                      # Effekt des Vokabulars
uv run python ../tools/stt_bench/run.py --threads 8                        # Ziel-PC nachstellen
```
Ergebnisse: `results/<zeit>_summary.md` (Übersicht) und `results/<zeit>_details.csv` (jede Aufnahme).

**Wichtig:** Die Zeiten gelten für den Rechner, auf dem gemessen wird – final auf dem ELW-Rechner laufen lassen.

## Kennzahlen
| Kennzahl | Bedeutung |
|---|---|
| WER Inhalt | Wortfehlerrate im Inhaltsfeld (0 % = perfekt). Getrennte Komposita („Angriff Trupp“) zählen voll als Fehler. |
| CER Inhalt | Zeichenfehlerrate ohne Leerzeichen – näher am „ist der Sinn noch klar?“ |
| Fachbegriffe | Anteil der in `samples.yaml` markierten Begriffe, die exakt erkannt wurden |
| Empfänger richtig | gesprochener Empfänger → richtige Funktion zugeordnet |
| Halluzination | Aufnahmen ohne Sprache, bei denen trotzdem Text erkannt wurde |
| Echtzeitfaktor | Rechenzeit / Aufnahmedauer (0,3 = 10 s Aufnahme in 3 s erkannt) |
