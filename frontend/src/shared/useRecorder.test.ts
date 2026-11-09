import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { mikrofonVerfuegbar, type RecorderOptions, useRecorder } from "./useRecorder";

const LEISE = 0.001;
const LAUT = 0.2;

let pegel = LEISE;
let unterstuetzt: string[] = [];
let recorder: FakeRecorder;
const track = { stop: vi.fn(), getSettings: () => ({ echoCancellation: false, sampleRate: 48000 }) };
const stream = { getTracks: () => [track], getAudioTracks: () => [track] };
const getUserMedia = vi.fn();

class FakeRecorder {
  static isTypeSupported = (m: string) => unterstuetzt.includes(m);
  state = "inactive";
  mimeType: string;
  ondataavailable?: (e: { data: Blob }) => void;
  onstop?: () => void;

  constructor(
    public stream: unknown,
    public optionen: MediaRecorderOptions,
  ) {
    this.mimeType = optionen.mimeType ?? "";
    recorder = this;
  }

  start() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["audio"]) });
    this.onstop?.();
  }
}

class FakeAudioContext {
  close = vi.fn();
  createMediaStreamSource = () => ({ connect() {} });
  createAnalyser = () => ({ fftSize: 1024, getFloatTimeDomainData: (b: Float32Array) => b.fill(pegel) });
}

function rec(opts?: RecorderOptions) {
  let r!: ReturnType<typeof useRecorder>;
  const wrapper = mount(
    defineComponent({
      setup() {
        r = useRecorder(opts);
        return () => h("div");
      },
    }),
  );
  return { r, wrapper };
}

/** Macht aus dem Rückgabewert prüfbaren Zustand, ohne auf ein nie erfülltes Promise zu warten. */
function beobachte(fertig: Promise<Blob | null>) {
  const zustand: { fertig: boolean; audio?: Blob | null } = { fertig: false };
  void fertig.then((audio) => Object.assign(zustand, { fertig: true, audio }));
  return zustand;
}

const warte = (ms: number) => vi.advanceTimersByTimeAsync(ms);

beforeEach(() => {
  vi.useFakeTimers();
  pegel = LEISE;
  unterstuetzt = ["audio/webm;codecs=opus"];
  track.stop.mockClear();
  getUserMedia.mockReset().mockResolvedValue(stream);
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  vi.stubGlobal("AudioContext", FakeAudioContext);
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
  vi.stubGlobal("isSecureContext", true);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Aufnahme", () => {
  it("nimmt roh auf, ohne Echounterdrückung", async () => {
    await rec().r.start();
    expect(getUserMedia.mock.calls[0][0].audio).toMatchObject({
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
    });
  });

  it("liefert nach stop() das Audio und gibt das Mikrofon frei", async () => {
    const { r } = rec();
    const { fertig } = await r.start();
    expect(r.state.value).toBe("recording");
    r.stop();
    expect((await fertig)?.size).toBeGreaterThan(0);
    expect(r.state.value).toBe("idle");
    expect(track.stop).toHaveBeenCalled();
  });

  it("zählt die Sekunden mit", async () => {
    const { r } = rec();
    await r.start();
    await warte(1400);
    expect(r.sekunden.value).toBeCloseTo(1.4, 1);
  });

  it("setzt die Pegelanzeige und nach dem Ende auf null zurück", async () => {
    const { r } = rec();
    await r.start();
    pegel = LAUT;
    await warte(100);
    expect(r.pegel.value).toBeGreaterThan(0.5);
    r.stop();
    expect(r.pegel.value).toBe(0);
  });
});

describe("Audioformat", () => {
  it.each([
    [["audio/webm;codecs=opus", "audio/mp4"], "audio/webm;codecs=opus"],
    [["audio/mp4"], "audio/mp4"], // iOS kann kein WebM
    [["audio/ogg;codecs=opus"], "audio/ogg;codecs=opus"],
  ])("wählt aus %j: %s", async (formate, erwartet) => {
    unterstuetzt = formate;
    const { r } = rec();
    const { fertig } = await r.start();
    expect(recorder.optionen.mimeType).toBe(erwartet);
    r.stop();
    expect((await fertig)?.type).toBe(erwartet);
  });

  it("überlässt die Wahl dem Browser, wenn kein Kandidat passt", async () => {
    unterstuetzt = [];
    await rec().r.start();
    expect(recorder.optionen.mimeType).toBeUndefined();
  });

  it("zeichnet mit 64 kbit/s auf, darunter beschneidet Opus die Bandbreite", async () => {
    await rec().r.start();
    expect(recorder.optionen.audioBitsPerSecond).toBe(64_000);
  });
});

