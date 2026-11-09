"""Server und Caddy als Kindprozesse, ohne Oberfläche."""

import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import BACKEND_DIR, PROJECT_DIR
from app.starter.ordner import Startauftrag

log = logging.getLogger("meldi.starter")

WINDOWS = sys.platform == "win32"
HEALTH_URL = "http://127.0.0.1:8000/api/health"
LOKALE_ADRESSE = "http://localhost:8000/"
# Eine Windows-Proxy-Einstellung darf die Abfrage von localhost nicht umleiten.
_OHNE_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


if WINDOWS:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _kernel32.TerminateJobObject.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.SetThreadExecutionState.argtypes = (wintypes.DWORD,)
    _kernel32.SetThreadExecutionState.restype = wintypes.DWORD

    class _BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimits),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]
else:
    import fcntl

_JOB_EXTENDED_LIMITS = 9
_KILL_ON_JOB_CLOSE = 0x2000
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


class _Job:
    """Windows-Job-Objekt je Kindprozess.

    `python.exe` einer venv ist nur ein Starter, der echte Interpreter läuft als dessen Kind. TerminateProcess träfe
    nur den Starter. Über den Job endet der ganze Baum, auch wenn das Startfenster selbst abstürzt.
    """

    def __init__(self, prozess: subprocess.Popen) -> None:
        handle = _kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        grenzen = _ExtendedLimits()
        grenzen.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
        if not _kernel32.SetInformationJobObject(
            handle, _JOB_EXTENDED_LIMITS, ctypes.byref(grenzen), ctypes.sizeof(grenzen)
        ) or not _kernel32.AssignProcessToJobObject(handle, int(prozess._handle)):
            fehler = ctypes.WinError(ctypes.get_last_error())
            _kernel32.CloseHandle(handle)
            raise fehler
        self._handle = handle

    def beende(self) -> None:
        _kernel32.TerminateJobObject(self._handle, 1)

    def schliesse(self) -> None:
        if self._handle:
            _kernel32.CloseHandle(self._handle)
            self._handle = None


def standby_verhindern() -> None:
    """Muss aus dem Tk-Hauptthread kommen: Der Zustand gilt pro Thread und endet mit ihm."""
    if WINDOWS:
        _kernel32.SetThreadExecutionState(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)


def standby_erlauben() -> None:
    if WINDOWS:
        _kernel32.SetThreadExecutionState(_ES_CONTINUOUS)


