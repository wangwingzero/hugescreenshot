import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { resolve } from "path";
import { realpathSync } from "fs";

// @ts-expect-error process is a nodejs global
const host = process.env.TAURI_DEV_HOST;
const projectRoot = __dirname;
const projectRealRoot = realpathSync(projectRoot);

// https://vite.dev/config/
export default defineConfig(async () => ({
  root: projectRoot,
  plugins: [vue()],
  // 统一从仓库根目录读取 .env
  envDir: "..",

  // 路径别名
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
      "@resources": resolve(__dirname, "resources"),
    },
  },

  define: {
    __INTLIFY_JIT_COMPILATION__: true,
  },

  // 多页面配置
  base: './',
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, "index.html"),
        overlay: resolve(__dirname, "overlay.html"),
        pin: resolve(__dirname, "pin.html"),
        workbench: resolve(__dirname, "workbench.html"),
        mouseHighlight: resolve(__dirname, "mouse-highlight-overlay.html"),
        ocrResult: resolve(__dirname, "ocr-result.html"),
        recordingControl: resolve(__dirname, "recording-control.html"),
        recordingPreview: resolve(__dirname, "recording-preview.html"),
      },
    },
  },

  // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
  //
  // 1. prevent Vite from obscuring rust errors
  clearScreen: false,
  // 2. tauri expects a fixed port, fail if that port is not available
  server: {
    port: 1425,
    strictPort: true,
    host: host || false,
    fs: {
      // 锁定到项目目录，避免 Windows 错误 cwd 时扫到系统目录
      allow: [projectRoot, projectRealRoot],
    },
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      // 3. tell Vite to ignore watching `src-tauri`
      ignored: ["**/src-tauri/**"],
    },
  },
}));
