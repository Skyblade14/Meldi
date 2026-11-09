import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { api, ApiError, sitzungBeendet } from "./api";
import type { Nachricht } from "./types";
import { useLiveFeed } from "./useLiveFeed";

vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  api: { me: vi.fn() },
  sitzungBeendet: vi.fn(),
}));

class FakeWebSocket {
  static OPEN = 1;
  static alle: FakeWebSocket[] = [];
  readyState = 0;
  onopen?: () => void;
  onclose?: () => void;
  onmessage?: (e: { data: string }) => void;
  send = vi.fn();
  close = vi.fn(() => this.onclose?.());

  constructor(public url: string) {
    FakeWebSocket.alle.push(this);
  }

  oeffne() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }
}

const anzahl = () => FakeWebSocket.alle.length;
const letzte = () => FakeWebSocket.alle[anzahl() - 1];

function feed(rollen: ("elw" | "beobachter")[] = ["elw"]) {
  const onNachricht = vi.fn();
  const onVerbunden = vi.fn();
  let ergebnis!: ReturnType<typeof useLiveFeed>;
  const wrapper = mount(
    defineComponent({
      setup() {
        ergebnis = useLiveFeed(onNachricht, onVerbunden, rollen);
        return () => h("div");
      },
    }),
  );
  return { ...ergebnis, onNachricht, onVerbunden, wrapper };
}

/** Lässt die Backoff-Wartezeit und das anschließende `await api.me()` ablaufen. */
const warte = (ms: number) => vi.advanceTimersByTimeAsync(ms);

beforeEach(() => {
  vi.useFakeTimers();
  FakeWebSocket.alle = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
  vi.mocked(api.me).mockReset().mockResolvedValue({ name: "A", rolle: "elw", funktion: "ELW", einsatz: "E" });
  vi.mocked(sitzungBeendet).mockReset();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Verbindung", () => {
  it("verbindet sich und meldet „live“", () => {
    const f = feed();
    expect(f.verbindung.value).toBe("verbinde");
    letzte().oeffne();
    expect(f.verbindung.value).toBe("live");
    expect(f.onVerbunden).toHaveBeenCalledOnce();
  });

  it("leitet neue und geänderte Nachrichten weiter und ignoriert Unbekanntes", () => {
    const f = feed();
    letzte().oeffne();
    const n = { id: 1 } as Nachricht;
    letzte().onmessage?.({ data: JSON.stringify({ type: "nachricht.neu", nachricht: n }) });
    letzte().onmessage?.({ data: JSON.stringify({ type: "nachricht.geaendert", nachricht: n }) });
    letzte().onmessage?.({ data: JSON.stringify({ type: "etwas.anderes" }) });
    expect(f.onNachricht.mock.calls).toEqual([
      [n, "neu"],
      [n, "geaendert"],
    ]);
  });

  it("schickt regelmäßig einen Ping", async () => {
    feed();
    letzte().oeffne();
    await warte(20_000);
    expect(letzte().send).toHaveBeenCalledWith("ping");
  });

  it("zeigt „getrennt“ beim Verbindungsverlust", () => {
    const f = feed();
    letzte().oeffne();
    letzte().onclose?.();
    expect(f.verbindung.value).toBe("getrennt");
  });
});

describe("Wiederverbinden", () => {
  it("verdoppelt die Wartezeit bis höchstens 10 s", async () => {
    feed();
    for (const [i, ms] of [1000, 2000, 4000, 8000, 10_000, 10_000].entries()) {
      letzte().onclose?.();
      await warte(ms - 1);
      expect(anzahl(), `Versuch ${i}: noch nicht`).toBe(i + 1);
      await warte(1);
      expect(anzahl(), `Versuch ${i}: jetzt`).toBe(i + 2);
    }
  });

  it("beginnt nach erfolgreicher Verbindung wieder von vorn", async () => {
    feed();
    letzte().onclose?.();
    await warte(1000);
    letzte().onclose?.();
    await warte(2000);
    letzte().oeffne();
    letzte().onclose?.();
    await warte(1000);
    expect(anzahl()).toBe(4);
  });

  it("holt nach dem Wiederverbinden Verpasstes nach", async () => {
    const f = feed();
    letzte().oeffne();
    letzte().onclose?.();
    await warte(1000);
    letzte().oeffne();
    expect(f.onVerbunden).toHaveBeenCalledTimes(2);
  });

  it("versucht es bei Netzfehlern weiter", async () => {
    vi.mocked(api.me).mockRejectedValue(new ApiError(0, "Keine Verbindung"));
    feed();
    letzte().onclose?.();
    await warte(1000);
    expect(anzahl()).toBe(2);
  });

  it("versucht es weiter, wenn Caddy den Server noch nicht erreicht", async () => {
    vi.mocked(api.me).mockRejectedValue(new ApiError(502, "Bad Gateway"));
    feed();
    letzte().onclose?.();
    await warte(1000);
    expect(anzahl()).toBe(2);
  });
});

describe("Ende der Sitzung", () => {
  it("verbindet nach 401 nicht mehr neu", async () => {
    vi.mocked(api.me).mockRejectedValue(new ApiError(401, "Nicht angemeldet"));
    feed();
    letzte().onclose?.();
    await warte(60_000);
    expect(anzahl()).toBe(1);
  });

  it("beendet die Ansicht, wenn die Anmeldung inzwischen eine andere Rolle hat", async () => {
    vi.mocked(api.me).mockResolvedValue({ name: "A", rolle: "melder", funktion: "EA", einsatz: "E" });
    feed(["elw", "beobachter"]);
    letzte().onclose?.();
    await warte(60_000);
    expect(sitzungBeendet).toHaveBeenCalledOnce();
    expect(anzahl()).toBe(1);
  });

  it("räumt beim Verlassen der Ansicht auf", async () => {
    const f = feed();
    letzte().oeffne();
    f.wrapper.unmount();
    expect(letzte().close).toHaveBeenCalled();
    await warte(60_000);
    expect(anzahl()).toBe(1);
    expect(letzte().send).not.toHaveBeenCalled();
  });

  it("bricht ein geplantes Wiederverbinden beim Verlassen ab", async () => {
    const f = feed();
    letzte().onclose?.();
    f.trennen();
    await warte(60_000);
    expect(anzahl()).toBe(1);
  });
});
