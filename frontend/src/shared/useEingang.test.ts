import { describe, expect, it } from "vitest";
import type { Nachricht } from "./types";
import { type Filter, passt, suchwoerter } from "./useEingang";

const nachricht = (n: Partial<Nachricht> = {}): Nachricht =>
  ({
    id: 1,
    lfd_nr: 7,
    von_funktion: "EA Brand",
    von_name: "Max Müller",
    an: "Einsatzleitung",
    inhalt: "Feuer im Keller",
    status: "neu",
    eingang_at: "2026-11-08T14:30:30+01:00",
    ...n,
  }) as Nachricht;

const filter = (f: Partial<Filter> = {}): Filter => ({ status: "alle", von: "", an: "", ab: "", bis: "", text: "", ...f });
const trifft = (f: Partial<Filter>, n?: Partial<Nachricht>) => passt(nachricht(n), filter(f), suchwoerter(f.text ?? ""));

describe("Zeitraum", () => {
  // datetime-local liefert Ortszeit ohne Zone. Die Grenzen hier sind daher relativ zur lokalen Zeit gebaut.
  const eingang = (hms: string) => new Date(`2026-11-08T${hms}`).toISOString();

  it("„bis 14:30“ schließt 14:30:59 ein", () => {
    expect(trifft({ bis: "2026-11-08T14:30" }, { eingang_at: eingang("14:30:59") })).toBe(true);
  });

  it("„bis 14:30“ schließt 14:31:00 aus", () => {
    expect(trifft({ bis: "2026-11-08T14:30" }, { eingang_at: eingang("14:31:00") })).toBe(false);
  });

  it("„ab 14:30“ beginnt genau um 14:30:00", () => {
    expect(trifft({ ab: "2026-11-08T14:30" }, { eingang_at: eingang("14:30:00") })).toBe(true);
    expect(trifft({ ab: "2026-11-08T14:30" }, { eingang_at: eingang("14:29:59") })).toBe(false);
  });
});

describe("Status", () => {
  it.each([
    ["alle", "erledigt", true],
    ["offen", "neu", true],
    ["offen", "gesichtet", true],
    ["offen", "erledigt", false],
    ["gesichtet", "gesichtet", true],
    ["gesichtet", "neu", false],
  ] as const)("Filter %s bei Nachricht %s: %s", (status, nStatus, erwartet) => {
    expect(trifft({ status }, { status: nStatus })).toBe(erwartet);
  });
});

describe("Von und An", () => {
  it("vergleichen exakt", () => {
    expect(trifft({ von: "EA Brand" })).toBe(true);
    expect(trifft({ von: "EA" })).toBe(false);
    expect(trifft({ an: "Einsatzleitung" })).toBe(true);
    expect(trifft({ an: "Polizei" })).toBe(false);
  });
});

describe("Freitext", () => {
  it("ignoriert Groß- und Kleinschreibung", () => {
    expect(trifft({ text: "KELLER" })).toBe(true);
  });

  it("findet Umlaute unabhängig von der Schreibweise", () => {
    expect(trifft({ text: "MÜLLER" })).toBe(true);
    expect(trifft({ text: "ÄRGER" }, { inhalt: "Viel ärger" })).toBe(true);
  });

  it("verlangt alle Wörter, egal in welchem Feld", () => {
    expect(trifft({ text: "keller brand" })).toBe(true);
    expect(trifft({ text: "keller polizei" })).toBe(false);
  });

  it("sucht auch in der laufenden Nummer", () => {
    expect(trifft({ text: "7" })).toBe(true);
    expect(trifft({ text: "8" })).toBe(false);
  });

  it("ignoriert überzählige Leerzeichen", () => {
    expect(suchwoerter("  Feuer \t  Keller ")).toEqual(["feuer", "keller"]);
    expect(suchwoerter("   ")).toEqual([]);
  });
});
