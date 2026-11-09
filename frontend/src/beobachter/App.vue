<script setup lang="ts">
import LoginForm from "@/shared/LoginForm.vue";
import type { Me } from "@/shared/types";
import { useSitzung } from "@/shared/useSitzung";
import Lage from "./Lage.vue";

const { me, geladen, abgelaufen, angemeldet, abmelden } = useSitzung();

const darfLesen = (m: Me | null) => m?.rolle === "beobachter" || m?.rolle === "elw";
</script>

<template>
  <template v-if="geladen">
    <Lage v-if="me && darfLesen(me)" :me="me" @abmelden="abmelden" />
    <main v-else class="login-wrap">
      <LoginForm
        titel="Beobachter – Anmeldung"
        rolle="beobachter"
        :hinweis="abgelaufen ? 'Anmeldung abgelaufen. Bitte neu anmelden.' : undefined"
        @angemeldet="angemeldet"
      />
    </main>
  </template>
</template>

<style scoped>
.login-wrap {
  padding: 16px;
}
</style>
