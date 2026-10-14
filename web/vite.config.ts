import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// GitHub Pages serves the site from /<repository-name>/.
const base = process.env.VITE_BASE ?? "/stock-screener/";

export default defineConfig({
  base,
  plugins: [react()],
  test: {
    environment: "node",
  },
});
