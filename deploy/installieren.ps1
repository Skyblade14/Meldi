# Meldi unter Windows installieren, aktualisieren oder auf die vorige Version zurueckstellen.
#   installieren.cmd                  installiert oder aktualisiert nach C:\Meldi
#   installieren.cmd -Zurueck         stellt die vorige Version wieder her
# Weitere Schalter: -Ziel <Ordner>, -OhneModell, -Still (keine Rueckfragen).
#
# Nur PowerShell 5.1 und nur ASCII in dieser Datei: PowerShell 5.1 liest Skripte ohne BOM als ANSI.
param(
    [string]$Ziel = "C:\Meldi",
    [switch]$Zurueck,
    [switch]$OhneModell,
    [switch]$Still
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$Ziel = [IO.Path]::GetFullPath($Ziel)
$quelle = Split-Path -Parent $PSScriptRoot
$versionen = Join-Path $Ziel "versionen"
$aktiv = Join-Path $Ziel "aktiv"
$data = Join-Path $Ziel "data"
$einsaetze = Join-Path $data "einsaetze"
$sicherung = Join-Path $data "sicherung"
$vorigeDatei = Join-Path $Ziel "vorige-version.txt"
$marker = ".installiert"
$behalten = 3

function Meldung([string]$Text) {
    Write-Host $Text -ForegroundColor Green
}

function Lies-Version([string]$Ordner) {
    $datei = Join-Path $Ordner "VERSION"
    if (Test-Path -LiteralPath $datei) {
        return (Get-Content -LiteralPath $datei -Raw).Trim()
    }
    return $null
}

function Pruefe-Nicht-Laufend {
    if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
        throw "Meldi laeuft noch (Port 8000 belegt). Bitte zuerst das Startfenster schliessen."
    }
}

function Starte-Programm([string]$Programm, [string[]]$Argumente, [string]$Ordner) {
    # uv schreibt den Fortschritt auf stderr. Mit "Stop" kann PowerShell 5.1 das als Fehler werten.
    $vorher = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    Push-Location -LiteralPath $Ordner
    try {
        & $Programm @Argumente
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
        $ErrorActionPreference = $vorher
    }
    if ($code -ne 0) {
        throw "$Programm endete mit Code $code"
    }
}

function Setze-Aktiv([string]$Ordner) {
    if (Test-Path -LiteralPath $aktiv) {
        # Nicht Remove-Item: PowerShell 5.1 kann dabei in das Ziel der Junction hineinloeschen.
        [IO.Directory]::Delete($aktiv, $false)
    }
    New-Item -ItemType Junction -Path $aktiv -Target $Ordner | Out-Null
}

function Installiere-Abhaengigkeiten([string]$Ordner) {
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $Ziel "python"
    $env:UV_CACHE_DIR = Join-Path $Ziel "uv-cache"
    $env:VIRTUAL_ENV = $null
    $env:UV_PYTHON = $null
    # --no-build: Auf dem ELW-Rechner wird nichts kompiliert, es kommen nur die Dateien mit den Hashes aus uv.lock.
    # --no-install-project: Die App laeuft aus dem Quellordner, sonst muesste uv ein Build-Werkzeug nachladen.
    $argumente = @("sync", "--frozen", "--no-dev", "--no-install-project", "--no-build", "--managed-python")
    Starte-Programm (Join-Path $Ordner "deploy\bin\uv.exe") $argumente (Join-Path $Ordner "backend")
}

