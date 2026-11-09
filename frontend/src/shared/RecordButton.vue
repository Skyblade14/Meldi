<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { api, ApiError } from "./api";
import { fmtSek } from "./format";
import type { Feld, TranscribeResult } from "./types";
import { mikrofonVerfuegbar, useRecorder } from "./useRecorder";

const props = defineProps<{ feld: Feld; label?: string }>();
const emit = defineEmits<{ result: [TranscribeResult]; belegt: [boolean] }>();

const rec = useRecorder({ maxSekunden: props.feld === "an" ? 10 : 60 });
const erkennt = ref(false);
const fehler = ref<string | null>(mikrofonVerfuegbar());
const info = ref<string | null>(null);

const startet = ref(false); // Das Betriebssystem fragt evtl. erst nach der Mikrofon-Erlaubnis

const phase = computed(() => (erkennt.value ? "processing" : rec.state.value));
watch([phase, startet], () => emit("belegt", startet.value || phase.value !== "idle"));

async function klick() {
  if (phase.value === "processing") return;
  if (phase.value === "recording") {
    rec.stop();
    return;
  }
  fehler.value = null;
  info.value = null;
  let fertig: Promise<Blob | null>;
  startet.value = true;
  try {
    ({ fertig } = await rec.start());
  } catch (e) {
    startet.value = false;
    fehler.value =
      e instanceof DOMException && e.name === "NotAllowedError"
        ? "Mikrofon-Zugriff verweigert – in den Browser-Einstellungen erlauben"
        : "Mikrofon konnte nicht gestartet werden";
    return;
  }
  startet.value = false;
  const audio = await fertig;
  if (!audio) return;
  erkennt.value = true;
  try {
    const r = await api.transcribe(audio, props.feld, rec.spur.value);
    if (!r.text) fehler.value = "Nichts erkannt – bitte nochmal sprechen";
    else info.value = `erkannt in ${fmtSek(r.verarbeitung_sekunden + r.warte_sekunden)} · ${r.modell}`;
    emit("result", r);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) fehler.value = "Anmeldung war abgelaufen – bitte nochmal sprechen";
    else fehler.value = e instanceof Error ? e.message : "Fehler bei der Erkennung";
  } finally {
    erkennt.value = false;
  }
}
</script>

<template>
  <div class="rec">
    <button
      type="button"
      class="rec-btn"
      :class="phase"
      :disabled="phase === 'processing' || !!mikrofonVerfuegbar()"
      :aria-label="phase === 'recording' ? 'Aufnahme beenden' : (label ?? 'Sprechen')"
      @click="klick"
    >
      <span v-if="phase === 'idle'" class="rec-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
          <path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z" />
        </svg>
      </span>
      <span v-else-if="phase === 'recording'" class="rec-stop" aria-hidden="true"></span>
      <span v-else class="spinner" aria-hidden="true"></span>
      <span class="rec-text">
        <template v-if="phase === 'idle'">{{ label ?? "Sprechen" }}</template>
        <template v-else-if="phase === 'recording'">Stopp · {{ Math.floor(rec.sekunden.value) }} s</template>
        <template v-else>Erkenne …</template>
      </span>
      <span v-if="phase === 'recording'" class="pegel" :style="{ transform: `scaleX(${rec.pegel.value})` }"></span>
    </button>
    <p v-if="fehler" class="rec-msg fehler">{{ fehler }}</p>
    <p v-else-if="info" class="rec-msg">{{ info }}</p>
  </div>
</template>

<style scoped>
.rec {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.rec-btn {
  position: relative;
  overflow: hidden;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 52px;
  padding: 0 18px;
  border-radius: var(--radius);
  border: 2px solid var(--accent);
  background: var(--surface);
  color: var(--accent);
  font-weight: 700;
  font-size: 1rem;
}
.rec-btn.recording {
  background: var(--accent);
  color: var(--on-accent);
  animation: puls 1.2s ease-in-out infinite;
}
.rec-btn.processing {
  border-color: var(--border);
  color: var(--muted);
}
.rec-btn:disabled {
  opacity: 0.6;
}
.rec-stop {
  width: 16px;
  height: 16px;
  border-radius: 3px;
  background: currentColor;
}
.pegel {
  position: absolute;
  left: 0;
  bottom: 0;
  height: 5px;
  width: 100%;
  background: var(--on-accent);
  opacity: 0.8;
  transform-origin: left;
  transition: transform 80ms linear;
}
.rec-msg {
  margin: 0;
  font-size: 0.8rem;
  color: var(--muted);
}
.rec-msg.fehler {
  color: var(--danger);
}
.spinner {
  width: 18px;
  height: 18px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: dreh 0.8s linear infinite;
}
@keyframes dreh {
  to {
    transform: rotate(360deg);
  }
}
@keyframes puls {
  50% {
    box-shadow: 0 0 0 6px color-mix(in srgb, var(--accent) 30%, transparent);
  }
}
</style>
