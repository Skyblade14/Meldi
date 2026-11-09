<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { api, ApiError } from "@/shared/api";
import { fmtZeit } from "@/shared/format";
import { bereiteFotoVor, type VorbereitetesFoto } from "@/shared/foto";
import RecordButton from "@/shared/RecordButton.vue";
import type { FeldEingabe, Me, Nachricht, TranscribeResult, Vorschlag } from "@/shared/types";

const props = defineProps<{ me: Me }>();

/** Ab diesem Score wird ein gesprochener Empfänger direkt übernommen. */
const AUTO_UEBERNAHME_SCORE = 80;
const MAX_FOTOS = 5; // wie MELDI_MAX_FOTOS im Backend

interface FotoEintrag {
  key: number;
  vorschau?: string; // blob:-URL, nur im Arbeitsspeicher
  foto?: VorbereitetesFoto;
  id?: string;
  laedt: boolean;
  fehler?: string;
}

const gesendet = ref<Nachricht[]>([]);
const form = reactive({ an: "", inhalt: "" });
const eingabe = reactive<{ an?: FeldEingabe; inhalt?: FeldEingabe }>({});
const vorschlaege = ref<Vorschlag[]>([]);
/** Aufnahmen für die Einsatzablage: beim Empfänger nur die letzte, beim Inhalt alle Etappen. */
const aufnahmen = reactive<{ an: string[]; inhalt: string[] }>({ an: [], inhalt: [] });
let erfasstAt: string | null = null;
const sendet = ref(false);
const fehler = ref<string | null>(null);
const bestaetigung = ref<Nachricht | null>(null);
const formNr = ref(0); // erzwingt frische Mikrofon-Buttons nach dem Absenden
const fotos = ref<FotoEintrag[]>([]);
const spracheBelegt = reactive({ an: false, inhalt: false });
const fotoInput = ref<HTMLInputElement | null>(null);
let fotoKey = 0;
let sendeId = neueSendeId();

/** Zufällige ID je Formular. getRandomValues statt randomUUID: funktioniert auch ohne HTTPS (Entwicklung). */
function neueSendeId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Nur Empfänger, an die in dieser Anmeldung schon gesendet wurde – neueste zuerst, ohne Doppelte. */
const empfaenger = computed(() => [...new Set(gesendet.value.map((n) => n.an))].filter((an) => an !== props.me.funktion));
/** Warum nicht abgesendet werden kann, obwohl die Felder gefüllt sind. Unter Stress muss das am Knopf stehen. */
const sperrGrund = computed(() => {
  if (spracheBelegt.an || spracheBelegt.inhalt) return "Spracheingabe läuft. Bitte warten, bis der Text erkannt ist.";
  if (fotos.value.some((f) => f.laedt)) return "Foto wird noch hochgeladen.";
  if (fotos.value.some((f) => f.fehler)) return "Fehlerhaftes Foto entfernen oder erneut hochladen.";
  return null;
});
const sendebereit = computed(() => form.an.trim() && form.inhalt.trim() && !sperrGrund.value && !sendet.value);

async function ladeGesendet() {
  gesendet.value = [];
  try {
    gesendet.value = await api.nachrichten({ nurEigene: true });
  } catch {
    // Nur die Übersicht. Das Erfassen geht auch ohne, und ein 401 führt schon zum Login.
  }
}

onMounted(ladeGesendet);
// Neue Anmeldung nach Ablauf der Sitzung, womöglich eine andere Person: Deren Liste, nicht die alte.
watch(
  () => props.me,
  () => {
    bestaetigung.value = null;
    fehler.value = null;
    ladeGesendet();
  },
);
onUnmounted(() => fotos.value.forEach(gibVorschauFrei));

function beginne() {
  erfasstAt ??= new Date().toISOString();
}

function anErkannt(r: TranscribeResult) {
  if (!r.text) return;
  beginne();
  const [best, ...rest] = r.vorschlaege;
  if (best && best.score >= AUTO_UEBERNAHME_SCORE) {
    form.an = best.name;
    vorschlaege.value = rest.filter((v) => v.score >= 50);
  } else {
    form.an = r.text.replace(/[.!?]$/, "");
    vorschlaege.value = r.vorschlaege.filter((v) => v.score >= 40);
  }
  eingabe.an = { art: "sprache", rohtext: r.rohtext, modell: r.modell };
  aufnahmen.an = r.aufnahme_id ? [r.aufnahme_id] : [];
}

function inhaltErkannt(r: TranscribeResult) {
  if (!r.text) return;
  beginne();
  // Mehrere Aufnahmen hintereinander werden angehängt – so kann man in Etappen diktieren.
  form.inhalt = form.inhalt.trim() ? `${form.inhalt.trim()} ${r.text}` : r.text;
  const vorher = eingabe.inhalt?.rohtext;
  eingabe.inhalt = { art: "sprache", rohtext: vorher ? `${vorher} ${r.rohtext}` : r.rohtext, modell: r.modell };
  if (r.aufnahme_id) aufnahmen.inhalt.push(r.aufnahme_id);
}