function Schreibe-Einstellungen([string]$Ordner) {
    # Der Datenordner liegt ausserhalb der Versionen, sonst waeren die Einsaetze nach einem Update weg.
    # Schraegstriche und einfache Anfuehrungszeichen, damit die .env-Datei keine Backslash-Folgen auswertet.
    $pfad = $data.Replace("\", "/")
    [IO.File]::WriteAllText((Join-Path $Ordner "backend\.env"), "MELDI_DATA_DIR='$pfad'`r`n")
}

function Lade-Modell([string]$Ordner) {
    $vorhanden = Join-Path $data "models\models--*large-v3-turbo\snapshots\*\model.bin"
    if ($OhneModell -or (Test-Path -Path $vorhanden)) {
        return
    }
    Meldung "Lade das Sprachmodell (etwa 1,6 GB), das dauert einige Minuten ..."
    $env:HF_HUB_DISABLE_TELEMETRY = "1"
    $backend = Join-Path $Ordner "backend"
    Starte-Programm (Join-Path $backend ".venv\Scripts\python.exe") @("-m", "app.cli", "download-model") $backend
}

function Sichere-Einsaetze([string]$Version) {
    if (-not (Test-Path -LiteralPath $einsaetze)) {
        return
    }
    $zielOrdner = Join-Path (Join-Path $sicherung $Version) "einsaetze"
    if (Test-Path -LiteralPath $zielOrdner) {
        Remove-Item -LiteralPath $zielOrdner -Recurse -Force
    }
    # Vorlaeufige Uploads wurden nie abgesendet und muessen spurlos verschwinden, also nicht mitsichern.
    Get-ChildItem -LiteralPath $einsaetze -Recurse -File |
        Where-Object { $_.FullName -notmatch '\\vorlaeufig\\' } |
        ForEach-Object {
            $relativ = $_.FullName.Substring($einsaetze.Length + 1)
            $kopie = Join-Path $zielOrdner $relativ
            [IO.Directory]::CreateDirectory((Split-Path -Parent $kopie)) | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $kopie
        }
}

function Lege-Verknuepfung-An {
    $backend = Join-Path $aktiv "backend"
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "Meldi.lnk"))
    $link.TargetPath = Join-Path $backend ".venv\Scripts\pythonw.exe"
    $link.Arguments = '-c "from app.starter import main; main()"'
    $link.WorkingDirectory = $backend
    $link.Description = "Meldi Startfenster"
    $link.Save()
}

function Biete-Firewall-An {
    $name = "Meldi HTTPS"
    if ($Still -or (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue)) {
        return
    }
    $antwort = Read-Host "Firewall-Regel fuer TCP 80 und 443 nur im privaten Netz anlegen? Das braucht Adminrechte. (j/n)"
    if ($antwort -notmatch '^[jJ]') {
        Write-Host "Ohne die Regel erreichen die Handys den Server nicht. Siehe docs/betrieb.md."
        return
    }
    $befehl = "New-NetFirewallRule -DisplayName '$name' -Direction Inbound -Protocol TCP -LocalPort 80,443 -Profile Private -Action Allow"
    try {
        Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList "-NoProfile", "-Command", $befehl
    } catch {
        Write-Host "Die Regel wurde nicht angelegt: $_"
    }
}

function Raeume-Auf {
    $aktuell = Lies-Version $aktiv
    $Vorige = ""
    if (Test-Path -LiteralPath $vorigeDatei) {
        $Vorige = (Get-Content -LiteralPath $vorigeDatei -Raw).Trim()
    }
    Get-ChildItem -LiteralPath $versionen -Directory |
        Sort-Object CreationTime -Descending |
        Select-Object -Skip $behalten |
        Where-Object { $_.Name -ne $aktuell -and $_.Name -ne $Vorige } |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force
            $alt = Join-Path $sicherung $_.Name
            if (Test-Path -LiteralPath $alt) {
                Remove-Item -LiteralPath $alt -Recurse -Force
            }
        }
}

