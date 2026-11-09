import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, beiAbgelaufenerSitzung } from "./api";

const antwort = (status: number, body?: unknown) =>
  new Response(body === undefined ? null : JSON.stringify(body), { status });

afterEach(() => {
  beiAbgelaufenerSitzung(() => {});
  vi.unstubAllGlobals();
});

describe("Fehlerbehandlung", () => {
  it("meldet 401 zentral und wirft trotzdem", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(antwort(401, { detail: "Nicht angemeldet" })));
    const handler = vi.fn();
    beiAbgelaufenerSitzung(handler);
    await expect(api.nachrichten()).rejects.toMatchObject({ status: 401, message: "Nicht angemeldet" });
    expect(handler).toHaveBeenCalledOnce();
  });

  it("meldet andere Fehler nicht als abgelaufene Sitzung", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(antwort(503, { detail: "NAS weg" })));
    const handler = vi.fn();
    beiAbgelaufenerSitzung(handler);
    await expect(api.nachrichten()).rejects.toMatchObject({ status: 503, message: "NAS weg" });
    expect(handler).not.toHaveBeenCalled();
  });

  it("zeigt Validierungsfehler verständlich statt als JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(antwort(422, { detail: [{ loc: ["body", "inhalt"], msg: "too long" }] })));
    await expect(api.me()).rejects.toThrow("Eingabe ungültig");
  });

  it("ohne Netz: Status 0 und deutscher Text", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const fehler = await api.me().catch((e) => e);
    expect(fehler).toBeInstanceOf(ApiError);
    expect(fehler).toMatchObject({ status: 0, message: "Keine Verbindung zum ELW" });
  });

  it("kommt mit einer Fehlerantwort ohne JSON zurecht", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>Bad Gateway</html>", { status: 502, statusText: "Bad Gateway" })));
    await expect(api.me()).rejects.toMatchObject({ status: 502, message: "Bad Gateway" });
  });
});

describe("Anfragen", () => {
  it("nutzt keinen Browser-Cache", async () => {
    const f = vi.fn().mockResolvedValue(antwort(200, []));
    vi.stubGlobal("fetch", f);
    await api.nachrichten({ nurEigene: true });
    expect(f.mock.calls[0][0]).toBe("/api/messages?nur_eigene=true");
    expect(f.mock.calls[0][1]).toMatchObject({ credentials: "same-origin", cache: "no-store" });
  });

  it("liefert bei 204 undefined", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(api.logout()).resolves.toBeUndefined();
  });

  it.each([
    ["audio/webm;codecs=opus", "aufnahme.webm"],
    ["audio/mp4", "aufnahme.m4a"],
    ["audio/ogg;codecs=opus", "aufnahme.ogg"],
  ])("benennt die Aufnahme nach dem Format: %s", async (typ, name) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(antwort(200, {})));
    const anhaengen = vi.spyOn(FormData.prototype, "append");
    await api.transcribe(new Blob(["x"], { type: typ }), "inhalt");
    expect(anhaengen.mock.calls[0][2]).toBe(name);
  });
});
