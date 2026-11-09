<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "./api";
import type { Funktion, Me, Rolle } from "./types";

const props = defineProps<{ titel: string; rolle: Rolle; standardFunktion?: string; hinweis?: string }>();
const emit = defineEmits<{ angemeldet: [Me] }>();

const name = ref("");
const funktion = ref(props.standardFunktion ?? "");
const funktionen = ref<Funktion[]>([]);
const fehler = ref<string | null>(null);
const laeuft = ref(false);
const mitFunktion = props.rolle !== "beobachter";

onMounted(async () => {
  if (!mitFunktion) return;
  try {
    funktionen.value = await api.funktionen();
  } catch (e) {
    fehler.value = e instanceof Error ? e.message : String(e);
  }
});

async function anmelden() {
  fehler.value = null;
  laeuft.value = true;
  try {
    emit("angemeldet", await api.login(name.value, props.rolle, mitFunktion ? funktion.value : undefined));
  } catch (e) {
    fehler.value = e instanceof Error ? e.message : String(e);
  } finally {
    laeuft.value = false;
  }
}
</script>

<template>
  <form class="card login" @submit.prevent="anmelden">
    <h1>{{ titel }}</h1>
    <p v-if="hinweis" class="fehler">{{ hinweis }}</p>
    <label>
      Name
      <input v-model="name" autocomplete="name" autocapitalize="words" required />
    </label>
    <label v-if="mitFunktion">
      Funktion
      <input v-model="funktion" list="funktionen" placeholder="z.B. EA Brand" required />
      <datalist id="funktionen">
        <option v-for="f in funktionen" :key="f.id" :value="f.name" />
      </datalist>
    </label>
    <div v-if="mitFunktion && funktionen.length" class="chips">
      <button
        v-for="f in funktionen"
        :key="f.id"
        type="button"
        class="chip"
        :class="{ aktiv: funktion === f.name }"
        @click="funktion = f.name"
      >
        {{ f.name }}
      </button>
    </div>
    <p v-if="fehler" class="fehler">{{ fehler }}</p>
    <button class="primary" :disabled="laeuft">Anmelden</button>
  </form>
</template>

<style scoped>
.login {
  max-width: 420px;
  margin: 24px auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
h1 {
  margin: 0;
  font-size: 1.4rem;
}
</style>
