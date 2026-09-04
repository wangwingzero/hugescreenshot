/**
 * 钉图窗口入口
 *
 * 这是钉图窗口的独立入口点，用于显示固定在屏幕上的截图。
 * 钉图窗口是置顶的无边框窗口，支持调整大小、移动和透明度调整。
 *
 * # 功能特性
 *
 * - 显示截图图像
 * - 支持拖拽移动窗口
 * - 支持调整窗口大小
 * - 支持透明度调整（20% - 100%）
 * - 双击关闭窗口
 * - 悬停显示控制栏
 */

import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { invoke } from "@tauri-apps/api/core";
import { convertFileSrc } from "@tauri-apps/api/core";

// 钉图窗口初始化信息接口
interface PinWindowInitInfo {
  label: string;
  imagePath: string;
  width: number;
  height: number;
  opacity: number;
}

// 全局状态
let windowLabel: string = "";
let lastClickTime: number = 0;
const DOUBLE_CLICK_THRESHOLD = 300; // 双击时间阈值（毫秒）
let hasInitInfo = false;

// Tauri 事件取消监听函数
const unlistenFns: (() => void)[] = [];

// DOM 元素
let imageElement: HTMLImageElement | null = null;
let loadingElement: HTMLElement | null = null;
let opacitySlider: HTMLInputElement | null = null;
let closeButton: HTMLButtonElement | null = null;
let dragRegion: HTMLElement | null = null;

/**
 * 初始化钉图窗口
 */
async function initPinWindow() {
  console.log("[Pin] 初始化钉图窗口...");

  // 尽早获取窗口标签，避免后续命令因空 label 失败
  windowLabel = getCurrentWindow().label;
  console.log("[Pin] 当前窗口标签:", windowLabel);

  // 获取 DOM 元素
  imageElement = document.querySelector(".pin-image");
  loadingElement = document.querySelector(".loading");
  opacitySlider = document.querySelector(".opacity-slider");
  closeButton = document.querySelector(".control-btn.close");
  dragRegion = document.querySelector(".drag-region");

  // 监听初始化事件
  const unlistenInit = await listen<PinWindowInitInfo>("pin-init", (event) => {
    const info = event.payload;
    console.log("[Pin] 收到初始化信息:", info);
    applyInitInfo(info);
  });
  unlistenFns.push(unlistenInit);

  // 监听透明度变化事件（从 Rust 端）
  const unlistenOpacity = await listen<number>("pin-opacity-changed", (event) => {
    const opacity = event.payload;
    console.log("[Pin] 透明度变化:", opacity);

    // 更新滑块值
    if (opacitySlider) {
      opacitySlider.value = String(Math.round(opacity * 100));
    }

    // 通过 CSS 设置整个窗口内容的透明度
    const pinApp = document.getElementById("pin-app");
    if (pinApp) {
      pinApp.style.opacity = String(opacity);
    }
  });
  unlistenFns.push(unlistenOpacity);

  // 设置事件监听
  setupEventListeners();

  // 双保险：主动拉取初始化数据，避免 pin-init 事件竞态丢失
  await loadInitInfoFromCommand();

  console.log("[Pin] 钉图窗口初始化完成");
}

/**
 * 应用初始化信息（幂等）
 */
function applyInitInfo(info: PinWindowInitInfo) {
  if (hasInitInfo) {
    return;
  }

  hasInitInfo = true;
  windowLabel = info.label || windowLabel;

  // 加载图像
  loadImage(info.imagePath);

  // 设置初始透明度
  if (opacitySlider) {
    opacitySlider.value = String(Math.round(info.opacity * 100));
  }

  const pinApp = document.getElementById("pin-app");
  if (pinApp) {
    pinApp.style.opacity = String(info.opacity);
  }
}

/**
 * 通过命令主动获取初始化信息（用于规避事件竞态）
 */
async function loadInitInfoFromCommand() {
  if (!windowLabel) {
    console.warn("[Pin] 缺少窗口标签，无法主动获取初始化信息");
    return;
  }

  try {
    const info = await invoke<PinWindowInitInfo>("get_pin_window_init", {
      label: windowLabel,
    });
    console.log("[Pin] 通过命令获取初始化信息:", info);
    applyInitInfo(info);
  } catch (error) {
    console.warn("[Pin] 主动获取初始化信息失败，等待事件:", error);
  }
}

/**
 * 加载图像
 */
