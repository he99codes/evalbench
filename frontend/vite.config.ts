import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    watch: {
      // Needed for hot reload through Docker bind mounts on Windows/macOS.
      usePolling: process.env.VITE_USE_POLLING === "true",
    },
  },
});
