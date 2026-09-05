import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // Matches tsconfig.json's "@/*" path. TypeScript only checks types;
    // Vite needs its own alias to resolve the specifier at build time.
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    // The worktree's reserved port, and the host the API already
    // trusts. See bin/worktree-env.py, which writes both.
    port: Number(process.env.CLIENT_PORT) || 5173,
    host: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
