<script setup lang="ts">
const ansichten = [
  { href: "/melder/", titel: "Melder", text: "Nachrichten erfassen, am Handy" },
  { href: "/elw/", titel: "ELW", text: "Eingang sichten und bearbeiten, am Rechner" },
  { href: "/beobachter/", titel: "Beobachter", text: "Alle Nachrichten mitlesen, am Handy" },
];
</script>

<template>
  <main>
    <h1>Meldi</h1>
    <p class="muted">Bitte die Ansicht wählen.</p>
    <nav>
      <a v-for="a in ansichten" :key="a.href" :href="a.href" class="card kachel">
        <strong>{{ a.titel }}</strong>
        <span class="muted">{{ a.text }}</span>
      </a>
    </nav>
  </main>
</template>

<style scoped>
main {
  max-width: 480px;
  margin: 0 auto;
  padding: 24px 16px;
}
h1 {
  margin: 0 0 4px;
}
nav {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}
.kachel {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 72px;
  justify-content: center;
  color: var(--text);
  text-decoration: none;
}
.kachel strong {
  font-size: 1.25rem;
}
</style>
