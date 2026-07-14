import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
//
// Three independent HTML entry points, deliberately not one SPA shell:
// `index.html` is the static Welcome/landing gate (no React, real page
// load, shown once per browser); `privacy/index.html` is the static
// Privacy Policy (linked from Welcome's consent checkbox); `app/index.html`
// mounts the React SPA that owns everything after "Say hello" — Home,
// Response, Crisis Support. See frontend/README.md for why this split
// exists.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      input: {
        welcome: path.resolve(__dirname, "index.html"),
        privacy: path.resolve(__dirname, "privacy/index.html"),
        app: path.resolve(__dirname, "app/index.html"),
      },
    },
  },
});
