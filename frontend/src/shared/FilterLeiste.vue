<script setup lang="ts">
import { computed, ref } from "vue";
import { type Filter, STATUS, type StatusFilter } from "./useEingang";

const props = defineProps<{
  filter: Filter;
  absender: string[];
  empfaenger: string[];
  anzahl: number;
  gesamt: number;
  aktiv: boolean;
}>();
defineEmits<{ zuruecksetzen: [] }>();

/** Auf dem Handy eingeklappt, am Desktop immer sichtbar (siehe CSS). */
const offen = ref(false);
const statusWahl: { wert: StatusFilter; label: string }[] = [
  { wert: "alle", label: "alle" },
  { wert: "offen", label: "offen" },
  ...STATUS.map((s) => ({ wert: s, label: s })),
];
const anzahlAktiv = computed(
  () => [props.filter.status !== "alle", props.filter.von, props.filter.an, props.filter.ab, props.filter.bis].filter(Boolean).length,
);
</script>

<template>
  <div class="filterleiste">
    <div class="suche">
      <input v-model="filter.text" type="search" placeholder="Suchen: Nr., Von, An, Inhalt" aria-label="Suchen" />
      <button type="button" class="secondary umschalten" :aria-expanded="offen" @click="offen = !offen">
        Filter<template v-if="anzahlAktiv"> ({{ anzahlAktiv }})</template> {{ offen ? "▴" : "▾" }}
      </button>
    </div>
    <div :class="['weitere', { offen }]">
      <div class="chips" role="group" aria-label="Status">
        <button
          v-for="s in statusWahl"
          :key="s.wert"
          type="button"
          :class="['chip', { aktiv: filter.status === s.wert }]"
          :title="s.wert === 'offen' ? 'neu und gesichtet' : undefined"
          @click="filter.status = s.wert"
        >
          {{ s.label }}
        </button>
      </div>
      <label>
        Von
        <select v-model="filter.von">
          <option value="">alle</option>
          <option v-for="v in absender" :key="v" :value="v">{{ v }}</option>
        </select>
      </label>
      <label>
        An
        <select v-model="filter.an">
          <option value="">alle</option>
          <option v-for="a in empfaenger" :key="a" :value="a">{{ a }}</option>
        </select>
      </label>
      <label>
        Eingang ab
        <input v-model="filter.ab" type="datetime-local" />
      </label>
      <label>
        bis
        <input v-model="filter.bis" type="datetime-local" />
      </label>
    </div>
    <p class="anzahl muted">
      {{ anzahl }} von {{ gesamt }}
      <button v-if="aktiv" type="button" class="link" @click="$emit('zuruecksetzen')">Filter zurücksetzen</button>
    </p>
  </div>
</template>

<style scoped>
.filterleiste {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}
.suche {
  display: flex;
  gap: 8px;
}
.suche input {
  flex: 1;
  min-height: 44px;
  padding: 8px 12px;
}
.umschalten {
  min-height: 44px;
  white-space: nowrap;
}
.weitere {
  display: none;
  flex-direction: column;
  gap: 10px;
}
.weitere.offen {
  display: flex;
}
label {
  font-weight: 400;
  font-size: 0.85rem;
  color: var(--muted);
  gap: 4px;
}
select,
label input {
  min-height: 44px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--text);
  font-size: 1rem;
}
.anzahl {
  margin: 0;
  font-size: 0.85rem;
}
.link {
  min-height: 44px;
  margin-left: 8px;
  padding: 0;
  border: none;
  background: none;
  color: var(--accent);
  text-decoration: underline;
  font-size: inherit;
}
@media (min-width: 900px) {
  .umschalten {
    display: none;
  }
  .weitere,
  .weitere.offen {
    display: flex;
    flex-direction: row;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: 10px 14px;
  }
  .weitere .chips {
    align-self: flex-end;
  }
  select {
    min-width: 160px;
  }
}
</style>
