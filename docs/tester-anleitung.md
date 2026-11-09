# Meldi testen: Anleitung für Tester

Meldi läuft auf einem privaten Testrechner und ist nur über Tailscale erreichbar (ein privates VPN, kostenlos
für Privatnutzer). Du brauchst dafür etwa 10 Minuten, einmalig. Es sind **nur Übungsdaten** im System, bitte
keine echten Einsatzdaten eingeben.

Du brauchst:

- ein Smartphone (Android oder iPhone)
- eine Einladung zum Tailscale-Netz (bekommst du vom Testleiter)
- die Datei `ca.crt` (bekommst du vom Testleiter, z. B. per Messenger oder Mail)
- die Adresse des Testrechners (bekommst du vom Testleiter, in dieser Anleitung `ADRESSE` genannt)

## 1. Tailscale installieren

1. Installiere die App **Tailscale** aus dem Play Store (Android) oder App Store (iPhone).
2. Öffne die Einladung des Testleiters und melde dich mit deinem Google-, Microsoft-, Apple- oder GitHub-Konto an.
   Bitte nutze dieselbe E-Mail-Adresse, an die die Einladung ging.
3. Erlaube in der App die VPN-Verbindung, wenn das Handy fragt.
4. Schalte in der App den Schalter oben auf **Verbunden**. Auf dem Handy erscheint ein Schlüssel- oder VPN-Symbol.

Tailscale muss beim Testen **verbunden** sein. Wenn die Seite nicht lädt, prüfe das zuerst.

## 2. Zertifikat installieren (einmalig)

Ohne diesen Schritt warnt der Browser vor einer unsicheren Verbindung, und das Mikrofon funktioniert nicht.

**Android**

1. Speichere die Datei `ca.crt` auf dem Handy.
2. Öffne *Einstellungen → Sicherheit → Weitere Sicherheitseinstellungen → Von Speicher installieren → CA-Zertifikat*
   (je nach Hersteller etwas anders, Suche nach „Zertifikat“ hilft).
3. Bestätige die Warnung („Trotzdem installieren“) und wähle `ca.crt`.

**iPhone**

1. Öffne `ca.crt` (z. B. aus der Mail oder den Dateien) und wähle *Zulassen*.
2. Gehe zu *Einstellungen → Allgemein → VPN & Geräteverwaltung*, tippe auf „Meldi Test-CA“ und wähle *Installieren*.
3. Gehe zu *Einstellungen → Allgemein → Info → Zertifikatsvertrauenseinstellungen* und schalte
   „Meldi Test-CA“ **ein**.

## 3. Meldi öffnen

1. Stelle sicher, dass Tailscale verbunden ist.
2. Öffne im Browser (Chrome auf Android, Safari auf iPhone):
   `https://ADRESSE:8443/melder/`
3. Gib deinen Namen ein, wähle deine Funktion und tippe auf **Anmelden**.
4. Erlaube dem Browser den Zugriff aufs **Mikrofon**, wenn er fragt.

Tipp: Lege ein Lesezeichen an oder wähle „Zum Home-Bildschirm“.

## Beobachter-Ansicht (nur lesen)

Als Beobachter siehst du alle Nachrichten live, kannst aber nichts melden oder ändern.

1. Öffne `https://ADRESSE:8443/beobachter/`
2. Gib deinen Namen ein und tippe auf **Anmelden**.
3. Lass einen zweiten Tester als Melder eine Nachricht absenden und prüfe, ob sie bei dir sofort erscheint.
   Prüfe auch die Statusanzeige und den Filter.

## 4. Was getestet werden soll

- Eine Nachricht per Sprache aufnehmen, prüfen, ob der erkannte Text stimmt, und absenden.
- Ein Foto anhängen.
- Eine Nachricht bewusst falsch erkennen lassen, den Text korrigieren und senden.
- Abmelden und wieder anmelden.

Bitte notiere bei Auffälligkeiten: Was hast du gesagt, was wurde erkannt, welches Handy und welcher Browser.

## Probleme

| Problem | Lösung |
|---|---|
| Seite lädt nicht | Tailscale auf dem Handy öffnen und prüfen, ob „Verbunden“ angezeigt wird. Der Testrechner muss laufen. |
| Zertifikatswarnung im Browser | Schritt 2 wiederholen. Auf dem iPhone den Schalter unter „Zertifikatsvertrauenseinstellungen“ prüfen. |
| Mikrofon geht nicht | Mikrofonfreigabe für den Browser in den Handy-Einstellungen prüfen. Die Seite muss über `https://` geöffnet sein. |