class StarterSperre:
    """Nur ein Startfenster je Rechner. Die Sperre gehört dem Betriebssystem und endet auch bei einem Absturz."""

    def __init__(self, data_dir: Path) -> None:
        self._pfad = data_dir / "starter.lock"
        self._datei = None

    def erwerben(self) -> bool:
        self._pfad.parent.mkdir(parents=True, exist_ok=True)
        datei = self._pfad.open("a+b")
        try:
            if WINDOWS:
                datei.seek(0)
                msvcrt.locking(datei.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(datei.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            datei.close()
            return False
        self._datei = datei
        return True

    def freigeben(self) -> None:
        if self._datei is not None:
            self._datei.close()  # gibt die Sperre auf beiden Plattformen frei
            self._datei = None


@dataclass(frozen=True)
class Befehl:
    name: str
    kommando: list[str]
    umgebung: dict[str, str]
    cwd: Path


class Kind:
    def __init__(self, befehl: Befehl, log_dir: Path) -> None:
        self.befehl = befehl
        self.logdatei = log_dir / f"{befehl.name}.log"
        self._prozess: subprocess.Popen | None = None
        self._job: _Job | None = None

    @property
    def laeuft(self) -> bool:
        return self._prozess is not None and self._prozess.poll() is None

    @property
    def exitcode(self) -> int | None:
        return self._prozess.poll() if self._prozess is not None else None

    def starte(self) -> None:
        self._schliesse_job()
        self.logdatei.parent.mkdir(parents=True, exist_ok=True)
        with self.logdatei.open("ab") as ausgabe:
            ausgabe.write(f"\n--- Start {datetime.now():%Y-%m-%d %H:%M:%S} ---\n".encode())
            ausgabe.flush()
            self._prozess = subprocess.Popen(
                self.befehl.kommando,
                cwd=self.befehl.cwd,
                env=self.befehl.umgebung,
                stdin=subprocess.DEVNULL,
                stdout=ausgabe,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if WINDOWS else 0,
            )
        if WINDOWS:
            try:
                self._job = _Job(self._prozess)
            except OSError:
                log.exception("Job-Objekt für %s nicht angelegt", self.befehl.name)

    def stoppe(self, frist: float = 10) -> None:
        if self._prozess is None:
            return
        if self._prozess.poll() is None:
            if self._job is not None:
                self._job.beende()
            else:
                self._prozess.terminate()
            try:
                self._prozess.wait(frist)
            except subprocess.TimeoutExpired:
                self._prozess.kill()
                self._prozess.wait(frist)
        self._schliesse_job()

    def _schliesse_job(self) -> None:
        if self._job is not None:
            self._job.schliesse()
            self._job = None


class Dienste:
    def __init__(self, server: Befehl, caddy: Befehl | None, log_dir: Path, host: str = "localhost") -> None:
        self.server = Kind(server, log_dir)
        self.caddy = Kind(caddy, log_dir) if caddy is not None else None
        self.host = host
        self.caddy_fehler: str | None = None if caddy is not None else "Caddy nicht gefunden"

    @property
    def adresse(self) -> str:
        # Der Server lauscht nur auf Loopback. Ohne Caddy ist er nur am ELW-Rechner direkt erreichbar.
        return f"https://{self.host}/" if self.caddy is not None and self.caddy.laeuft else LOKALE_ADRESSE

    @property
    def abgestuerzt(self) -> bool:
        return not self.server.laeuft or (self.caddy is not None and not self.caddy.laeuft)

    def _starte_caddy(self) -> None:
        if self.caddy is None:
            return
        try:
            self.caddy.starte()
            self.caddy_fehler = None
        except OSError as exc:
            # Der Server soll auch ohne Caddy laufen, am ELW-Rechner ist er weiter erreichbar.
            log.exception("Caddy konnte nicht gestartet werden")
            self.caddy_fehler = f"Caddy konnte nicht gestartet werden: {exc}"

    def starten(self) -> None:
        self.server.starte()
        self._starte_caddy()

    def neu_starten(self) -> None:
        if not self.server.laeuft:
            self.server.starte()
        if self.caddy is not None and not self.caddy.laeuft:
            self._starte_caddy()

    def stoppen(self, frist: float = 10) -> None:
        # Caddy zuerst, damit während des Herunterfahrens keine neuen Anfragen mehr ankommen.
        if self.caddy is not None:
            self.caddy.stoppe(frist)
        self.server.stoppe(frist)


def python_fuer_kindprozess() -> str:
    """Das Startfenster läuft unter pythonw.exe. Dessen fehlende Standardausgabe taugt nicht für den Server."""
    pfad = Path(sys.executable)
    return str(pfad.with_name("python.exe")) if pfad.name.lower() == "pythonw.exe" else str(pfad)


def server_umgebung(data_dir: Path, auftrag: Startauftrag, basis: dict[str, str] | None = None) -> dict[str, str]:
    umgebung = dict(os.environ if basis is None else basis)
    umgebung.update({
        "MELDI_EINSATZ_KENNUNG": auftrag.kennung,
        "MELDI_EINSATZ_BEZEICHNUNG": auftrag.bezeichnung,
        "MELDI_ABLAGE_DIR": str(auftrag.ordner),
        "MELDI_STT_MODEL_DIR": str(data_dir / "models"),
        "MELDI_STT_LOCAL_FILES_ONLY": "true",
        "HF_HUB_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        # Das Log soll auch kurz vor einem Absturz vollständig und unabhängig von der Windows-Codepage sein.
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    umgebung.pop("MELDI_ABLAGE_NEU_AUFBAUEN", None)
    if auftrag.neu_aufbauen:
        umgebung["MELDI_ABLAGE_NEU_AUFBAUEN"] = "true"
    return umgebung


def server_kommando() -> list[str]:
    return [
        python_fuer_kindprozess(), "-m", "uvicorn", "--factory", "app.main:create_app",
        "--host", "127.0.0.1", "--port", "8000",
    ]


def caddy_kommando() -> list[str] | None:
    gebuendelt = PROJECT_DIR / "deploy" / "bin" / "caddy.exe"
    gefunden = str(gebuendelt) if gebuendelt.is_file() else shutil.which("caddy")
    if gefunden is None:
        return None
    return [gefunden, "run", "--config", str(PROJECT_DIR / "deploy" / "Caddyfile")]


def meldi_host(umgebung: dict[str, str] | None = None) -> str:
    """MELDI_HOST oder die erste eigene Adresse. Fragt nur den lokalen Namensdienst, nichts nach außen."""
    gesetzt = (os.environ if umgebung is None else umgebung).get("MELDI_HOST", "").strip()
    if gesetzt:
        return gesetzt
    try:
        adressen = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        return "localhost"
    for adresse in adressen:
        if not adresse.startswith(("127.", "169.254.")):
            return adresse
    return "localhost"


def dienste_fuer(data_dir: Path, auftrag: Startauftrag) -> Dienste:
    host = meldi_host()
    server = Befehl("server", server_kommando(), server_umgebung(data_dir, auftrag), BACKEND_DIR)
    kommando = caddy_kommando()
    caddy = Befehl("caddy", kommando, {**os.environ, "MELDI_HOST": host}, PROJECT_DIR) if kommando else None
    return Dienste(server, caddy, data_dir / "logs", host)


def health(url: str = HEALTH_URL, timeout: float = 1.5) -> dict | None:
    """Antwort des Servers oder None, solange er nicht erreichbar ist."""
    try:
        with _OHNE_PROXY.open(url, timeout=timeout) as antwort:
            daten = json.loads(antwort.read())
    except (OSError, ValueError):  # URLError ist ein OSError
        return None
    return daten if isinstance(daten, dict) else None