function loadImage(imagePath: string) {
  if (!imageElement || !loadingElement) return;

  console.log("[Pin] 加载图像，原始路径:", imagePath);

  // 【性能优化】立即设置深色占位符背景，给用户即时视觉反馈
  document.body.style.backgroundColor = "#2a2a2a";
  imageElement.style.opacity = "0";
  imageElement.style.transition = "opacity 0.15s ease-in";

  // 显示加载状态
  loadingElement.classList.remove("hidden");

  // 转换路径为 asset:// 协议
  // 如果已经是 asset:// 协议，提取原始路径再转换
  let filePath = imagePath;
  if (imagePath.startsWith("asset://localhost/")) {
    filePath = imagePath.replace("asset://localhost/", "");
  } else if (imagePath.startsWith("asset://")) {
    filePath = imagePath.replace("asset://", "");
  }

  // 使用 Tauri 的 convertFileSrc 正确转换路径
  const assetUrl = convertFileSrc(filePath);
  console.log("[Pin] 转换后的 asset URL:", assetUrl);

  // 设置图像源
  imageElement.onload = () => {
    console.log("[Pin] 图像加载成功");
    loadingElement?.classList.add("hidden");
    // 【性能优化】图片加载完成后淡入显示，替换占位符
    if (imageElement) {
      imageElement.style.opacity = "1";
    }
  };

  imageElement.onerror = (e) => {
    console.error("[Pin] 图像加载失败:", e);
    if (loadingElement) {
      loadingElement.textContent = "图像加载失败";
    }
  };

  imageElement.src = assetUrl;
}

/**
 * 设置事件监听
 */
function setupEventListeners() {
  // 透明度滑块
  if (opacitySlider) {
    opacitySlider.addEventListener("input", handleOpacityChange);
  }

  // 关闭按钮
  if (closeButton) {
    closeButton.addEventListener("click", handleClose);
  }

  // 双击关闭
  if (dragRegion) {
    dragRegion.addEventListener("click", handleClick);
  }

  // 键盘事件（ESC 关闭）
  document.addEventListener("keydown", handleKeyDown);
}

/**
 * 处理透明度变化
 */
async function handleOpacityChange(e: Event) {
  const target = e.target as HTMLInputElement;
  const opacity = parseInt(target.value, 10) / 100;

  console.log("[Pin] 设置透明度:", opacity);

  // 立即应用 CSS 透明度（即时反馈）
  const pinApp = document.getElementById("pin-app");
  if (pinApp) {
    pinApp.style.opacity = String(opacity);
  }

  if (!windowLabel) {
    console.warn("[Pin] windowLabel 未初始化，跳过后端透明度同步");
    return;
  }

  try {
    // 调用 Rust 命令设置透明度（用于持久化和同步）
    await invoke("set_pin_opacity", {
      label: windowLabel,
      opacity: opacity,
    });
  } catch (error) {
    console.error("[Pin] 设置透明度失败:", error);
  }
}

/**
 * 处理点击事件（检测双击）
 */
function handleClick() {
  const now = Date.now();
  const timeDiff = now - lastClickTime;

  if (timeDiff < DOUBLE_CLICK_THRESHOLD) {
    // 双击 - 关闭窗口
    console.log("[Pin] 检测到双击，关闭窗口");
    handleClose();
  }

  lastClickTime = now;
}

/**
 * 处理关闭
 */
async function handleClose() {
  console.log("[Pin] 关闭钉图窗口");

  // 优先调用 Rust 命令，确保后端窗口状态和缓存一起清理
  if (windowLabel) {
    try {
      await invoke("close_pin_window", { label: windowLabel });
      return;
    } catch (error) {
      console.error("[Pin] Rust 命令关闭失败，尝试直接关闭:", error);
    }
  }

  // 兜底：直接关闭当前窗口（Rust 命令失败或未拿到 label 时）
  try {
    const currentWindow = getCurrentWindow();
    await currentWindow.close();
  } catch (error) {
    console.error("[Pin] 关闭窗口失败:", error);
  }
}

/**
 * 处理键盘事件
 */
function handleKeyDown(e: KeyboardEvent) {
  if (e.key === "Escape") {
    handleClose();
  }
}

/**
 * 清理所有事件监听器
 */
function cleanupEventListeners() {
  // 清理 DOM 事件监听
  if (opacitySlider) {
    opacitySlider.removeEventListener("input", handleOpacityChange);
  }
  if (closeButton) {
    closeButton.removeEventListener("click", handleClose);
  }
  if (dragRegion) {
    dragRegion.removeEventListener("click", handleClick);
  }
  document.removeEventListener("keydown", handleKeyDown);

  // 清理 Tauri 事件监听
  unlistenFns.forEach((fn) => fn());
  unlistenFns.length = 0;
}

// 页面卸载时清理事件监听
window.addEventListener("beforeunload", cleanupEventListeners);

// 启动初始化
initPinWindow().catch((e) => {
  console.error("[Pin] 初始化失败:", e);
});
