import { computed, onMounted, reactive, ref, watch } from "vue";
import { api } from "./api";
import type { Nachricht, Rolle, Status } from "./types";
import { type Ereignis, useLiveFeed } from "./useLiveFeed";

export type StatusFilter = "alle" | "offen" | Status;

export interface Filter {
  status: StatusFilter;
  von: string;
  an: string;
  /** datetime-local, Ortszeit */
  ab: string;
  bis: string;
  text: string;
}

export const STATUS: Status[] = ["neu", "gesichtet", "erledigt"];

const leererFilter = (): Filter => ({ status: "alle", von: "", an: "", ab: "", bis: "", text: "" });

const klein = (s: string) => s.toLocaleLowerCase("de-DE");

export function passt(n: Nachricht, f: Filter, woerter: string[]): boolean {
  if (f.status === "offen" ? n.status === "erledigt" : f.status !== "alle" && n.status !== f.status) return false;
  if (f.von && n.von_funktion !== f.von) return false;
  if (f.an && n.an !== f.an) return false;
  const eingang = new Date(n.eingang_at).getTime();
  if (f.ab && eingang < new Date(f.ab).getTime()) return false;
  if (f.bis && eingang > new Date(f.bis).getTime() + 59_999) return false; // „bis 14:30“ schließt 14:30:59 ein
  if (!woerter.length) return true;
  const text = klein(`${n.lfd_nr} ${n.von_funktion} ${n.von_name} ${n.an} ${n.inhalt}`);
  return woerter.every((w) => text.includes(w));
}

export const suchwoerter = (text: string) => klein(text).split(/\s+/).filter(Boolean);

const sortiert = (werte: string[]) => [...new Set(werte)].sort((a, b) => a.localeCompare(b, "de"));

/**
 * Alle Nachrichten des Einsatzes, live aktualisiert, mit Filter und Suche. Für ELW- und Beobachter-Ansicht.
 * Gefiltert wird im Browser: Ein Einsatz hat wenige hundert Nachrichten, und neue fallen so sofort in den Filter.
 * Filter und „ungelesen“ liegen nur im Speicher (keine Daten auf dem Gerät ablegen).
 */
export function useEingang(titel: string, rollen: Rolle[]) {
  const nachrichten = ref<Nachricht[]>([]);
  const ungelesen = ref(new Set<number>());
  const filter = reactive<Filter>(leererFilter());
  let schonGeladen = false;

  async function laden() {
    let liste: Nachricht[];
    try {
      liste = await api.nachrichten();
    } catch {
      return; // 401 führt schon zum Login, sonst holt der nächste Verbindungsaufbau die Liste
    }
    const bekannt = new Set(nachrichten.value.map((n) => n.id));
    if (schonGeladen) liste.filter((n) => !bekannt.has(n.id)).forEach((n) => ungelesen.value.add(n.id));
    schonGeladen = true;
    // Was während des Ladens live ankam, fehlt womöglich in der Antwort und darf nicht verloren gehen.
    const geladen = new Set(liste.map((n) => n.id));
    nachrichten.value = [...nachrichten.value.filter((n) => !geladen.has(n.id)), ...liste].sort((a, b) => b.lfd_nr - a.lfd_nr);
  }

  /** Neue Nachricht einsortieren bzw. geänderte ersetzen (z.B. nach Statuswechsel). */
  function einpflegen(n: Nachricht, ereignis: Ereignis = "geaendert") {
    const i = nachrichten.value.findIndex((x) => x.id === n.id);
    if (i >= 0) nachrichten.value[i] = n;
    else if (ereignis === "neu") {
      nachrichten.value.unshift(n);
      ungelesen.value.add(n.id);
    } else laden(); // Änderung an einer unbekannten Nachricht: Liste ist veraltet
  }

  const { verbindung } = useLiveFeed(einpflegen, laden, rollen);
  onMounted(laden);

  const anzahlUngelesen = computed(() => ungelesen.value.size);
  watch(anzahlUngelesen, (n) => (document.title = n ? `(${n}) ${titel}` : titel));

  const gefiltert = computed(() => {
    const woerter = suchwoerter(filter.text);
    return nachrichten.value.filter((n) => passt(n, filter, woerter));
  });
  const filterAktiv = computed(() => JSON.stringify(filter) !== JSON.stringify(leererFilter()));
  const absender = computed(() => sortiert(nachrichten.value.map((n) => n.von_funktion)));
  const empfaenger = computed(() => sortiert(nachrichten.value.map((n) => n.an)));

  return {
    nachrichten,
    gefiltert,
    filter,
    filterAktiv,
    filterZuruecksetzen: () => Object.assign(filter, leererFilter()),
    absender,
    empfaenger,
    ungelesen,
    anzahlUngelesen,
    gelesen: (id: number) => ungelesen.value.delete(id),
    einpflegen,
    verbindung,
  };
}
