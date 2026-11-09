import { fileURLToPath, URL } from "node:url";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

const backend = process.env.MELDI_BACKEND ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        start: fileURLToPath(new URL("./index.html", import.meta.url)),
        melder: fileURLToPath(new URL("./melder/index.html", import.meta.url)),
        elw: fileURLToPath(new URL("./elw/index.html", import.meta.url)),
        beobachter: fileURLToPath(new URL("./beobachter/index.html", import.meta.url)),
      },
    },
  },
  test: {
    environment: "happy-dom",
    include: ["src/**/*.test.ts"],
    restoreMocks: true,
  },
  server: {
    host: "127.0.0.1",
    proxy: { "/api": { target: backend, ws: true } },
  },
});
