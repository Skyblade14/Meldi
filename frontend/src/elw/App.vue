<script setup lang="ts">
import LoginForm from "@/shared/LoginForm.vue";
import { useSitzung } from "@/shared/useSitzung";
import Eingang from "./Eingang.vue";

const { me, geladen, abgelaufen, angemeldet, abmelden } = useSitzung();
</script>

<template>
  <template v-if="geladen">
    <Eingang v-if="me && me.rolle === 'elw'" :me="me" @abmelden="abmelden" />
    <main v-else class="login-wrap">
      <LoginForm
        titel="ELW – Anmeldung"
        rolle="elw"
        standard-funktion="ELW"
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