describe("Stille-Stopp", () => {
  it("stoppt nach 2,5 s Stille, wenn gesprochen wurde", async () => {
    const { r } = rec();
    const z = beobachte((await r.start()).fertig);
    await warte(200);
    pegel = LAUT;
    await warte(500);
    pegel = LEISE;
    await warte(2400);
    expect(z.fertig).toBe(false);
    await warte(300);
    expect(z.fertig).toBe(true);
    expect(z.audio).toBeInstanceOf(Blob);
  });

  it("stoppt nicht, solange nicht gesprochen wurde", async () => {
    const { r } = rec();
    await r.start();
    await warte(20_000);
    expect(r.state.value).toBe("recording");
  });

  it("gleichmäßiger Lärm zählt nicht als Sprache", async () => {
    const { r } = rec();
    pegel = 0.05;
    await r.start();
    await warte(20_000);
    expect(r.state.value).toBe("recording");
  });

  it("stilleStoppMs 0 schaltet den Stopp ab", async () => {
    const { r } = rec({ stilleStoppMs: 0 });
    await r.start();
    await warte(200);
    pegel = LAUT;
    await warte(200);
    pegel = LEISE;
    await warte(20_000);
    expect(r.state.value).toBe("recording");
  });

  it("Sprechpausen unter 2,5 s beenden die Aufnahme nicht", async () => {
    const { r } = rec();
    await r.start();
    await warte(200);
    for (let i = 0; i < 3; i++) {
      pegel = LAUT;
      await warte(300);
      pegel = LEISE;
      await warte(2000);
    }
    expect(r.state.value).toBe("recording");
  });
});

describe("Maximaldauer", () => {
  it("stoppt auch bei durchgehendem Sprechen", async () => {
    const { r } = rec({ maxSekunden: 3 });
    const z = beobachte((await r.start()).fertig);
    pegel = LAUT;
    await warte(2900);
    expect(z.fertig).toBe(false);
    await warte(400);
    expect(z.fertig).toBe(true);
    expect(z.audio).toBeInstanceOf(Blob);
  });
});

describe("Abbruch", () => {
  it("verwirft die Aufnahme und gibt das Mikrofon frei", async () => {
    const { r } = rec();
    const z = beobachte((await r.start()).fertig);
    r.abbrechen();
    await warte(0);
    expect(z).toEqual({ fertig: true, audio: null });
    expect(track.stop).toHaveBeenCalled();
    expect(r.state.value).toBe("idle");
  });

  it("beim Verlassen der Ansicht", async () => {
    const { r, wrapper } = rec();
    const z = beobachte((await r.start()).fertig);
    wrapper.unmount();
    await warte(0);
    expect(z).toEqual({ fertig: true, audio: null });
    expect(track.stop).toHaveBeenCalled();
    await warte(5000);
    expect(r.sekunden.value).toBeLessThan(1); // Timer läuft nicht weiter
  });

  it("fehlende Erlaubnis kommt beim Aufrufer an", async () => {
    getUserMedia.mockRejectedValue(new DOMException("nein", "NotAllowedError"));
    await expect(rec().r.start()).rejects.toMatchObject({ name: "NotAllowedError" });
  });
});

describe("Verfügbarkeit", () => {
  it("meldet keinen Hinderungsgrund", () => {
    expect(mikrofonVerfuegbar()).toBeNull();
  });

  it("verlangt HTTPS", () => {
    vi.stubGlobal("isSecureContext", false);
    expect(mikrofonVerfuegbar()).toContain("HTTPS");
  });

  it("erkennt fehlende getUserMedia", () => {
    vi.stubGlobal("navigator", {});
    expect(mikrofonVerfuegbar()).toContain("unterstützt");
  });

  it("erkennt fehlenden MediaRecorder", () => {
    vi.stubGlobal("MediaRecorder", undefined);
    expect(mikrofonVerfuegbar()).toContain("unterstützt");
  });
});
