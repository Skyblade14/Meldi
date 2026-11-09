<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { api } from "@/shared/api";
import { fmtZeit } from "@/shared/format";
import type { AktiveAnmeldung } from "@/shared/types";

defineEmits<{ schliessen: [] }>();

const AKTUALISIEREN_MS = 15000;
const liste = ref<AktiveAnmeldung[]>([]);
const fehler = ref<string | null>(null);
const ROLLEN = { melder: "Melder", elw: "ELW", beobachter: "Beobachter" } as const;

async function laden() {
  try {
    liste.value = await api.anmeldungen();
    fehler.value = null;
  } catch (e) {
    fehler.value = e instanceof Error ? e.message : String(e);
  }
}

let timer: number | undefined;
onMounted(() => {
  laden();
  timer = window.setInterval(laden, AKTUALISIEREN_MS);
});
onUnmounted(() => window.clearInterval(timer));
</script>

<template>
  <aside class="card panel">
    <header>
      <h2>Angemeldet ({{ liste.length }})</h2>
      <button class="secondary" @click="$emit('schliessen')">Schließen</button>
    </header>
    <p v-if="fehler" class="fehler">{{ fehler }}</p>
    <table>
      <thead>
        <tr><th>Name</th><th>Rolle</th><th>Funktion</th><th>Seit</th></tr>
      </thead>
      <tbody>
        <tr v-for="(a, i) in liste" :key="i">
          <td>{{ a.name }}</td>
          <td>{{ ROLLEN[a.rolle] }}</td>
          <td>{{ a.funktion }}</td>
          <td>{{ fmtZeit(a.angemeldet_at) }}</td>
        </tr>
      </tbody>
    </table>
  </aside>
</template>

<style scoped>
.panel {
  position: fixed;
  top: 64px;
  right: 16px;
  z-index: 20;
  width: min(560px, calc(100vw - 32px));
  max-height: calc(100vh - 96px);
  overflow: auto;
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
h2 {
  margin: 0;
  font-size: 1.1rem;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 8px;
}
th,
td {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}
</style>
