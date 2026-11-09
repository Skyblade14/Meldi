@echo off
rem Startet den Installer. Das Bypass gilt nur fuer diesen einen Aufruf, die Windows-Richtlinie bleibt unveraendert.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\installieren.ps1" %*
set MELDI_ERGEBNIS=%ERRORLEVEL%
rem Bei Doppelklick bliebe die Meldung sonst nicht lesbar stehen.
if "%~1"=="" pause
exit /b %MELDI_ERGEBNIS%
