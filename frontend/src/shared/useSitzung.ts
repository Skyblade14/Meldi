import { onMounted, ref } from "vue";
import { api, beiAbgelaufenerSitzung } from "./api";
import type { Me } from "./types";

/** Anmeldung einer Ansicht. Läuft sie ab, wechselt die Ansicht von selbst zum Login, egal bei welcher Anfrage. */
export function useSitzung() {
  const me = ref<Me | null>(null);
  const geladen = ref(false);
  const abgelaufen = ref(false);

  beiAbgelaufenerSitzung(() => {
    if (me.value) abgelaufen.value = true; // beim ersten Laden ist ein 401 der Normalfall
    me.value = null;
  });

  onMounted(async () => {
    try {
      me.value = await api.me();
    } catch {
      me.value = null;
    }
    geladen.value = true;
  });

  function angemeldet(m: Me) {
    me.value = m;
    abgelaufen.value = false;
  }

  async function abmelden() {
    try {
      await api.logout();
    } finally {
      me.value = null;
      abgelaufen.value = false;
    }
  }

  return { me, geladen, abgelaufen, angemeldet, abmelden };
}
