<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { api } from "./api";
import { fmtDatumZeit } from "./format";
import type { Anhang, AuditEvent, Nachricht, Status } from "./types";
import { STATUS } from "./useEingang";

/**
 * Detailansicht einer Nachricht für ELW und Beobachter. Ein Klick auf ein Feld markiert es ganz, dann Strg+C
 * (→ EDP Web). Fotos per Rechtsklick → „Bild kopieren“.
 */
const props = defineProps<{ nachricht: Nachricht; darfStatus?: boolean; statusLaeuft?: boolean }>();
defineEmits<{ status: [Status] }>();

const audit = ref<AuditEvent[]>([]);

// Neu laden bei anderer Nachricht und nach Statuswechsel (auch wenn ihn ein anderer ELW-Platz gesetzt hat)
watch(
  () => [props.nachricht.id, props.nachricht.status],
  async ([id], alt) => {
    if (alt?.[0] !== id) audit.value = [];
    try {
      const geladen = await api.audit(props.nachricht.id);
      if (props.nachricht.id === id) audit.value = geladen;
    } catch {
      // 401 führt schon zum Login. Sonst bleibt das Protokoll bis zum nächsten Statuswechsel leer.
    }
  },
  { immediate: true },
);

const aufnahmen = computed(() => props.nachricht.anhaenge.filter((a) => a.art === "audio"));
const fotos = computed(() => props.nachricht.anhaenge.filter((a) => a.art === "foto"));

function gps(a: Anhang): string | null {
  const g = a.meta.gps as { lat: number; lon: number } | undefined;
  return g ? `${g.lat.toFixed(6)}, ${g.lon.toFixed(6)}` : null;
}
const aufgenommen = (a: Anhang) => (typeof a.meta.aufgenommen_at === "string" ? fmtDatumZeit(a.meta.aufgenommen_at) : null);
const aufnahmeLabel = (a: Anhang) => (a.feld === "an" ? "An" : `Inhalt ${a.dateiname.match(/_(\d+)\./)?.[1] ?? ""}`);

const eingabeart = (feld: "an" | "inhalt") => (props.nachricht.eingabe[feld]?.art === "sprache" ? "🎤" : "⌨");

/** Klick markiert das ganze Feld. Wer mit der Maus zieht, behält seine Teilauswahl (kein user-select: all). */
function markiere(e: MouseEvent) {
  const auswahl = window.getSelection();
  if (!auswahl?.isCollapsed) return;
  const range = document.createRange();
  range.selectNodeContents(e.currentTarget as Node);
  auswahl.removeAllRanges();
  auswahl.addRange(range);
}

/** Markierungen über Blockgrenzen bringen Zeilenumbrüche mit. In EDP Web ergäbe das Leerzeilen. */
function kopieren(e: ClipboardEvent) {
  const text = window.getSelection()?.toString() ?? "";
  if (!e.clipboardData || text.trim() === text) return;
  e.clipboardData.setData("text/plain", text.trim());
  e.preventDefault();
}

function aktion(a: AuditEvent): string {
  const s = a.aenderungen.status;
  return a.aktion === "status" && s ? `${s.alt} → ${s.neu}` : a.aktion;
}
</script>

