<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import FilterLeiste from "@/shared/FilterLeiste.vue";
import { fmtZeit } from "@/shared/format";
import NachrichtDetail from "@/shared/NachrichtDetail.vue";
import type { Me, Nachricht } from "@/shared/types";
import { useEingang } from "@/shared/useEingang";

/** Mobile Lese-Ansicht: alle Nachrichten des Einsatzes live, ohne Status setzen oder Erfassen. */
defineProps<{ me: Me }>();
defineEmits<{ abmelden: [] }>();

const e = useEingang("Meldi – Beobachter", ["elw", "beobachter"]);
const { nachrichten, gefiltert, filter, ungelesen, anzahlUngelesen, verbindung } = e;

const auswahlId = ref<number | null>(null);
const auswahl = computed(() => nachrichten.value.find((n) => n.id === auswahlId.value) ?? null);

// Die Zurück-Taste des Handys schließt die Detailansicht, statt die Seite zu verlassen.
function oeffne(n: Nachricht) {
  auswahlId.value = n.id;
  e.gelesen(n.id);
  history.pushState({ detail: n.id }, "");
  window.scrollTo(0, 0);
}
const zurueck = () => history.back();
const onPopState = () => (auswahlId.value = null);
onMounted(() => window.addEventListener("popstate", onPopState));
onBeforeUnmount(() => window.removeEventListener("popstate", onPopState));
</script>

<template>
  <header class="top">
    <template v-if="auswahl">
      <button class="secondary" @click="zurueck">‹ Zurück</button>
      <strong class="titel">Nr. {{ auswahl.lfd_nr }}</strong>
    </template>
    <template v-else>
      <strong class="titel">{{ me.einsatz }}</strong>
      <button class="secondary" @click="$emit('abmelden')">Abmelden</button>
    </template>
    <span data-testid="verbindung" :class="['verbindung', verbindung]">{{ verbindung === "live" ? "● live" : verbindung === "verbinde" ? "…" : "● getrennt" }}</span>
  </header>

  <main v-if="auswahl" class="detail-wrap">
    <NachrichtDetail :nachricht="auswahl" />
  </main>

  <!-- v-show statt v-if: Scrollposition und Filter bleiben beim Zurückkehren erhalten -->
  <main v-show="!auswahl" class="liste">
    <p class="muted wer">
      {{ me.funktion }} · {{ me.name }}<template v-if="anzahlUngelesen"> · <strong>{{ anzahlUngelesen }} neu</strong></template>
    </p>
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
    <button v-for="n in gefiltert" :key="n.id" data-testid="nachricht-karte" :class="['karte', 'card', { neu: ungelesen.has(n.id) }]" @click="oeffne(n)">
      <span class="kopf">
        <strong>Nr. {{ n.lfd_nr }}</strong>
        <span class="muted">{{ fmtZeit(n.eingang_at) }}</span>
        <span data-testid="status" :class="['status-badge', n.status]">{{ n.status }}</span>
      </span>
      <span class="route">{{ n.von_funktion }} → {{ n.an }}</span>
      <span class="vorschau">
        <template v-if="n.anhaenge.some((a) => a.art === 'foto')">📷 </template>{{ n.inhalt }}
      </span>
    </button>
  </main>
</template>

<style scoped>
.top {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  padding-top: max(8px, env(safe-area-inset-top));
  background: var(--accent);
  color: var(--on-accent);
}
.titel {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.top .secondary {
  min-height: 44px;
  background: transparent;
  color: inherit;
  border-color: currentColor;
}
.verbindung {
  font-size: 0.8rem;
  padding: 2px 8px;
  border-radius: 999px;
  white-space: nowrap;
  background: color-mix(in srgb, var(--on-accent) 20%, transparent);
}
.verbindung.getrennt {
  background: var(--on-accent);
  color: var(--accent);
  font-weight: 700;
}
.liste,
.detail-wrap {
  padding: 12px 16px 32px;
  max-width: 720px;
  margin: 0 auto;
}
.liste {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.wer {
  margin: 0;
  font-size: 0.9rem;
}
.karte {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  min-height: 44px;
  padding: 12px 14px;
  text-align: left;
}
.karte.neu {
  background: var(--neu-bg);
  box-shadow: inset 4px 0 0 var(--accent);
}
.kopf {
  display: flex;
  align-items: center;
  gap: 10px;
}
.kopf .status-badge {
  margin-left: auto;
}
.route {
  overflow-wrap: anywhere;
  font-weight: 600;
}
.vorschau {
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
