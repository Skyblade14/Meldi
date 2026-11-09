import { onBeforeUnmount, ref } from "vue";

/**
 * Push-to-Talk-Aufnahme über MediaRecorder. Das Audio verlässt das Handy nur Richtung ELW-Server –
 * bewusst KEINE Web Speech API, da Chrome/Safari das Audio dafür an Google/Apple senden.
 */

const MIME_KANDIDATEN = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

/**
 * „roh“ ist Standard: Auf Android schaltet echoCancellation das Mikrofon in den Telefonie-Modus, der oberhalb
 * von ~4 kHz abschneidet (Zischlaute fehlen, Whisper erkennt schlechter). Whisper kommt mit Lärm selbst zurecht.
 * Zum Vergleich in der Testphase: `?audio=verarbeitet` an die URL hängen.
 */
const AUFNAHME_PROFILE = {
  roh: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
  verarbeitet: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
} satisfies Record<string, MediaTrackConstraints>;
type AufnahmeProfil = keyof typeof AUFNAHME_PROFILE;

function aufnahmeProfil(): AufnahmeProfil {
  const wunsch = new URLSearchParams(location.search).get("audio");
  return wunsch === "verarbeitet" ? wunsch : "roh";
}

export interface RecorderOptions {
  maxSekunden?: number;
  /** Nach so viel Stille (nachdem gesprochen wurde) automatisch stoppen. 0 = aus. */
  stilleStoppMs?: number;
}

export type RecorderState = "idle" | "recording";

export function mikrofonVerfuegbar(): string | null {
  if (!window.isSecureContext) return "Mikrofon nur über HTTPS verfügbar";
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined")
    return "Dieser Browser unterstützt keine Audioaufnahme";
  return null;
}

export function useRecorder(opts: RecorderOptions = {}) {
  const maxSekunden = opts.maxSekunden ?? 60;
  const stilleStoppMs = opts.stilleStoppMs ?? 2500;

  const state = ref<RecorderState>("idle");
  const pegel = ref(0); // 0..1 für die Pegelanzeige
  const sekunden = ref(0);
  /** Profil + tatsächliche Spur-Einstellungen der letzten Aufnahme, für die Auswertung in der Testphase. */
  const spur = ref("");

  let stream: MediaStream | null = null;
  let recorder: MediaRecorder | null = null;
  let ctx: AudioContext | null = null;
  let raf = 0;
  let timer = 0;
  let resolveStop: ((b: Blob | null) => void) | null = null;

  /** Startet die Aufnahme. `fertig` liefert das Audio nach stop() (bzw. null bei Abbruch). */
  async function start(): Promise<{ fertig: Promise<Blob | null> }> {
    const profil = aufnahmeProfil();
    stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, ...AUFNAHME_PROFILE[profil] } });
    const { echoCancellation, noiseSuppression, autoGainControl, sampleRate } = stream.getAudioTracks()[0].getSettings();
    spur.value = JSON.stringify({ profil, echoCancellation, noiseSuppression, autoGainControl, sampleRate });
    const mimeType = MIME_KANDIDATEN.find((m) => MediaRecorder.isTypeSupported(m));
    // 64 kbit/s: bei 32 kbit/s beschneidet Opus die Bandbreite. 60 s ≈ 480 kB, für das WLAN kein Problem.
    recorder = new MediaRecorder(stream, { ...(mimeType ? { mimeType } : {}), audioBitsPerSecond: 64_000 });
    const chunks: Blob[] = [];
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    const fertig = new Promise<Blob | null>((resolve) => {
      resolveStop = resolve;
      recorder!.onstop = () => {
        aufraeumen();
        resolve(chunks.length ? new Blob(chunks, { type: recorder?.mimeType || mimeType || "audio/webm" }) : null);
      };
    });
    recorder.start(250);
    state.value = "recording";
    sekunden.value = 0;
    const startZeit = performance.now();
    timer = window.setInterval(() => {
      sekunden.value = (performance.now() - startZeit) / 1000;
      if (sekunden.value >= maxSekunden) stop();
    }, 200);
    pegelUeberwachen();
    return { fertig };
  }

  function pegelUeberwachen() {
    if (!stream) return;
    ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    let gesprochen = false;
    let stilleSeit = performance.now();
    // Sprache = deutlich (~10 dB) über dem Grundrauschen. Fester Schwellwert passt ohne AGC nicht für jedes
    // Handy, und bei Pumpenlärm würde nie gestoppt. Das Grundrauschen folgt Minima sofort, steigt nur langsam.
    let grundrauschen = Infinity;

    const tick = () => {
      analyser.getFloatTimeDomainData(buf);
      const rms = Math.sqrt(buf.reduce((s, v) => s + v * v, 0) / buf.length);
      pegel.value = Math.min(1, Math.max(0, (20 * Math.log10(rms + 1e-9) + 60) / 50)); // −60…−10 dBFS
      grundrauschen = Math.min(rms, grundrauschen * 1.002);
      const now = performance.now();
      if (rms > Math.max(0.005, grundrauschen * 3.2)) {
        gesprochen = true;
        stilleSeit = now;
      } else if (gesprochen && stilleStoppMs > 0 && now - stilleSeit > stilleStoppMs) {
        stop();
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    tick();
  }

  function stop() {
    if (recorder && recorder.state !== "inactive") recorder.stop();
    else aufraeumen();
  }

  /** Aufnahme verwerfen, ohne sie hochzuladen. */
  function abbrechen() {
    const r = resolveStop;
    resolveStop = null;
    if (recorder) recorder.onstop = () => aufraeumen();
    stop();
    r?.(null);
  }

  function aufraeumen() {
    cancelAnimationFrame(raf);
    clearInterval(timer);
    stream?.getTracks().forEach((t) => t.stop()); // Mikrofon wirklich freigeben
    ctx?.close();
    stream = null;
    ctx = null;
    recorder = null;
    pegel.value = 0;
    state.value = "idle";
  }

  onBeforeUnmount(abbrechen);

  return { state, pegel, sekunden, spur, start, stop, abbrechen };
}
