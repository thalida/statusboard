import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import { defineConfig } from "vitest/config";

export default defineConfig({
  // The router plugin writes src/routeTree.gen.ts from the route
  // files. It runs before react(), which compiles what it wrote.
  plugins: [
    tanstackRouter({
      target: "react",
      // A test beside a route is not a route. Without this the
      // plugin warns on each one and skips it anyway.
      routeFileIgnorePattern: "\\.test\\.tsx?$",
    }),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg"],
      manifest: {
        name: "Statusboard",
        short_name: "Statusboard",
        description: "Monitor the status pages of services in one place.",
        theme_color: "navy",
        background_color: "white",
        display: "standalone",
        start_url: "/",
        icons: [
          {
            src: "/icon.svg",
            sizes: "any",
            type: "image/svg+xml",
            purpose: "any maskable",
          },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,ico}"],
      },
    }),
    react(),
    tailwindcss(),
  ],
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
