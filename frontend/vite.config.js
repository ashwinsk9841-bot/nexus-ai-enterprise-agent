import { defineConfig } from "vite";
import { cpSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

// NEXUS uses classic <script> tags (shared globals) and loads page templates
// at runtime via fetch("./src/pages/<page>.html"). Vite only bundles
// statically-referenced files, so we must copy src/js and src/pages verbatim
// into the production build (dist/). The stylesheet is still bundled+minified
// by Vite into dist/assets.
function nexusCopyStatic() {
  return {
    name: "nexus-copy-static",
    closeBundle() {
      for (const dir of ["js", "pages"]) {
        const src = resolve(__dirname, "src", dir);
        if (!existsSync(src)) continue;
        const out = resolve(__dirname, "dist", "src", dir);
        cpSync(src, out, { recursive: true });
        console.log(`[nexus] copied src/${dir} -> ${out}`);
      }
    },
  };
}

export default defineConfig({
  plugins: [nexusCopyStatic()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});