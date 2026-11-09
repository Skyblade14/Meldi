import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/shared/api";
import type { Me, Nachricht, TranscribeResult, Vorschlag } from "@/shared/types";
import MessageForm from "./MessageForm.vue";

vi.mock("@/shared/api", async (original) => ({
  ...(await original<typeof import("@/shared/api")>()),
  api: { nachrichten: vi.fn(), sende: vi.fn(), transcribe: vi.fn(), ladeFotoHoch: vi.fn() },
}));

const ME: Me = { name: "Max", rolle: "melder", funktion: "EA Brand", einsatz: "E" };

const ergebnis = (text: string, vorschlaege: Vorschlag[] = []): TranscribeResult =>
  ({ text, rohtext: text, modell: "m", vorschlaege, aufnahme_id: "a1", verarbeitung_sekunden: 1, warte_sekunden: 0 }) as TranscribeResult;
const v = (name: string, score: number): Vorschlag => ({ funktion_id: name.length, name, score }) as Vorschlag;

async function formular(): Promise<VueWrapper> {
  const w = mount(MessageForm, { props: { me: ME }, global: { stubs: { RecordButton: { name: "RecordButton", template: "<i />" } } } });
  await flushPromises();
  return w;
}

const mikrofone = (w: VueWrapper) => w.findAllComponents({ name: "RecordButton" });
const wert = (w: VueWrapper, id: string) => (w.get(id).element as HTMLInputElement).value;
const absenden = (w: VueWrapper) => w.get("button.primary");
const chips = (w: VueWrapper) => w.findAll(".vorschlaege .chip").map((c) => c.text());

async function sprichEmpfaenger(w: VueWrapper, r: TranscribeResult) {
  mikrofone(w)[0].vm.$emit("result", r);
  await flushPromises();
}

beforeEach(() => {
  vi.mocked(api.nachrichten).mockReset().mockResolvedValue([]);
  vi.mocked(api.sende).mockReset();
});

describe("Empfänger per Sprache", () => {
  it("übernimmt ab 80 Punkten direkt", async () => {
    const w = await formular();
    await sprichEmpfaenger(w, ergebnis("Einsatzleitug", [v("Einsatzleitung", 80)]));
    expect(wert(w, "#an")).toBe("Einsatzleitung");
    expect(chips(w)).toEqual([]);
  });

  it("nimmt unter 80 Punkten den erkannten Text ohne Satzzeichen", async () => {
    const w = await formular();
    await sprichEmpfaenger(w, ergebnis("Trupp zwei.", [v("EA Atemschutz", 79)]));
    expect(wert(w, "#an")).toBe("Trupp zwei");
    expect(chips(w)).toEqual(["EA Atemschutz"]);
  });

  it("bietet nach Übernahme nur Alternativen ab 50 Punkten an", async () => {
    const w = await formular();
    await sprichEmpfaenger(w, ergebnis("ELW", [v("ELW", 100), v("Einsatzleitung", 50), v("Polizei", 49)]));
    expect(chips(w)).toEqual(["Einsatzleitung"]);
  });

  it("bietet ohne Übernahme alles ab 40 Punkten an", async () => {
    const w = await formular();
    await sprichEmpfaenger(w, ergebnis("Etwas", [v("A", 79), v("BB", 40), v("CCC", 39)]));
    expect(chips(w)).toEqual(["A", "BB"]);
  });

  it("ein leeres Ergebnis ändert nichts", async () => {
    const w = await formular();
    await w.get("#an").setValue("Getippt");
    await sprichEmpfaenger(w, ergebnis(""));
    expect(wert(w, "#an")).toBe("Getippt");
  });

  it("merkt bei der Wahl eines Vorschlags die Tastatur als Eingabeart", async () => {
    vi.mocked(api.sende).mockResolvedValue({ id: 1, lfd_nr: 1, an: "ELW", eingang_at: "2026-11-08T10:00:00Z", anhaenge: [] } as unknown as Nachricht);
    const w = await formular();
    await sprichEmpfaenger(w, ergebnis("Etwas", [v("ELW", 60)]));
    await w.get(".vorschlaege .chip").trigger("click");
    await w.get("#inhalt").setValue("Text");
    await w.get("form").trigger("submit");
    await flushPromises();
    expect(vi.mocked(api.sende).mock.calls[0][0].eingabe.an).toEqual({ art: "text" });
  });
});