async function fotoGewaehlt(e: Event) {
  const input = e.target as HTMLInputElement;
  const dateien = [...(input.files ?? [])].slice(0, MAX_FOTOS - fotos.value.length);
  input.value = ""; // keine Referenz auf die Originaldatei behalten
  for (const datei of dateien) {
    beginne();
    const eintrag = reactive<FotoEintrag>({ key: ++fotoKey, laedt: true });
    fotos.value.push(eintrag);
    try {
      const foto = await bereiteFotoVor(datei);
      if (!fotoNochDa(eintrag)) continue; // während der Vorbereitung entfernt
      eintrag.foto = foto;
      eintrag.vorschau = URL.createObjectURL(foto.blob);
    } catch {
      eintrag.laedt = false;
      eintrag.fehler = "Foto nicht lesbar";
      continue;
    }
    await ladeFotoHoch(eintrag);
  }
}

async function ladeFotoHoch(eintrag: FotoEintrag) {
  if (!eintrag.foto) return;
  eintrag.laedt = true;
  eintrag.fehler = undefined;
  try {
    const { foto_id } = await api.ladeFotoHoch(eintrag.foto);
    if (!fotoNochDa(eintrag)) return; // entfernt – der Upload verfällt auf dem Server
    eintrag.id = foto_id;
    eintrag.foto = undefined; // liegt jetzt im ELW, Vorschau genügt
  } catch (e) {
    eintrag.fehler = e instanceof Error ? e.message : String(e);
  } finally {
    eintrag.laedt = false;
  }
}

const fotoNochDa = (f: FotoEintrag) => fotos.value.some((x) => x.key === f.key);

function gibVorschauFrei(f: FotoEintrag) {
  if (f.vorschau) URL.revokeObjectURL(f.vorschau);
}

function entferneFoto(f: FotoEintrag) {
  gibVorschauFrei(f);
  fotos.value = fotos.value.filter((x) => x.key !== f.key);
}

function waehleEmpfaenger(name: string) {
  beginne();
  form.an = name;
  vorschlaege.value = [];
  eingabe.an = { art: "text" };
}

async function absenden() {
  fehler.value = null;
  sendet.value = true;
  try {
    const n = await api.sende({
      an: form.an,
      inhalt: form.inhalt,
      erfasst_at: erfasstAt ?? new Date().toISOString(),
      eingabe: {
        an: eingabe.an ?? { art: "text" },
        inhalt: eingabe.inhalt ?? { art: "text" },
      },
      anhaenge: [...aufnahmen.an, ...aufnahmen.inhalt, ...fotos.value.map((f) => f.id!)],
      sende_id: sendeId,
    });
    gesendet.value = [n, ...gesendet.value.filter((x) => x.id !== n.id)];
    bestaetigung.value = n;
    zuruecksetzen();
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return; // Login, danach sendet man mit dem erhaltenen Text erneut
    fehler.value = `Nicht übermittelt: ${e instanceof Error ? e.message : e}. Bitte erneut senden.`;
  } finally {
    sendet.value = false;
  }
}

function leereInhalt() {
  form.inhalt = "";
  delete eingabe.inhalt;
  aufnahmen.inhalt = [];
}

function zuruecksetzen() {
  form.an = "";
  form.inhalt = "";
  delete eingabe.an;
  delete eingabe.inhalt;
  aufnahmen.an = [];
  aufnahmen.inhalt = [];
  fotos.value.forEach(gibVorschauFrei);
  fotos.value = [];
  vorschlaege.value = [];
  erfasstAt = null;
  sendeId = neueSendeId();
  spracheBelegt.an = spracheBelegt.inhalt = false;
  formNr.value++;
}
</script>