function Installieren {
    $version = Lies-Version $quelle
    if (-not $version) {
        throw "Keine VERSION-Datei gefunden. Bitte das entpackte Release-Paket verwenden."
    }
    Pruefe-Nicht-Laufend
    $bisher = Lies-Version $aktiv
    $ordner = Join-Path $versionen $version
    $fertig = Join-Path $ordner $marker
    [IO.Directory]::CreateDirectory($versionen) | Out-Null

    if ($ordner -eq $quelle) {
        throw "Bitte aus dem entpackten Release-Paket starten, nicht aus dem installierten Ordner."
    }
    if ((Test-Path -LiteralPath $fertig) -and $version -ne $bisher) {
        throw "Version $version ist schon vorhanden. Zum Zurueckgehen -Zurueck verwenden, denn aeltere Software versteht neuere Datenbanken nicht."
    }

    if (-not (Test-Path -LiteralPath $fertig)) {
        # Reste eines abgebrochenen Versuchs entfernen. Die bisherige Version bleibt bis zur Umstellung unberuehrt.
        if (Test-Path -LiteralPath $ordner) {
            Remove-Item -LiteralPath $ordner -Recurse -Force
        }
        # Aus dem Internet geladene Dateien sperrt Windows sonst beim Start.
        Get-ChildItem -LiteralPath $quelle -Recurse -File | Unblock-File
        Meldung "Installiere Meldi $version nach $ordner ..."
        Copy-Item -LiteralPath $quelle -Destination $ordner -Recurse
        Schreibe-Einstellungen $ordner
        Installiere-Abhaengigkeiten $ordner
        Lade-Modell $ordner
        [IO.File]::WriteAllText($fertig, $version)
    }

    if ($bisher -and $bisher -ne $version) {
        Meldung "Sichere die Datenbanken von Version $bisher ..."
        Sichere-Einsaetze $bisher
        [IO.File]::WriteAllText($vorigeDatei, $bisher)
    }
    Setze-Aktiv $ordner
    Lege-Verknuepfung-An
    Biete-Firewall-An
    Raeume-Auf
    Meldung "Meldi $version ist installiert. Start ueber die Verknuepfung Meldi auf dem Desktop."
}

function Schema-Stand([string]$Ordner) {
    $migrationen = Get-ChildItem -LiteralPath (Join-Path $Ordner "backend\alembic\versions") -Filter "*.py" |
        Sort-Object Name | ForEach-Object { $_.Name }
    return ($migrationen -join "|")
}

function Zurueckstellen {
    Pruefe-Nicht-Laufend
    if (-not (Test-Path -LiteralPath $vorigeDatei)) {
        throw "Es gibt keine vorige Version, zu der zurueckgestellt werden kann."
    }
    $version = (Get-Content -LiteralPath $vorigeDatei -Raw).Trim()
    $ordner = Join-Path $versionen $version
    if (-not (Test-Path -LiteralPath (Join-Path $ordner $marker))) {
        throw "Version $version ist nicht mehr vollstaendig vorhanden."
    }

    # Ohne Schema-Aenderung passt die Datenbank weiter, und nichts seit dem Update geht verloren.
    if ((Schema-Stand $ordner) -ne (Schema-Stand $aktiv) -and (Test-Path -LiteralPath $einsaetze)) {
        $gesichert = Join-Path (Join-Path $sicherung $version) "einsaetze"
        if (-not (Test-Path -LiteralPath $gesichert)) {
            throw "Fuer Version $version gibt es keine Datenbank-Sicherung."
        }
        if (-not $Still) {
            $antwort = Read-Host "Die Datenbanken gehen auf den Stand vor dem Update zurueck. Fortfahren? (j/n)"
            if ($antwort -notmatch '^[jJ]') {
                throw "Abgebrochen."
            }
        }
        $aufheben = Join-Path $sicherung ("vor-rueckweg-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
        Move-Item -LiteralPath $einsaetze -Destination $aufheben
        Copy-Item -LiteralPath $gesichert -Destination $einsaetze -Recurse
        Meldung "Der neuere Stand der Datenbanken liegt unter $aufheben."
    }

    Setze-Aktiv $ordner
    Remove-Item -LiteralPath $vorigeDatei
    Meldung "Meldi $version ist wieder aktiv."
}

try {
    if ($Zurueck) {
        Zurueckstellen
    } else {
        Installieren
    }
    exit 0
} catch {
    Write-Host "FEHLER: $_" -ForegroundColor Red
    exit 1
}
