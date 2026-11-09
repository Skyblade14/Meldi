import type { VorbereitetesFoto } from "./foto";
import type {
  AktiveAnmeldung,
  AuditEvent,
  Feld,
  FotoUpload,
  Funktion,
  Me,
  Nachricht,
  NachrichtCreate,
  Rolle,
  Status,
  TranscribeResult,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

let abgelaufenHandler: () => void = () => {};

/** Jede Ansicht meldet hier an, was bei einer abgelaufenen Sitzung passieren soll. */
export function beiAbgelaufenerSitzung(handler: () => void) {
  abgelaufenHandler = handler;
}

export function sitzungBeendet() {
  abgelaufenHandler();
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { credentials: "same-origin", cache: "no-store", ...init });
  } catch {
    throw new ApiError(0, "Keine Verbindung zum ELW");
  }
  if (!res.ok) {
    if (res.status === 401) sitzungBeendet();
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : "Eingabe ungültig. Bitte prüfen: leer oder zu lang?";
    } catch {
      /* kein JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  funktionen: () => request<Funktion[]>("/api/auth/funktionen"),
  me: () => request<Me>("/api/auth/me"),
  login: (name: string, rolle: Rolle, funktion?: string) => request<Me>("/api/auth/login", json({ name, rolle, funktion })),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  anmeldungen: () => request<AktiveAnmeldung[]>("/api/auth/anmeldungen"),

  nachrichten: ({ nurEigene = false } = {}) => request<Nachricht[]>(`/api/messages${nurEigene ? "?nur_eigene=true" : ""}`),
  sende: (n: NachrichtCreate) => request<Nachricht>("/api/messages", json(n)),
  audit: (id: number) => request<AuditEvent[]>(`/api/messages/${id}/audit`),
  setzeStatus: (id: number, status: Status) =>
    request<Nachricht>(`/api/messages/${id}/status`, { ...json({ status }), method: "PUT" }),
  anhangUrl: (nachrichtId: number, anhangId: number) => `/api/messages/${nachrichtId}/anhaenge/${anhangId}`,

  transcribe(audio: Blob, field: Feld, aufnahme = "") {
    const form = new FormData();
    const ext = audio.type.includes("mp4") ? "m4a" : audio.type.includes("ogg") ? "ogg" : "webm";
    form.append("audio", audio, `aufnahme.${ext}`);
    form.append("field", field);
    form.append("aufnahme", aufnahme);
    return request<TranscribeResult>("/api/speech/transcribe", { method: "POST", body: form });
  },

  ladeFotoHoch(foto: VorbereitetesFoto) {
    const form = new FormData();
    form.append("datei", foto.blob, "foto.jpg");
    if (foto.gps) {
      form.append("gps_lat", String(foto.gps.lat));
      form.append("gps_lon", String(foto.gps.lon));
    }
    if (foto.aufgenommenAt) form.append("aufgenommen_at", foto.aufgenommenAt);
    return request<FotoUpload>("/api/uploads/foto", { method: "POST", body: form });
  },
};
