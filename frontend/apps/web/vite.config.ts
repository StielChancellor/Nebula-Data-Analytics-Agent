import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Brand-aware build: `vite build --mode <brand>` loads .env.<brand>
// from this directory so VITE_BRAND + VITE_API_BASE are baked in.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  return {
    plugins: [react()],
    resolve: {
      alias: [
        { find: "@insnav/locale", replacement: path.resolve(__dirname, "../../packages/locale/src/index.ts") },
        { find: "@insnav/brand-runtime", replacement: path.resolve(__dirname, "../../packages/brand-runtime/src/index.ts") },
        { find: "@insnav/brand-static", replacement: path.resolve(__dirname, "../../packages/brand-static/src/index.ts") },
        { find: "@insnav/api-client", replacement: path.resolve(__dirname, "../../packages/api-client/src/index.ts") },
        { find: "@insnav/ui-kit", replacement: path.resolve(__dirname, "../../packages/ui-kit/src/index.ts") },
        { find: "@insnav/charts", replacement: path.resolve(__dirname, "../../packages/charts/src/index.ts") },
        { find: "@insnav/pivot", replacement: path.resolve(__dirname, "../../packages/pivot/src/index.ts") },
        { find: "@insnav/dashboards", replacement: path.resolve(__dirname, "../../packages/dashboards/src/index.ts") },
        { find: "@insnav/chat", replacement: path.resolve(__dirname, "../../packages/chat/src/index.ts") },
        { find: "@insnav/share-embed", replacement: path.resolve(__dirname, "../../packages/share-embed/src/index.ts") },
        { find: "@insnav/auth", replacement: path.resolve(__dirname, "../../packages/auth/src/index.ts") },
      ],
    },
    server: {
      port: 5173,
      proxy: {
        // Proxy /api/* to local backend during dev so we hit a single origin (no CORS)
        "/api": {
          target: env.VITE_API_BASE || "http://localhost:8000",
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ""),
        },
      },
    },
    build: {
      outDir: `dist-${mode}`,
      sourcemap: true,
    },
  };
});
