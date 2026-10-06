import { loadEnv } from "vite";
import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => ({
  plugins: [sveltekit()],
  server: {
    proxy: {
      "/api": {
        target: loadEnv(mode, ".", "").DEV_API_PROXY ?? "http://localhost:8000",
        changeOrigin: false,
      },
    },
  },
  test: {
    include: ["tests/**/*.test.ts"],
    environment: "jsdom",
    setupFiles: ["tests/setup.ts"],
    testTimeout: 30000,
    globals: false,
    server: {
      deps: {
        inline: [/@testing-library\/svelte/],
      },
    },
  },
  resolve: {
    conditions: ["browser"],
  },
}));
