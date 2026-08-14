import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
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
});