<template>
  <div v-if="bestaetigung" class="ok card" role="status">
    <strong>Nachricht Nr. {{ bestaetigung.lfd_nr }} übermittelt</strong>
    <span>Eingang im ELW {{ fmtZeit(bestaetigung.eingang_at) }} · an {{ bestaetigung.an }}</span>
    <span v-if="bestaetigung.fehlende_anhaenge" class="fehler">
      {{ bestaetigung.fehlende_anhaenge }} Aufnahme(n) bzw. Foto(s) sind nicht angekommen. Fotos bitte in einer neuen
      Nachricht erneut senden.
    </span>
    <button class="secondary" @click="bestaetigung = null">OK</button>
  </div>

  <form class="nachricht card" @submit.prevent="absenden">
    <div class="von">
      <span class="muted">Von</span>
      <strong>{{ me.funktion }}</strong>
    </div>

    <section>
      <div class="feldkopf">
        <label for="an">An</label>
        <RecordButton :key="`an${formNr}`" feld="an" label="Empfänger sprechen" @result="anErkannt" @belegt="spracheBelegt.an = $event" />
      </div>
      <input id="an" v-model="form.an" placeholder="Empfänger" autocomplete="off" @input="beginne(); eingabe.an ??= { art: 'text' }" />
      <div v-if="vorschlaege.length" class="vorschlaege">
        <span class="muted">Meinten Sie:</span>
        <button v-for="v in vorschlaege" :key="v.funktion_id" type="button" class="chip" @click="waehleEmpfaenger(v.name)">
          {{ v.name }}
        </button>
      </div>
      <div v-if="empfaenger.length" class="chips">
        <button
          v-for="an in empfaenger"
          :key="an"
          type="button"
          class="chip"
          :class="{ aktiv: form.an === an }"
          @click="waehleEmpfaenger(an)"
        >
          {{ an }}
        </button>
      </div>
    </section>

    <section>
      <div class="feldkopf">
        <label for="inhalt">Inhalt</label>
        <RecordButton :key="`inhalt${formNr}`" feld="inhalt" label="Inhalt sprechen" @result="inhaltErkannt" @belegt="spracheBelegt.inhalt = $event" />
      </div>
      <textarea id="inhalt" v-model="form.inhalt" rows="5" placeholder="Was soll gemeldet werden?" @input="beginne(); eingabe.inhalt ??= { art: 'text' }" />
      <button v-if="form.inhalt" type="button" class="link" @click="leereInhalt">Inhalt leeren</button>
    </section>

    <section>
      <div class="feldkopf">
        <span class="label">Fotos <span v-if="fotos.length" class="muted">({{ fotos.length }}/{{ MAX_FOTOS }})</span></span>
        <button
          v-if="fotos.length < MAX_FOTOS"
          type="button"
          class="secondary foto-btn"
          :disabled="sendet"
          @click="fotoInput?.click()"
        >
          📷 Foto aufnehmen
        </button>
        <input ref="fotoInput" type="file" accept="image/*" capture="environment" hidden @change="fotoGewaehlt" />
      </div>
      <ul v-if="fotos.length" class="fotos">
        <li v-for="f in fotos" :key="f.key" data-testid="foto-kachel" :class="{ fehler: f.fehler }">
          <img v-if="f.vorschau" :src="f.vorschau" alt="Foto-Vorschau" />
          <span v-if="f.laedt" class="status">lädt …</span>
          <span v-else-if="f.fehler" class="status">
            {{ f.fehler }}
            <button v-if="f.foto" type="button" class="link" @click="ladeFotoHoch(f)">erneut</button>
          </span>
          <button type="button" class="entfernen" aria-label="Foto entfernen" @click="entferneFoto(f)">✕</button>
        </li>
      </ul>
    </section>

    <p v-if="fehler" class="fehler">{{ fehler }}</p>
    <p v-if="sperrGrund" class="muted sperr-grund">{{ sperrGrund }}</p>
    <button class="primary" :disabled="!sendebereit">{{ sendet ? "Sende …" : "Absenden" }}</button>
  </form>

  <section v-if="gesendet.length" class="gesendet">
    <h2>Gesendet</h2>
    <article v-for="n in gesendet" :key="n.id" class="card eintrag">
      <header>
        <strong>Nr. {{ n.lfd_nr }}</strong>
        <span class="muted">{{ fmtZeit(n.eingang_at) }}</span>
      </header>
      <div class="muted">
        an {{ n.an }}
        <template v-if="n.anhaenge.some((a) => a.art === 'foto')">
          · 📷 {{ n.anhaenge.filter((a) => a.art === "foto").length }}
        </template>
      </div>
      <p>{{ n.inhalt }}</p>
    </article>
  </section>
</template>

<style scoped>
.nachricht {
  display: flex;
  flex-direction: column;
  gap: 22px;
}
section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.von {
  display: flex;
  gap: 10px;
  align-items: baseline;
  font-size: 1.1rem;
}
.feldkopf {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.feldkopf label,
.label {
  font-weight: 700;
  font-size: 1.1rem;
  padding-top: 12px;
}
.vorschlaege {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.foto-btn {
  min-height: 44px;
  margin-top: 4px;
}
.fotos {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 8px;
}
.fotos li {
  position: relative;
  aspect-ratio: 1;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--bg);
  display: flex;
  align-items: center;
  justify-content: center;
}
.fotos li.fehler {
  border-color: var(--danger);
}
.fotos img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.fotos .status {
  position: absolute;
  inset: auto 0 0 0;
  padding: 2px 6px;
  font-size: 0.8rem;
  background: color-mix(in srgb, var(--surface) 85%, transparent);
}
.fotos .entfernen {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 44px;
  height: 44px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface);
  font-size: 1.1rem;
}
.sperr-grund {
  margin: 0;
}
.link {
  align-self: flex-start;
  min-height: 44px;
  min-width: 44px;
  background: none;
  border: none;
  padding: 0;
  color: var(--muted);
  text-decoration: underline;
  font-size: 0.9rem;
}
.ok {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 16px;
  border-color: var(--ok);
  border-width: 2px;
}
.ok strong {
  color: var(--ok);
}
.ok .secondary {
  align-self: flex-start;
}
.gesendet h2 {
  font-size: 1.1rem;
  margin: 24px 0 0;
}
.eintrag header {
  display: flex;
  gap: 10px;
  align-items: baseline;
}
.eintrag p {
  margin: 6px 0 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
