"""Smoke-Test mit WebKit-Engine und iPhone-Maßen. Ersetzt kein echtes iPhone, findet aber grobe Safari-Fehler.

Unter Linux braucht WebKit Systembibliotheken: sudo .venv/bin/playwright install-deps webkit
"""

import os

import pytest
from playwright.sync_api import Error, expect

from tests.ui.conftest import IPHONE, anmelden, sende_text

pytestmark = pytest.mark.ui


def _ohne_snap_umgebung() -> dict[str, str]:
    """VS Code als Snap vererbt seine Bibliothekspfade ans Terminal, daran scheitert der Netzwerkprozess von WebKit."""
    umgebung = dict(os.environ)
    for name, original in os.environ.items():
        if name.endswith("_VSCODE_SNAP_ORIG"):
            ziel = name.removesuffix("_VSCODE_SNAP_ORIG")
            if original:
                umgebung[ziel] = original
            else:
                umgebung.pop(ziel, None)
    return umgebung


@pytest.fixture(scope="module")
def webkit(playwright):
    try:
        browser = playwright.webkit.launch(env=_ohne_snap_umgebung())
    except Error as exc:
        if os.environ.get("CI"):
            raise  # In der CI ist WebKit installiert. Ein stilles Überspringen fiele dort niemandem auf.
        pytest.skip(f"WebKit nicht startbar: {exc.message.splitlines()[0]}")
    yield browser
    browser.close()


@pytest.fixture
def iphone(webkit, server, waechter, playwright):
    contexts = []

    def oeffnen():
        context = webkit.new_context(base_url=server.url, **playwright.devices[IPHONE])
        contexts.append(context)
        waechter.beobachte(context, handy=True)
        return context.new_page()

    yield oeffnen
    waechter.abschluss()
    waechter.kontexte.clear()
    for context in contexts:
        context.close()


def test_melden_und_live_mitlesen(iphone):
    """Prüft auch, dass der WebSocket unter der CSP in WebKit durchkommt."""
    beobachter = iphone()
    anmelden(beobachter, "beobachter", "Bea")
    expect(beobachter.get_by_test_id("verbindung")).to_have_text("● live")
    melder = iphone()
    anmelden(melder, "melder", "Max", "EA Brand")
    sende_text(melder, "ELW", "Hallo aus WebKit")
    expect(beobachter.get_by_test_id("nachricht-karte")).to_contain_text("Hallo aus WebKit")
