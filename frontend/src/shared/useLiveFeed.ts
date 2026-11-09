import { onBeforeUnmount, ref } from "vue";
import { api, ApiError, sitzungBeendet } from "@/shared/api";
import type { Nachricht, Rolle } from "@/shared/types";

export type Verbindung = "verbinde" | "live" | "getrennt";
export type Ereignis = "neu" | "geaendert";

/**
 * Live-Feed neuer und geänderter Nachrichten per WebSocket, mit automatischem Wiederverbinden.
 * `rollen`: Wer diese Ansicht sehen darf. Im selben Browser kann die Anmeldung inzwischen eine andere sein.
 */
export function useLiveFeed(onNachricht: (n: Nachricht, ereignis: Ereignis) => void, onVerbunden: () => void, rollen: Rolle[]) {
  const verbindung = ref<Verbindung>("verbinde");
  let ws: WebSocket | null = null;
  let versuche = 0;
  let ping = 0;
  let retry = 0;
  let beendet = false;

  function verbinden() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/api/ws/elw`);
    ws.onopen = () => {
      onVerbunden(); // Verpasstes nachladen, auch beim ersten Mal: Der Kanal kann nach dem ersten Laden aufgehen
      versuche = 0;
      verbindung.value = "live";
      ping = window.setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send("ping"), 20_000);
    };
    ws.onmessage = (e) => {
      const event = JSON.parse(e.data);
      if (event.type === "nachricht.neu") onNachricht(event.nachricht, "neu");
      else if (event.type === "nachricht.geaendert") onNachricht(event.nachricht, "geaendert");
    };
    ws.onclose = () => {
      clearInterval(ping);
      verbindung.value = "getrennt";
      if (beendet) return;
      versuche++;
      retry = window.setTimeout(wiederverbinden, Math.min(10_000, 500 * 2 ** versuche));
    };
  }

  /** Ein abgelehnter WebSocket sieht aus wie eine Netzstörung. Erst die Sitzung zeigt, ob sich Warten lohnt. */
  async function wiederverbinden() {
    try {
      const me = await api.me();
      if (!rollen.includes(me.rolle)) {
        sitzungBeendet();
        return;
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return; // api.ts hat die Ansicht schon zum Login geschickt
      // Sonst Netz oder Server weg: trotzdem weiter versuchen, das WebSocket-onclose plant den nächsten Anlauf.
    }
    if (!beendet) verbinden();
  }

  function trennen() {
    beendet = true;
    clearTimeout(retry);
    clearInterval(ping);
    ws?.close();
  }

  verbinden();
  onBeforeUnmount(trennen);
  return { verbindung, trennen };
}
