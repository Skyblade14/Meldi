---
name: release
description: Neue Meldi-Version veröffentlichen. Prüft den Stand, setzt Version und Changelog, pusht das Tag, verfolgt die Release-Action und gibt den Entwurf erst nach Freigabe frei.
argument-hint: "[patch|minor|major|rc|X.Y.Z|X.Y.Z-rc.N]"
disable-model-invocation: true
---

# Release

Ziel: Ein Tag `vX.Y.Z` löst `.github/workflows/release.yml` aus, und am Ende steht ein geprüfter Release auf GitHub.
Die Action legt nur einen Entwurf an. Veröffentlicht wird erst nach ausdrücklicher Freigabe in Schritt 6.

Grundregeln:

- **Tags werden nie verschoben oder gelöscht.** Scheitert ein Release, gibt es ein neues `rc` oder einen Patch.
- An den beiden markierten Stopps warten, auch wenn vorher schon „mach mal“ gesagt wurde.
- Das Repository ist öffentlich: keine Einsatzdaten, Namen oder Adressen in Changelog und Commit-Text.

## 1. Stand prüfen

Abbrechen und die Ursache nennen, wenn etwas davon nicht stimmt:

- Branch ist `main`, `git status --porcelain` ist leer, `git fetch` zeigt keinen Unterschied zu `origin/main`.
- Der Lauf von `Tests` für `HEAD` ist grün: `gh run list --workflow tests.yml --commit "$(git rev-parse HEAD)"`.
- Es gibt keinen offenen Release-Entwurf: `gh release list`.

## 2. Änderungen auswerten

Letztes Tag: `git describe --tags --abbrev=0`. Gibt es noch keines, gilt die gesamte Historie. Dann
`git log <tag>..HEAD` und `git diff --stat <tag>..HEAD` lesen.

Version bestimmen (Argument hat Vorrang, ohne Argument einen Vorschlag machen):

| Änderung | Stufe |
|---|---|
| Fehlerbehebungen | patch |
| Neue Funktionen, neue Migrationen | minor |
| `rc` | `-rc.N` hochzählen, oder neues `X.Y.Z-rc.1` |

Solange die Windows-Installation nicht auf echter Hardware erprobt ist (`docs/betrieb.md`, Hinweis „Stand“): nur `rc`.

Auffälligkeiten für Schritt 4 notieren:

- **Neue Dateien in `backend/alembic/versions/`:** Das Update ändert die Datenbanken. Der Rückweg setzt sie dann auf den
  Stand vor dem Update zurück.
- **Änderungen an `deploy/`, `tools/paket.py` oder den Werkzeug-Einträgen in `WERKZEUGE`:** besonders aufmerksam testen.

## 3. Spracherkennung lokal prüfen

CI lädt nie Whisper. Hat sich seit dem letzten Tag etwas unter `backend/app/stt/` oder an `faster-whisper`, `av`,
`ctranslate2`, `onnxruntime`, `tokenizers` oder `huggingface-hub` geändert (`git diff <tag>..HEAD -- backend/uv.lock`):

```bash
python tools/regression.py whisper
```

Sonst diesen Schritt überspringen und das im Bericht sagen. Prüfen, ob die festen Versionen in `WERKZEUGE` und
`PYTHON_VERSION` (`tools/paket.py`) Sicherheitsupdates verpassen. Dependabot pflegt sie nicht.

## 4. Version setzen, Changelog schreiben

`CHANGELOG.md` unter `## Unveröffentlicht` ergänzen: kurz, auf Deutsch, aus Sicht der Anwender. Interne Umbauten nur, wenn
sie etwas bewirken. Bei neuen Migrationen den Hinweis auf den Rückweg aufnehmen. Dann:

```bash
python tools/paket.py setze-version <version>
python tools/paket.py pruefe-tag v<version>
git diff
```

**STOPP 1.** Version, Changelog und die Auffälligkeiten zeigen und fragen, ob Commit, Tag und Push erfolgen sollen.

## 5. Commit, Tag, Action

```bash
git add CHANGELOG.md backend/pyproject.toml backend/uv.lock frontend/package.json frontend/package-lock.json
git commit -m "Release <version>"   # mit den Attributionszeilen aus den aktuellen Sitzungsanweisungen
git tag -a v<version> -m "Meldi <version>"
git push origin main
git push origin v<version>
```

Die Action läuft etwa 15 bis 30 Minuten: `gh run list --workflow release.yml --limit 1`, dann `gh run watch <id>` im
Hintergrund. Nicht in kurzen Abständen abfragen.

Schlägt sie fehl: die Ursache nennen (`gh run view <id> --log-failed`), das Tag stehen lassen und nach der Korrektur mit
einer neuen Version wieder bei Schritt 1 beginnen. Treffer der Leak-Prüfung nur mit Datei und Zeile melden.

## 6. Entwurf freigeben

`gh release view v<version> --json assets,isDraft,isPrerelease,body` prüfen: ZIP und `SHA256SUMS` sind vorhanden, die
Notizen stimmen, die Warnung zur fehlenden Zugangsprüfung steht noch drin, solange `ROADMAP.md` den Punkt als offen führt.

**STOPP 2.** Den Link zum Entwurf nennen. Zum Test auf dem Windows-Rechner auffordern: ZIP laden, `installieren.cmd`
ausführen, Startfenster öffnen, eine Sprachnachricht senden. Veröffentlichen erst nach ausdrücklichem OK:

```bash
gh release edit v<version> --draft=false
```

Danach den Link zum veröffentlichten Release melden und nennen, was übersprungen wurde.
