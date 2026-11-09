"""UI-Tests: echter uvicorn im selben Prozess, echter Browser, FakeSTT statt Whisper.

Jeder Test bekommt über `db_url` eine eigene Datenbank und Ablage. Datenbank, Audit und Ablage-Dateien prüft der Test
direkt, Test-Endpunkte in der App sind dadurch nicht nötig.
"""

import math
import re
import socket
import struct
import threading
import time
import wave
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
import uvicorn
from PIL import ExifTags, Image
from playwright.sync_api import BrowserContext, ConsoleMessage, Locator, Page, expect

from app.config import PROJECT_DIR
from app.db import new_session, utcnow
from app.main import create_app
from app.models import Anmeldung, Rolle
from app.schemas.message import NachrichtCreate
from app.services import auth_service, message_service

expect.set_options(timeout=7_000)

PIXEL = "Pixel 7"
IPHONE = "iPhone 15"
DESKTOP = {"viewport": {"width": 1400, "height": 900}}


# --- Server ---


class LiveServer:
    """uvicorn im Hintergrund. Lässt sich anhalten und auf demselben Port neu starten."""

    def __init__(self, app_factory: Callable) -> None:
        self._app_factory = app_factory
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        config = uvicorn.Config(
            self._app_factory(), host="127.0.0.1", port=self.port, log_level="warning", timeout_graceful_shutdown=1
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        ende = time.monotonic() + 10
        while not self._server.started:
            if time.monotonic() > ende or not self._thread.is_alive():
                raise RuntimeError("Testserver ist nicht gestartet")
            time.sleep(0.01)

    def stop(self) -> None:
        assert self._server and self._thread
        self._server.should_exit = True
        self._thread.join(timeout=10)


@pytest.fixture(scope="session")
def frontend_aktuell() -> None:
    """Sonst prüfen die Tests unbemerkt einen alten Stand."""
    frontend = PROJECT_DIR / "frontend"
    build = frontend / "dist" / "index.html"
    if not build.is_file():
        pytest.exit("frontend/dist fehlt. Bitte zuerst bauen: cd frontend && npm run build", returncode=2)
    quellen = [p for p in (frontend / "src").rglob("*") if p.is_file() and not p.name.endswith(".test.ts")]
    if max(p.stat().st_mtime for p in quellen) > build.stat().st_mtime:
        pytest.exit("frontend/dist ist älter als frontend/src. Bitte neu bauen: cd frontend && npm run build", returncode=2)


@pytest.fixture
def server(db_url, stt, frontend_aktuell):
    s = LiveServer(lambda: create_app(stt=stt, migrate=False))
    s.start()
    yield s
    stt.freigeben()  # eine hängende Erkennung darf das Herunterfahren nicht aufhalten
    s.stop()


# --- Browser ---


@pytest.fixture(scope="session")
def fake_mikrofon(tmp_path_factory) -> Path:
    """Synthetisch: 1,5 s Ton, dann Stille. Echte Aufnahmen aus data/ werden hier nie verwendet."""
    pfad = tmp_path_factory.mktemp("mikrofon") / "sprache.wav"
    rate = 16_000
    ton = [int(14_000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(int(rate * 1.5))]
    stille = [0] * int(rate * 5)
    with wave.open(str(pfad), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(ton) + len(stille)}h", *ton, *stille))
    return pfad


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args, fake_mikrofon, browser_name):
    if browser_name != "chromium":
        return browser_type_launch_args
    return {
        **browser_type_launch_args,
        "args": [
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-audio-capture={fake_mikrofon}",
        ],
    }


WAECHTER_JS = """
(() => {
  const melde = (text) => window.__meldiVerstoss(text);
  document.addEventListener("securitypolicyviolation", (e) =>
    melde(`CSP-Verletzung: ${e.violatedDirective} ${e.blockedURI} (${e.sourceFile}:${e.lineNumber})`));
  for (const name of ["SpeechRecognition", "webkitSpeechRecognition"]) {
    Object.defineProperty(window, name, {
      configurable: true,
      get() { melde(`${name} verwendet`); return undefined; },
    });
  }
})();
"""

SPEICHER_JS = """
async () => ({
  localStorage: localStorage.length,
  sessionStorage: sessionStorage.length,
  indexedDB: (await indexedDB.databases()).length,
  caches: (await caches.keys()).length,
  serviceWorker: (await navigator.serviceWorker.getRegistrations()).length,
})
"""

HANDY_JS = """
() => {
  const sichtbar = (el) => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
  };
  const name = (el) => `${el.tagName} "${(el.innerText || el.getAttribute("aria-label") || el.placeholder || "").trim().slice(0, 30)}"`;
  const zuKlein = [...document.querySelectorAll("a, button, input, select, textarea, summary")]
    .filter((el) => sichtbar(el) && !el.disabled)
    .filter((el) => { const r = el.getBoundingClientRect(); return r.height < 43.5 || r.width < 43.5; })
    .map((el) => { const r = el.getBoundingClientRect(); return `${name(el)} ${Math.round(r.width)}x${Math.round(r.height)}`; });
  const schriftZuKlein = [...document.querySelectorAll("input, textarea, select")]
    .filter((el) => sichtbar(el) && parseFloat(getComputedStyle(el).fontSize) < 16)
    .map(name);
  const d = document.documentElement;
  return { zuKlein, schriftZuKlein, scrollBreite: d.scrollWidth, breite: d.clientWidth };
}
"""


class Waechter:
    """Sichert in jedem UI-Test die Datenschutz- und Bedienregeln aus CLAUDE.md ab."""

    def __init__(self, server: LiveServer, tracing: bool = False) -> None:
        self._netloc = urlsplit(server.url).netloc
        self.verstoesse: list[str] = []
        self.handy_kontexte: list[BrowserContext] = []
        self.kontexte: list[BrowserContext] = []
        # Vor der Anmeldung antwortet /api/auth/me erwartungsgemäß mit 401.
        self._erlaubt = [re.compile(r"status of 401 .*/api/auth/me")]
        if tracing:
            # Nur Playwrights Trace-Aufzeichnung holt sich Blob-Bilder per fetch, die App nicht. Ohne Tracing bleibt es verboten.
            self.erlaube(r"Connecting to 'blob:|CSP-Verletzung: connect-src blob")

    def erlaube(self, muster: str) -> None:
        """Erwarteter Konsolenfehler in diesem Test. Geprüft wird gegen `Text @ URL`."""
        self._erlaubt.append(re.compile(muster))

    def _pruefe_url(self, url: str) -> None:
        teile = urlsplit(url)
        if teile.scheme not in ("data", "blob") and teile.netloc != self._netloc:
            self.verstoesse.append(f"Externer Zugriff: {url}")

    def _melde(self, text: str) -> None:
        if not any(m.search(text) for m in self._erlaubt):
            self.verstoesse.append(text)

    def _konsole(self, msg: ConsoleMessage) -> None:
        if msg.type == "error":
            self._melde(f"Konsolenfehler: {msg.text} @ {msg.location.get('url', '')}")

    def _seite(self, page: Page) -> None:
        page.on("console", self._konsole)
        page.on("pageerror", lambda e: self.verstoesse.append(f"Unbehandelter Fehler: {e}"))
        page.on("websocket", lambda ws: self._pruefe_url(ws.url.replace("ws://", "http://", 1).replace("wss://", "https://", 1)))

    def beobachte(self, context: BrowserContext, handy: bool) -> None:
        self.kontexte.append(context)
        if handy:
            self.handy_kontexte.append(context)
        context.expose_function("__meldiVerstoss", lambda text: self._melde(text))
        context.add_init_script(WAECHTER_JS)
        context.on("request", lambda r: self._pruefe_url(r.url))
        context.on("page", self._seite)

    def pruefe_handy(self, page: Page) -> None:
        """Auch zwischendurch aufrufbar, etwa wenn ein Zustand am Testende nicht mehr sichtbar ist."""
        m = page.evaluate(HANDY_JS)
        wo = urlsplit(page.url).path
        if m["scrollBreite"] > m["breite"]:
            self.verstoesse.append(f"{wo}: horizontale Scrollleiste ({m['scrollBreite']} > {m['breite']})")
        self.verstoesse += [f"{wo}: Touch-Ziel zu klein: {x}" for x in m["zuKlein"]]
        self.verstoesse += [f"{wo}: Schrift unter 16 px (iOS zoomt): {x}" for x in m["schriftZuKlein"]]

    def abschluss(self) -> None:
        for context in self.kontexte:
            for page in context.pages:
                if urlsplit(page.url).netloc != self._netloc:
                    continue
                speicher = {k: v for k, v in page.evaluate(SPEICHER_JS).items() if v}
                if speicher:
                    self.verstoesse.append(f"Daten im Browser hinterlassen: {speicher}")
                if context in self.handy_kontexte:
                    self.pruefe_handy(page)
        assert not self.verstoesse, "Wächter:\n" + "\n".join(dict.fromkeys(self.verstoesse))


@pytest.fixture
def waechter(server, new_context, pytestconfig):  # new_context zuletzt abbauen, der Wächter braucht noch offene Seiten
    w = Waechter(server, tracing=pytestconfig.getoption("--tracing") != "off")
    yield w
    w.abschluss()


@pytest.fixture
def desktop(server, new_context, waechter) -> Callable[[], Page]:
    """Neuer Browser-Kontext mit eigener Sitzung in Desktop-Größe."""

    def oeffnen() -> Page:
        context = new_context(base_url=server.url, **DESKTOP)
        waechter.beobachte(context, handy=False)
        return context.new_page()

    return oeffnen


@pytest.fixture
def handy(server, new_context, waechter, playwright) -> Callable[..., Page]:
    """Neuer Browser-Kontext mit eigener Sitzung als Pixel-Handy."""

    def oeffnen(init_script: str | None = None) -> Page:
        context = new_context(base_url=server.url, **playwright.devices[PIXEL])
        waechter.beobachte(context, handy=True)
        if init_script:
            context.add_init_script(init_script)
        return context.new_page()

    return oeffnen


# --- Bedienung ---


def anmelden(page: Page, ansicht: str, name: str, funktion: str | None = None) -> None:
    page.goto(f"/{ansicht}/")
    page.get_by_label("Name").fill(name)
    if funktion is not None:
        page.get_by_label("Funktion").fill(funktion)
    page.get_by_role("button", name="Anmelden", exact=True).click()
    expect(page.get_by_role("button", name="Abmelden")).to_be_visible()


@pytest.fixture
def elw_seite(desktop) -> Page:
    page = desktop()
    anmelden(page, "elw", "Erika ELW")
    expect(page.get_by_test_id("verbindung")).to_have_text("● live")
    return page


@pytest.fixture
def melder_seite(handy) -> Page:
    page = handy()
    anmelden(page, "melder", "Max Melder", "EA Brand")
    return page


@pytest.fixture
def beobachter_seite(handy) -> Page:
    page = handy()
    anmelden(page, "beobachter", "Bea Beobachter")
    expect(page.get_by_test_id("verbindung")).to_have_text("● live")
    return page


def warte_bis(page: Page, bedingung: Callable[[], object], sekunden: float = 7) -> None:
    """Für Zustände auf der Python-Seite (etwa angehaltene Routen). Auf dem Bildschirm wartet `expect`."""
    ende = time.monotonic() + sekunden
    while not bedingung():
        assert time.monotonic() < ende, "Bedingung nicht eingetreten"
        page.wait_for_timeout(20)  # lässt Playwright die Ereignisse verarbeiten


def filter_auswahl(page: Page, name: str) -> Locator:
    """`get_by_label` scheitert hier: Der Text der Optionen zählt zum Label."""
    return page.locator("label").filter(has_text=re.compile(rf"^\s*{name}\b")).locator("select")


def sende_text(page: Page, an: str, inhalt: str) -> None:
    page.get_by_label("An", exact=True).fill(an)
    page.get_by_label("Inhalt", exact=True).fill(inhalt)
    page.get_by_role("button", name="Absenden").click()
    expect(page.get_by_role("status")).to_contain_text("übermittelt")


def spreche(page: Page, knopf: str) -> None:
    """Startet die Aufnahme und beendet sie, sobald mindestens ein Stück Audio vorliegt."""
    page.get_by_role("button", name=knopf).click()
    stopp = page.get_by_role("button", name="Aufnahme beenden")
    expect(stopp).to_contain_text("Stopp")
    page.wait_for_function("() => document.querySelector('.pegel')?.style.transform !== 'scaleX(0)'")
    stopp.click()


def beende_sitzungen() -> None:
    """Wie abgemeldet im Hintergrund: Der Browser behält sein Cookie, der Server kennt die Anmeldung nicht mehr."""
    with new_session() as db:
        for a in db.query(Anmeldung).all():
            a.gueltig_bis = utcnow() - timedelta(minutes=1)
        db.commit()


def erzeuge_nachrichten(*inhalte: str, an: str = "Einsatzleitung", funktion: str = "EA Brand") -> list[int]:
    """Direkt in der Datenbank, also ohne Live-Ereignis. Auch bei angehaltenem Server möglich."""
    with new_session() as db:
        anmeldung, _ = auth_service.login(db, f"Hintergrund {funktion}", funktion, Rolle.MELDER, 24)
        return [
            message_service.create_nachricht(db, anmeldung, NachrichtCreate(an=an, inhalt=i)).nachricht.id for i in inhalte
        ]


class ApiMelder:
    """Weiterer Melder über die echte HTTP-API. Seine Nachrichten lösen Live-Ereignisse aus."""

    def __init__(self, server: LiveServer, name: str = "Api Melder", funktion: str = "EA Wasserversorgung") -> None:
        self._client = httpx.Client(base_url=server.url)
        r = self._client.post("/api/auth/login", json={"name": name, "rolle": "melder", "funktion": funktion})
        r.raise_for_status()

    def sende(self, inhalt: str, an: str = "Einsatzleitung") -> dict:
        r = self._client.post("/api/messages", json={"an": an, "inhalt": inhalt})
        r.raise_for_status()
        return r.json()


@pytest.fixture
def api_melder(server) -> ApiMelder:
    return ApiMelder(server)


def jpeg(pfad: Path, breite: int = 800, hoehe: int = 600, *, gps: bool = False, orientierung: int | None = None) -> Path:
    exif = Image.Exif()
    if orientierung:
        exif[ExifTags.Base.Orientation] = orientierung
    if gps:
        ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
        ifd[ExifTags.GPS.GPSLatitudeRef] = "N"
        ifd[ExifTags.GPS.GPSLatitude] = (52.0, 31.0, 12.0)
        ifd[ExifTags.GPS.GPSLongitudeRef] = "E"
        ifd[ExifTags.GPS.GPSLongitude] = (13.0, 24.0, 18.0)
    Image.new("RGB", (breite, hoehe), "orange").save(pfad, "JPEG", exif=exif)
    return pfad
