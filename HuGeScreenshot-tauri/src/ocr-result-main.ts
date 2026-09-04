/**
 * OCR 结果弹窗入口
 *
 * 独立的 OCR 结果显示窗口，参考 Python 版本的 OCRResultWindow
 * 功能：
 * - 显示 OCR 识别结果
 * - 复制文本
 * - 文本排版（合并单行、智能分段等）
 * - 翻译功能
 */

import { createApp } from "vue";
import { createPinia } from "pinia";
import OcrResultApp from "./OcrResultApp.vue";
// 引入主题样式，与工作台共享一致的 CSS 变量和基础样式
import "./styles/theme.css";
import { initializeTheme } from "./composables/useTheme";

// 在 Vue 挂载前初始化主题，防止白屏闪烁
initializeTheme();

const app = createApp(OcrResultApp);
const pinia = createPinia();

app.use(pinia);
app.mount("#app");