<template>
  <div class="detail" @copy="kopieren">
    <div v-if="darfStatus" class="status-wahl chips" role="group" aria-label="Status setzen">
      <button
        v-for="s in STATUS"
        :key="s"
        type="button"
        :class="['chip', { aktiv: nachricht.status === s }]"
        :disabled="statusLaeuft"
        :aria-pressed="nachricht.status === s"
        @click="nachricht.status !== s && $emit('status', s)"
      >
        {{ s }}
      </button>
    </div>

    <p class="muted hinweis kopier-hinweis">Klick markiert ein Feld · Strg+C kopiert</p>
    <dl>
      <dt>Nr.</dt>
      <dd class="kopierbar" @click="markiere">{{ nachricht.lfd_nr }}</dd>
      <dt>Status</dt>
      <dd><span data-testid="detail-status" :class="['status-badge', nachricht.status]">{{ nachricht.status }}</span></dd>
      <dt>Eingang ELW</dt>
      <dd class="kopierbar" @click="markiere">{{ fmtDatumZeit(nachricht.eingang_at) }}</dd>
      <dt>Von</dt>
      <dd class="kopierbar" @click="markiere">{{ nachricht.von_funktion }}</dd>
      <dt>Name</dt>
      <dd class="kopierbar" @click="markiere">{{ nachricht.von_name }}</dd>
      <dt>An <span class="muted" :title="nachricht.eingabe.an?.art">{{ eingabeart("an") }}</span></dt>
      <dd class="kopierbar" @click="markiere">{{ nachricht.an }}</dd>
      <dt>Erfasst (Handy)</dt>
      <dd class="kopierbar" @click="markiere">{{ fmtDatumZeit(nachricht.erfasst_at) }}</dd>
    </dl>
    <h3>Inhalt <span class="muted">{{ eingabeart("inhalt") }}</span></h3>
    <p class="inhalt-voll kopierbar" @click="markiere">{{ nachricht.inhalt }}</p>

    <details v-if="nachricht.eingabe.inhalt?.rohtext || nachricht.eingabe.an?.rohtext">
      <summary>Spracherkennung (Rohtext)</summary>
      <p v-if="nachricht.eingabe.an?.rohtext"><strong>An:</strong> {{ nachricht.eingabe.an.rohtext }}</p>
      <p v-if="nachricht.eingabe.inhalt?.rohtext"><strong>Inhalt:</strong> {{ nachricht.eingabe.inhalt.rohtext }}</p>
      <p class="muted">Modell: {{ nachricht.eingabe.inhalt?.modell ?? nachricht.eingabe.an?.modell }}</p>
    </details>

    <template v-if="fotos.length">
      <h3>Fotos <span class="muted hinweis">Rechtsklick → „Bild kopieren“</span></h3>
      <ul class="fotos">
        <li v-for="a in fotos" :key="a.id">
          <a :href="api.anhangUrl(nachricht.id, a.id)" target="_blank" rel="noopener">
            <img :src="api.anhangUrl(nachricht.id, a.id)" :alt="a.dateiname" loading="lazy" />
          </a>
          <span class="muted">
            {{ a.dateiname }}
            <template v-if="aufgenommen(a)"> · {{ aufgenommen(a) }}</template>
            <br />
            <template v-if="gps(a)">GPS {{ gps(a) }}</template>
            <template v-else>ohne GPS</template>
          </span>
        </li>
      </ul>
    </template>

    <template v-if="aufnahmen.length">
      <h3>Sprachaufnahmen</h3>
      <ul class="aufnahmen">
        <li v-for="a in aufnahmen" :key="a.id">
          <span class="muted">{{ aufnahmeLabel(a) }}</span>
          <audio controls preload="none" :src="api.anhangUrl(nachricht.id, a.id)" />
        </li>
      </ul>
    </template>

    <h3>Protokoll</h3>
    <ul class="audit">
      <li v-for="(a, i) in audit" :key="i">
        {{ fmtDatumZeit(a.zeitpunkt) }} – {{ aktion(a) }} durch {{ a.funktion }} ({{ a.name }})
      </li>
    </ul>
  </div>
</template>

<style scoped>
.status-wahl {
  margin-bottom: 14px;
}
.status-wahl .chip {
  min-height: 44px;
  min-width: 100px;
}
dl {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 6px 14px;
  margin: 0;
}
dt {
  color: var(--muted);
}
dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.kopierbar {
  cursor: text;
  border-radius: 2px;
}
@media (hover: hover) {
  /* box-shadow statt Padding/Margin: verschiebt nichts und erzeugt keinen seitlichen Überlauf */
  .kopierbar:hover {
    --hover-bg: color-mix(in srgb, var(--text) 8%, transparent);
    background: var(--hover-bg);
    box-shadow: 0 0 0 4px var(--hover-bg);
  }
}
.kopier-hinweis {
  margin: 0 0 8px;
}
h3 {
  font-size: 1rem;
  margin: 16px 0 6px;
}
.hinweis {
  font-size: 0.8rem;
  font-weight: 400;
}
@media (hover: none) {
  .hinweis {
    display: none; /* Handy: lange drücken statt Rechtsklick */
  }
}
.inhalt-voll {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 1.05rem;
  margin: 0;
}
details {
  margin-top: 12px;
  font-size: 0.9rem;
}
.audit {
  padding-left: 18px;
  margin: 0;
  font-size: 0.9rem;
}
.fotos {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px;
}
.fotos li {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.8rem;
}
.fotos img {
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  display: block;
}
.aufnahmen {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.aufnahmen li {
  display: grid;
  grid-template-columns: 70px 1fr;
  align-items: center;
  gap: 8px;
}
.aufnahmen audio {
  width: 100%;
}
</style>
