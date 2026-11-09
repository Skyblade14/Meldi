<script setup lang="ts">
import { computed, ref } from "vue";
import { api } from "@/shared/api";
import FilterLeiste from "@/shared/FilterLeiste.vue";
import { fmtZeit } from "@/shared/format";
import NachrichtDetail from "@/shared/NachrichtDetail.vue";
import type { Me, Nachricht, Status } from "@/shared/types";
import { useEingang } from "@/shared/useEingang";
import Anmeldungen from "./Anmeldungen.vue";

defineProps<{ me: Me }>();
defineEmits<{ abmelden: [] }>();

const e = useEingang("Meldi – ELW", ["elw"]);
const { nachrichten, gefiltert, filter, ungelesen, anzahlUngelesen, verbindung } = e;

// Nur die ID merken: Live-Updates ersetzen das Objekt in der Liste.
const auswahlId = ref<number | null>(null);
const auswahl = computed(() => nachrichten.value.find((n) => n.id === auswahlId.value) ?? null);
const statusLaeuft = ref(false);
const statusFehler = ref<string | null>(null);
const anmeldungenOffen = ref(false);

function oeffne(n: Nachricht) {
  // Wer gerade Text in der Tabelle markiert (zum Kopieren), will die Nachricht nicht wechseln.
  if (window.getSelection()?.toString()) return;
  auswahlId.value = n.id;
  statusFehler.value = null;
  e.gelesen(n.id);
}

async function setzeStatus(status: Status) {
  if (!auswahl.value) return;
  statusLaeuft.value = true;
  statusFehler.value = null;
  try {
    e.einpflegen(await api.setzeStatus(auswahl.value.id, status));
  } catch (err) {
    statusFehler.value = err instanceof Error ? err.message : String(err);
  } finally {
    statusLaeuft.value = false;
  }
}

const anzahlFotos = (n: Nachricht) => n.anhaenge.filter((a) => a.art === "foto").length;
</script>

<template>
  <header class="top">
    <strong>Meldi · ELW</strong>
    <span class="einsatz">{{ me.einsatz }}</span>
    <span data-testid="verbindung" :class="['verbindung', verbindung]">{{ verbindung === "live" ? "● live" : verbindung === "verbinde" ? "verbinde …" : "● getrennt" }}</span>
    <a class="secondary erfassen" href="/melder/" target="_blank" title="Melder-Ansicht in neuem Tab, z.B. für Meldungen per Funk oder Telefon">
      Nachricht erfassen
    </a>
    <button class="secondary" @click="anmeldungenOffen = !anmeldungenOffen">Angemeldet</button>
    <span class="wer">{{ me.funktion }} · {{ me.name }}</span>
    <button class="secondary" @click="$emit('abmelden')">Abmelden</button>
  </header>
  <Anmeldungen v-if="anmeldungenOffen" @schliessen="anmeldungenOffen = false" />

  <div class="layout">
    <section class="liste">
      <h2>
        Eingang <span class="muted">({{ nachrichten.length }}<template v-if="anzahlUngelesen">, {{ anzahlUngelesen }} neu</template>)</span>
      </h2>
      <FilterLeiste
        :filter="filter"
        :absender="e.absender.value"
        :empfaenger="e.empfaenger.value"
        :anzahl="gefiltert.length"
        :gesamt="nachrichten.length"
        :aktiv="e.filterAktiv.value"
        @zuruecksetzen="e.filterZuruecksetzen"
      />
      <p v-if="!nachrichten.length" class="muted">Noch keine Nachrichten.</p>
      <p v-else-if="!gefiltert.length" class="muted">Keine Nachricht passt zum Filter.</p>
      <table v-else>
        <thead>
          <tr>
            <th>Nr.</th>
            <th>Eingang</th>
            <th>Status</th>
            <th>Von</th>
            <th>An</th>
            <th>Inhalt</th>
          </tr>
        </thead>
        <tbody>
          <tr
            data-testid="nachricht-zeile"
            v-for="n in gefiltert"
            :key="n.id"
            :class="{ neu: ungelesen.has(n.id), aktiv: auswahlId === n.id, erledigt: n.status === 'erledigt' }"
            tabindex="0"
            @click="oeffne(n)"
            @keydown.enter="oeffne(n)"
          >
            <td class="nr">{{ n.lfd_nr }}</td>
            <td class="zeit">{{ fmtZeit(n.eingang_at) }}</td>
            <td><span data-testid="status" :class="['status-badge', n.status]">{{ n.status }}</span></td>
            <td>{{ n.von_funktion }}</td>
            <td>{{ n.an }}</td>
            <td class="inhalt">
              <span v-if="anzahlFotos(n)" class="foto-hinweis" :title="`${anzahlFotos(n)} Foto(s)`">📷 {{ anzahlFotos(n) }}</span>
              {{ n.inhalt }}
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <aside v-if="auswahl" class="detail card">
      <header>
        <h2>Nachricht Nr. {{ auswahl.lfd_nr }}</h2>
        <button class="secondary" @click="auswahlId = null">Schließen</button>
      </header>
      <p v-if="statusFehler" class="fehler">{{ statusFehler }}</p>
      <NachrichtDetail :nachricht="auswahl" darf-status :status-laeuft="statusLaeuft" @status="setzeStatus" />
    </aside>
  </div>
</template>

<style scoped>
.top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  padding: 10px 16px;
  background: var(--accent);
  color: var(--on-accent);
}
.einsatz {
  font-weight: 600;
}
.wer {
  margin-left: auto;
  font-size: 0.9rem;
}
.top .secondary {
  min-height: 34px;
  background: transparent;
  color: inherit;
  border-color: currentColor;
}
.erfassen {
  display: inline-flex;
  align-items: center;
  text-decoration: none;
  font-weight: 600;
}
.verbindung {
  font-size: 0.85rem;
  padding: 2px 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--on-accent) 20%, transparent);
}
.verbindung.getrennt {
  background: var(--on-accent);
  color: var(--accent);
  font-weight: 700;
}
.layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
  padding: 16px;
}
@media (min-width: 1000px) {
  .layout:has(.detail) {
    grid-template-columns: minmax(0, 3fr) minmax(360px, 2fr);
  }
  .detail {
    position: sticky;
    top: 16px;
    align-self: start;
    max-height: calc(100vh - 32px);
    overflow-y: auto;
  }
}
h2 {
  font-size: 1.15rem;
  margin: 0 0 10px;
}
.liste {
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
th,
td {
  padding: 10px;
  text-align: left;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}
th {
  font-size: 0.8rem;
  text-transform: uppercase;
  color: var(--muted);
}
tbody tr {
  cursor: pointer;
}
tbody tr:hover,
tr.aktiv {
  background: color-mix(in srgb, var(--text) 6%, transparent);
}
tr.neu {
  background: var(--neu-bg);
  font-weight: 600;
}
tr.neu td.nr {
  box-shadow: inset 4px 0 0 var(--accent);
}
tr.erledigt td:not(:nth-child(3)) {
  color: var(--muted);
}
.nr,
.zeit {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.inhalt {
  max-width: 480px;
  overflow-wrap: anywhere;
}
.detail header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.detail header h2 {
  margin: 0;
}
.detail .fehler {
  margin-bottom: 10px;
}
.foto-hinweis {
  margin-right: 6px;
  white-space: nowrap;
}
</style>
