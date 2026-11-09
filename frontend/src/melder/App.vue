<script setup lang="ts">
import { computed, ref, watch } from "vue";
import LoginForm from "@/shared/LoginForm.vue";
import type { Me } from "@/shared/types";
import { useSitzung } from "@/shared/useSitzung";
import MessageForm from "./MessageForm.vue";

const { me, geladen, abgelaufen, angemeldet, abmelden } = useSitzung();

const darfErfassen = computed(() => !!me.value && me.value.rolle !== "beobachter");
/** Bleibt beim Ablauf der Sitzung stehen, damit das Formular samt Text bis zur neuen Anmeldung im Speicher bleibt. */
const formularFuer = ref<Me | null>(null);
watch(me, (m) => {
  if (m && m.rolle !== "beobachter") formularFuer.value = m;
  else if (!abgelaufen.value) formularFuer.value = null; // Wer sich selbst abmeldet, gibt das Handy vielleicht weiter
});
</script>

<template>
  <header class="top">
    <strong>Meldi</strong>
    <template v-if="me && darfErfassen">
      <span class="wer">{{ me.funktion }} · {{ me.name }}</span>
      <button class="secondary" @click="abmelden">Abmelden</button>
    </template>
  </header>
  <main v-if="geladen">
    <MessageForm v-if="formularFuer" v-show="darfErfassen" :me="formularFuer" />
    <LoginForm
      v-if="!darfErfassen"
      titel="Anmelden als Melder"
      rolle="melder"
      :hinweis="abgelaufen ? 'Anmeldung abgelaufen. Bitte neu anmelden, der eingegebene Text bleibt erhalten.' : undefined"
      @angemeldet="angemeldet"
    />
  </main>
</template>

<style scoped>
.top {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  padding-top: max(10px, env(safe-area-inset-top));
  background: var(--accent);
  color: var(--on-accent);
}
.wer {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.9rem;
}
.top .secondary {
  min-height: 44px;
  background: transparent;
  color: inherit;
  border-color: currentColor;
}
main {
  padding: 16px;
  max-width: 640px;
  margin: 0 auto;
}
</style>