describe("Inhalt per Sprache", () => {
  it("hängt Etappen an und sammelt die Aufnahmen", async () => {
    vi.mocked(api.sende).mockResolvedValue({ id: 1, lfd_nr: 1, an: "ELW", eingang_at: "2026-11-08T10:00:00Z", anhaenge: [] } as unknown as Nachricht);
    const w = await formular();
    await w.get("#an").setValue("ELW");
    mikrofone(w)[1].vm.$emit("result", { ...ergebnis("Eins."), aufnahme_id: "a" });
    mikrofone(w)[1].vm.$emit("result", { ...ergebnis("Zwei."), aufnahme_id: "b" });
    await flushPromises();
    expect(wert(w, "#inhalt")).toBe("Eins. Zwei.");
    await w.get("form").trigger("submit");
    await flushPromises();
    const gesendet = vi.mocked(api.sende).mock.calls[0][0];
    expect(gesendet.anhaenge).toEqual(["a", "b"]);
    expect(gesendet.eingabe.inhalt).toEqual({ art: "sprache", rohtext: "Eins. Zwei.", modell: "m" });
  });
});

describe("Sperre beim Absenden", () => {
  async function gefuellt() {
    const w = await formular();
    await w.get("#an").setValue("ELW");
    await w.get("#inhalt").setValue("Text");
    return w;
  }

  it("ist ohne Hindernis frei", async () => {
    const w = await gefuellt();
    expect(absenden(w).attributes("disabled")).toBeUndefined();
    expect(w.find(".sperr-grund").exists()).toBe(false);
  });

  it.each([0, 1])("sperrt mit Grund, solange Mikrofon %i belegt ist", async (i) => {
    const w = await gefuellt();
    mikrofone(w)[i].vm.$emit("belegt", true);
    await flushPromises();
    expect(absenden(w).attributes("disabled")).toBeDefined();
    expect(w.get(".sperr-grund").text()).toContain("Spracheingabe läuft");
    mikrofone(w)[i].vm.$emit("belegt", false);
    await flushPromises();
    expect(absenden(w).attributes("disabled")).toBeUndefined();
  });

  it("gibt nach dem Absenden die Sperre frei, auch wenn das Mikrofon neu erzeugt wird", async () => {
    vi.mocked(api.sende).mockResolvedValue({ id: 1, lfd_nr: 1, an: "ELW", eingang_at: "2026-11-08T10:00:00Z", anhaenge: [] } as unknown as Nachricht);
    const w = await gefuellt();
    await w.get("form").trigger("submit");
    await flushPromises();
    await w.get("#an").setValue("ELW");
    await w.get("#inhalt").setValue("Noch eine");
    expect(absenden(w).attributes("disabled")).toBeUndefined();
  });
});

describe("Fehler beim Absenden", () => {
  it("behält den Text und meldet den Grund", async () => {
    vi.mocked(api.sende).mockRejectedValue(new ApiError(503, "NAS weg"));
    const w = await formular();
    await w.get("#an").setValue("ELW");
    await w.get("#inhalt").setValue("Wichtig");
    await w.get("form").trigger("submit");
    await flushPromises();
    expect(w.get("p.fehler").text()).toContain("NAS weg");
    expect(wert(w, "#inhalt")).toBe("Wichtig");
  });

  it("sendet beim Wiederholen dieselbe Sende-ID", async () => {
    vi.mocked(api.sende).mockRejectedValueOnce(new ApiError(0, "weg")).mockResolvedValue({ id: 1, lfd_nr: 1, an: "ELW", eingang_at: "2026-11-08T10:00:00Z", anhaenge: [] } as unknown as Nachricht);
    const w = await formular();
    await w.get("#an").setValue("ELW");
    await w.get("#inhalt").setValue("Wichtig");
    await w.get("form").trigger("submit");
    await flushPromises();
    await w.get("form").trigger("submit");
    await flushPromises();
    const [erste, zweite] = vi.mocked(api.sende).mock.calls.map((c) => c[0].sende_id);
    expect(erste).toBe(zweite);
  });

  it("verwendet für die nächste Nachricht eine neue Sende-ID", async () => {
    vi.mocked(api.sende).mockResolvedValue({ id: 1, lfd_nr: 1, an: "ELW", eingang_at: "2026-11-08T10:00:00Z", anhaenge: [] } as unknown as Nachricht);
    const w = await formular();
    for (const text of ["Eins", "Zwei"]) {
      await w.get("#an").setValue("ELW");
      await w.get("#inhalt").setValue(text);
      await w.get("form").trigger("submit");
      await flushPromises();
    }
    const [erste, zweite] = vi.mocked(api.sende).mock.calls.map((c) => c[0].sende_id);
    expect(erste).not.toBe(zweite);
  });

  it("lädt die gesendeten Nachrichten nach einer neuen Anmeldung neu", async () => {
    const w = await formular();
    vi.mocked(api.nachrichten).mockClear();
    await w.setProps({ me: { ...ME, name: "Andere Person" } });
    await flushPromises();
    expect(api.nachrichten).toHaveBeenCalledWith({ nurEigene: true });
  });
});
