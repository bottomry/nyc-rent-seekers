import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = dirname(fileURLToPath(import.meta.url));

export default defineConfig(({ mode }) => {
  const isDemo = mode === "demo";
  return {
    root: "web",
    publicDir: "public",
    base: "./",
    plugins: isDemo ? [viteSingleFile()] : [],
    build: {
      outDir: isDemo ? resolve(rootDir, "dist") : resolve(rootDir, "dist/app"),
      emptyOutDir: !isDemo,
      assetsInlineLimit: isDemo ? 100_000_000 : 4096,
      cssCodeSplit: !isDemo,
      rollupOptions: isDemo
        ? {
            input: resolve(rootDir, "web/demo.html"),
            output: {
              entryFileNames: "nyc-rent-seekers-demo.js",
              assetFileNames: "nyc-rent-seekers-demo.[ext]",
            },
          }
        : {
            input: resolve(rootDir, "web/index.html"),
          },
    },
    server: {
      port: 5179,
      strictPort: true,
    },
  };
});
