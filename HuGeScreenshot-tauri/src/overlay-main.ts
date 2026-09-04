/**
 * 截图覆盖窗口入口
 *
 * 功能：
 * - 全屏覆盖截图选区
 * - 底部绘图工具栏（矩形、箭头、画笔等）
 * - 侧边功能工具栏（撤销、颜色、保存等）
 * - 支持复制到剪贴板和保存到文件
 *
 * 焦点管理（关键！）：
 * - 使用 capture 阶段监听键盘事件，确保能捕获 Escape 等按键
 * - 初始化完成后调用 overlay_ready 通知后端
 * - 后端会通过 AttachThreadInput 强制获取前台焦点
 *
 * 屏幕冻结（关键！）：
 * - 在显示 overlay 时先捕获全屏截图
 * - 将截图设置为背景，实现"冻结屏幕"效果
 * - 用户在静态背景上选择区域，而不是实时桌面
 */

import { listen, emit } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { WebviewWindow } from "@tauri-apps/api/webviewWindow";
import { invoke, convertFileSrc } from "@tauri-apps/api/core";
import { save } from "@tauri-apps/plugin-dialog";
import { writeFile, readFile } from "@tauri-apps/plugin-fs";
import { writeText } from "@tauri-apps/plugin-clipboard-manager";
import { formatOcrUserError } from "@/utils/ocrError";
import { replaceTempImageExtension } from "@/utils/tempImagePath";
import {
  shouldAutoOcrOnSelection,
  shouldDeactivateOverlaySessionForOcrTeardown,
  shouldDeferOcrUntilCaptureComplete,
  shouldDestroyCurrentOverlayAfterTeardownFailure,
  shouldHideOverlayBeforeCachedOcrResult,
  overlayOcrCommandName,
  shouldRunOcrInBackendAfterOverlayHidden,
  shouldRestoreOverlayFocus,
  shouldRestoreOverlayFocusAfterCapture,
  shouldScheduleQueuedOcrAfterCapture,
  shouldTeardownOverlayBeforeBackendOcr,
  waitForOverlayVisualTeardown,
} from "@/utils/ocrOverlaySafety";

// ============================================
// 类型定义
// ============================================

interface MonitorInfo {
  monitorId: number;
  position: { x: number; y: number };
  size: { width: number; height: number };
  scaleFactor: number;
  name: string;
}

interface SelectionState {
  isSelecting: boolean;
  hasSelection: boolean;
  startX: number;
  startY: number;
  endX: number;
  endY: number;
}

// 选区编辑状态
type SelectionEditMode = "idle" | "moving" | "resizing";
type SelectionResizeHandle = "n" | "s" | "e" | "w" | "nw" | "ne" | "sw" | "se" | "";

interface CaptureResult {
  path: string;
  width: number;
  height: number;
  dpr: number;
  imageHash?: string;
}

// ============================================
// 静态快照相关类型（对应 Rust: src-tauri/src/screenshot/snapshot.rs）
// ============================================

/**
 * 单个显示器的快照信息
 * 
 * 描述单个显示器在虚拟桌面中的位置和属性，
 * 用于多显示器场景下的正确渲染和坐标计算。
 * 
 * 注意：所有坐标和尺寸都是物理像素值
 */
interface MonitorSnapshot {
  /** 显示器 ID（主显示器通常是 0） */
  monitor_id: number;
  /** 显示器左上角的 X 坐标（物理像素，可能为负值） */
  x: number;
  /** 显示器左上角的 Y 坐标（物理像素，可能为负值） */
  y: number;
  /** 显示器宽度（物理像素） */
  width: number;
  /** 显示器高度（物理像素） */
  height: number;
  /** 此显示器的设备像素比 (DPR) */
  dpr: number;
}

/**
 * 静态快照就绪事件的 payload
 * 
 * 当 Rust 后端完成静态快照捕获后，通过 `snapshot-ready` 事件发送此数据。
 * 前端收到后应加载快照图片并显示为 Canvas 背景。
 * 
 * **Validates: Requirements 3.2, 3.3**
 */
interface SnapshotReadyPayload {
  /** 临时快照文件的绝对路径（需要用 convertFileSrc 转换） */
  path: string;
  /** 合并后快照的总宽度（物理像素） */
  width: number;
  /** 合并后快照的总高度（物理像素） */
  height: number;
  /** 主显示器的设备像素比 (DPR) */
  dpr: number;
  /** 各显示器的详细信息 */
  monitors: MonitorSnapshot[];
}

// 保存截图时的元数据
interface SaveScreenshotMetadata {
  captureMode?: string;
  monitorId?: number;
  hasAnnotations?: boolean;
  appName?: string;
  windowTitle?: string;
}

// 保存截图并添加历史记录的结果
interface SaveScreenshotResult {
  filePath: string;
  historyId: number;
  thumbnailPath?: string;
}

// 绘图工具枚举
type DrawTool = "none" | "rect" | "ellipse" | "arrow" | "line" | "pen" | "marker" | "text" | "mosaic" | "step";

// 绘图操作类型
interface DrawOperation {
  id: number;
  tool: DrawTool;
  color: string;
  width: number;
  points: Array<{ x: number; y: number }>;
  text?: string;
  stepNumber?: number;
}

// 边界矩形
interface BoundingRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

// 编辑模式
type EditMode = "idle" | "drawing" | "selected" | "moving" | "resizing";

// 缩放手柄
type ResizeHandle = "tl" | "tr" | "bl" | "br" | "";

// 撤销操作类型
interface UndoAction {
  type: "create" | "move" | "resize" | "delete";
  operationId: number;
  operation?: DrawOperation;
  previousPoints?: Array<{ x: number; y: number }>;
  newPoints?: Array<{ x: number; y: number }>;
}

// OCR 相关类型（对应 Rust: src-tauri/src/commands/sidecar_cmd.rs）
interface OcrBox {
  text: string;
  confidence: number;
  box_coords: number[][];  // Rust 返回的字段名
}

interface OcrResult {
  text: string;
  boxes: OcrBox[];
  elapse: number;
  engine?: string;
}

// OCR 请求选项（控制是否打开面板/复制/提示）
interface OcrRequestOptions {
  openPanel: boolean;
  copyText: boolean;
  showToast: boolean;
  reason: "auto" | "manual";
}

// 内联文字编辑器状态（与 Python 版本一致）
interface InlineTextEditor {
  active: boolean;
  position: { x: number; y: number };
  text: string;
  cursorPos: number;
  cursorVisible: boolean;
  color: string;
  fontSize: number;
  editingItem: DrawOperation | null;  // 编辑已有文字时的引用
  inputElement: HTMLInputElement | null;  // 真实 input 元素，用于 IME 输入
  isComposing: boolean;  // 是否正在 IME 合成输入中
}

// ============================================
// 焦点变化事件类型（对应 Rust: src-tauri/src/window/focus_manager.rs）
// ============================================

/**
 * 焦点变化事件载荷
 * 
 * 用于窗口间焦点状态通信。当窗口获得或失去焦点时，
 * 通过 Tauri Event 广播此状态，其他窗口可以监听并响应。
 * 
 * **Validates: Requirements 5.1, 5.2, 5.3**
 */
interface FocusChangeEvent {
  /** 窗口标签（唯一标识符），如 "overlay-0", "ocr-result" 等 */
  windowLabel: string;
  /** 是否获得焦点 */
  isFocused: boolean;
  /** 事件时间戳（Unix 毫秒），用于事件排序和去重 */
  timestamp: number;
}


// ============================================
// 全局状态
// ============================================

let monitorInfo: MonitorInfo | null = null;
let selectionState: SelectionState = {
  isSelecting: false,
  hasSelection: false,
  startX: 0,
  startY: 0,
  endX: 0,
  endY: 0,
};

// 选区编辑状态
let selectionEditMode: SelectionEditMode = "idle";
let selectionResizeHandle: SelectionResizeHandle = "";
let selectionEditStartX = 0;
let selectionEditStartY = 0;
let selectionOriginalRect: BoundingRect | null = null;
let selectionEditPreviousCapture: CaptureResult | null = null;

// 选区编辑配置
const SELECTION_HANDLE_MARGIN = 6;
const SELECTION_MIN_SIZE = 10;

// 截图捕获节流与队列
let captureInProgress = false;
let queuedCaptureRect: BoundingRect | null = null;
let pendingOcrAfterCapture: OcrRequestOptions | null = null;
let queuedCaptureTriggerOcr = false;

// OCR 状态
let ocrInProgress = false;
let pendingOcrAfterCurrent: OcrRequestOptions | null = null;
// 自动 OCR 延迟触发，给复制等高优先动作让路
const AUTO_OCR_DEFER_MS = 350;
let autoOcrTimer: number | null = null;
let suspendAutoOcr = false;

const OCR_REQUEST_AUTO: OcrRequestOptions = {
  openPanel: false,
  copyText: false,
  showToast: true,
  reason: "auto",
};

const OCR_REQUEST_MANUAL: OcrRequestOptions = {
  openPanel: true,
  copyText: true,
  showToast: true,
  reason: "manual",
};

// 选区完成后自动 OCR
const AUTO_OCR_ON_SELECTION = shouldAutoOcrOnSelection();

let captureResult: CaptureResult | null = null;
let lastOcrResult: OcrResult | null = null;
let lastOcrCaptureKey: string | null = null;
let lastOcrImagePath: string | null = null;
let currentTool: DrawTool = "none";
let currentColor = "#FF0000";
let currentWidth = 3;
let currentWidthLevel = 2;  // 粗细级别 (1-10)

// 每个工具独立的颜色记忆（与 Python 版本一致）
const toolColorMemory: Map<DrawTool, string> = new Map([
  ["rect", "#FF0000"],      // 矩形 - 红色
  ["ellipse", "#0066FF"],   // 椭圆 - 蓝色
  ["arrow", "#FF0000"],     // 箭头 - 红色
  ["line", "#FF0000"],      // 直线 - 红色
  ["pen", "#FF0000"],       // 画笔 - 红色
  ["marker", "#FFCC00"],    // 高亮 - 黄色
  ["text", "#FF0000"],      // 文字 - 红色
  ["mosaic", "#666666"],    // 马赛克 - 灰色
  ["step", "#FF0000"],      // 编号 - 红色
]);

// 每个工具独立的粗细记忆（级别 1-10）
const toolWidthMemory: Map<DrawTool, number> = new Map([
  ["rect", 2],      // 矩形 - 默认级别 2
  ["ellipse", 2],   // 椭圆 - 默认级别 2
  ["arrow", 2],     // 箭头 - 默认级别 2
  ["line", 2],      // 直线 - 默认级别 2
  ["pen", 2],       // 画笔 - 默认级别 2
  ["marker", 5],    // 高亮 - 默认级别 5（较粗）
  ["text", 4],      // 文字 - 默认级别 4
  ["mosaic", 3],    // 马赛克 - 默认级别 3
  ["step", 3],      // 编号 - 默认级别 3
]);

// 绘图状态
let isDrawing = false;
let drawStartX = 0;
let drawStartY = 0;
let currentDrawPoints: Array<{ x: number; y: number }> = [];
let drawOperations: DrawOperation[] = [];
let undoStack: UndoAction[] = [];
let redoStack: UndoAction[] = [];
let stepCounter = 1;

// 操作ID计数器
let operationIdCounter = 0;

// 编辑状态
let editMode: EditMode = "idle";
let selectedOperationId: number | null = null;
let hoveredOperationId: number | null = null;
let activeResizeHandle: ResizeHandle = "";

// 移动/缩放时的起始位置
let editStartX = 0;
let editStartY = 0;
let originalBounds: BoundingRect | null = null;
let originalPoints: Array<{ x: number; y: number }> = [];

// 窗口探测状态（与 Rust WindowInfo 对应，使用 camelCase）
interface DetectedWindow {
  hwnd: number;
  title: string;
  className: string;
  rect: { x: number; y: number; width: number; height: number };
  physicalRect: { x: number; y: number; width: number; height: number };
}
let detectedWindow: DetectedWindow | null = null;
let windowDetectEnabled = true;
let lastDetectTime = 0;
const DETECT_THROTTLE_MS = 100; // 100ms 节流，降低 EnumWindows 与日志开销

// DOM 元素
let maskElement: HTMLDivElement | null = null;
let windowHighlightElement: HTMLDivElement | null = null;
let selectionElement: HTMLDivElement | null = null;
let sizeLabelElement: HTMLDivElement | null = null;
let bottomToolbar: HTMLDivElement | null = null;
let sideToolbar: HTMLDivElement | null = null;
let toastElement: HTMLDivElement | null = null;
let colorPickerPopup: HTMLDivElement | null = null;
let widthPickerPopup: HTMLDivElement | null = null;
let drawingCanvas: HTMLCanvasElement | null = null;
let drawingCtx: CanvasRenderingContext2D | null = null;

// 内联文字编辑器状态
let inlineEditor: InlineTextEditor = {
  active: false,
  position: { x: 0, y: 0 },
  text: "",
  cursorPos: 0,
  cursorVisible: true,
  color: "#FF0000",
  fontSize: 24,
  editingItem: null,
  inputElement: null,
  isComposing: false,
};
let cursorBlinkTimer: number | null = null;

// 工具栏拖动状态
let bottomToolbarManualPos: { left: number; top: number } | null = null;
let sideToolbarManualPos: { left: number; top: number } | null = null;
let toolbarDragState: {
  toolbar: HTMLDivElement;
  isSide: boolean;
  startMouseX: number;
  startMouseY: number;
  startLeft: number;
  startTop: number;
  isDragging: boolean;
} | null = null;

// 工具按钮映射
const toolButtons: Map<DrawTool, HTMLButtonElement> = new Map();

// 操作按钮引用（用于禁用/启用）
let ocrButton: HTMLButtonElement | null = null;
let pinButton: HTMLButtonElement | null = null;
let saveButton: HTMLButtonElement | null = null;

// ============================================
// 焦点管理状态（Requirements 5.1, 5.2, 5.3）
// ============================================

/**
 * 当前窗口是否拥有焦点
 * 
 * 用于更新视觉指示器（如遮罩透明度）以反映焦点状态。
 * 当 overlay 失去焦点时，可以稍微变暗以指示非活动状态。
 */
let isWindowFocused: boolean = true;

/**
 * 窗口焦点重获时间戳
 * 
 * 当 overlay 从其他窗口（如 OCR 面板）重获焦点时记录时间。
 * 用于防止刚获回焦点时的第一次点击误触发选区重置。
 */
let focusRegainedAt: number = 0;

/**
 * 焦点保护阈值（毫秒）
 * 
 * 在窗口重获焦点后的此时间内，点击选区外不会重置选区。
 * 防止从 OCR 面板等窗口切回时误操作。
 */
const FOCUS_REGAIN_GUARD_MS = 500;

/**
 * 焦点变化事件监听器的 unlisten 函数
 * 
 * 用于在窗口关闭时清理监听器，防止内存泄漏。
 */
/**
 * Note: unlisten functions are stored for potential future cleanup.
 * Using void to suppress noUnusedLocals.
 */

/**
 * 焦点变化事件名称（与 Rust focus_manager.rs 保持一致）
 */
const FOCUS_CHANGED_EVENT = "focus-changed";

// ============================================
// 预定义颜色和粗细
// ============================================

const PRESET_COLORS = [
  "#FF0000", "#FF6600", "#FFCC00", "#00FF00",
  "#00FFFF", "#0066FF", "#9900FF", "#FF00FF",
  "#FFFFFF", "#CCCCCC", "#666666", "#000000",
];

// ============================================
// 粗细级别系统（与 Python 版本一致）
// ============================================

// 粗细级别到实际像素的映射（非线性，让差异更明显）
const WIDTH_LEVEL_TO_PIXELS: Record<number, number> = {
  1: 1, 2: 2, 3: 4, 4: 6, 5: 8,
  6: 12, 7: 16, 8: 20, 9: 26, 10: 32
};

// 步骤编号直径范围
const STEP_DIAMETER_MIN = 20;
const STEP_DIAMETER_MAX = 100;
const STEP_DIAMETER_STEP = 5;

// 文字字体大小范围
const TEXT_FONT_SIZE_MIN = 10;
const TEXT_FONT_SIZE_MAX = 200;
const TEXT_FONT_SIZE_STEP = 2;

/**
 * 根据级别获取实际像素宽度
 */
function getActualWidth(level: number): number {
  const clampedLevel = Math.max(1, Math.min(10, level));
  return WIDTH_LEVEL_TO_PIXELS[clampedLevel] ?? clampedLevel * 2;
}

/**
 * 根据像素宽度反推级别
 */
function getWidthLevel(pixels: number): number {
  if (pixels <= 0) return 1;
  // 精确匹配
  for (const [level, px] of Object.entries(WIDTH_LEVEL_TO_PIXELS)) {
    if (px === pixels) return Number(level);
  }
  // 找最接近的级别
  let closestLevel = 1;
  let minDiff = Infinity;
  for (const [level, px] of Object.entries(WIDTH_LEVEL_TO_PIXELS)) {
    const diff = Math.abs(px - pixels);
    if (diff < minDiff) {
      minDiff = diff;
      closestLevel = Number(level);
    }
  }
  return closestLevel;
}

/**
 * 根据级别获取步骤编号直径
 */
function getStepDiameter(level: number): number {
  return STEP_DIAMETER_MIN + (Math.max(1, Math.min(10, level)) - 1) * STEP_DIAMETER_STEP;
}

/**
 * 根据直径反推步骤编号级别
 */
function getStepLevelFromDiameter(diameter: number): number {
  return Math.max(1, Math.min(10, Math.floor((diameter - STEP_DIAMETER_MIN) / STEP_DIAMETER_STEP) + 1));
}

// ============================================
// 初始化
// ============================================

// 全屏截图背景元素
let screenshotBackground: HTMLImageElement | null = null;

// 全屏截图结果（用于后续裁剪）
let fullScreenCapture: CaptureResult | null = null;

// ============================================
// 静态快照状态（对应 Requirements 3.2, 3.3）
// ============================================

/**
 * 静态快照图片元素
 * 
 * 当收到 `snapshot-ready` 事件后，加载快照图片到此元素。
 * 用于在 Canvas 上渲染静态背景，实现"冻结屏幕"效果。
 */
let snapshotImage: HTMLImageElement | null = null;

/**
 * 快照是否已加载完成
 * 
 * 用于判断是否可以开始渲染快照背景。
 * 在 `snapshot-ready` 事件处理中设置为 true。
 */
let snapshotLoaded: boolean = false;

/**
 * 快照元数据
 * 
 * 存储从 Rust 后端收到的快照信息，包括：
 * - path: 临时文件路径
 * - width/height: 物理像素尺寸
 * - dpr: 主显示器 DPR
 * - monitors: 各显示器详细信息
 */
let snapshotMetadata: SnapshotReadyPayload | null = null;

/**
 * 当前 overlay 截图会话是否仍然有效。
 *
 * `snapshot-ready` 是后端异步广播事件，可能在用户已经复制/保存并隐藏
 * overlay 后才到达。隐藏状态下收到的快照只能清理，不能再触发 UI 提示。
 */
let overlaySessionActive: boolean = false;

/**
 * 快照加载代号。
 *
 * 每次开始新加载或清理状态时递增，用于让旧 Image/onerror/setTimeout
 * 回调自动失效，避免上一轮截图的失败回调污染当前会话。
 */
let snapshotLoadGeneration: number = 0;

let snapshotRetryTimer: number | null = null;
let snapshotLoadingImage: HTMLImageElement | null = null;

async function notifyOverlayFrontendReady(): Promise<void> {
  try {
    await invoke("overlay_ready");
    console.debug("[Overlay] 已主动通知后端前端监听器就绪");
  } catch (error) {
    console.warn("[Overlay] 主动通知后端就绪失败:", error);
  }
}

async function initOverlay() {
  console.debug("[Overlay] 初始化覆盖窗口...");

  const app = document.getElementById("overlay-app");
  if (!app) return;

  // 获取截图背景元素
  screenshotBackground = document.getElementById("screenshot-background") as HTMLImageElement;

  // 创建 DOM 元素
  createMaskElement(app);
  createBottomToolbar(app);
  createSideToolbar(app);
  createColorPickerPopup(app);
  createWidthPickerPopup(app);
  createToast(app);

  // 【关键】设置静态快照事件监听器（Requirements 3.2, 3.3）
  // 必须在其他事件监听器之前设置，确保能接收到 snapshot-ready 事件
  await setupSnapshotListener();

  // 监听显示器信息事件
  await listen<MonitorInfo>("overlay-init", async (event) => {
    overlaySessionActive = true;
    monitorInfo = event.payload;
    console.debug("[Overlay] 收到显示器信息:", monitorInfo);

    // 【注意】不再在此处调用 captureAndSetBackground。
    // 背景截图由 Rust 后端通过 background-capture-ready 事件主动推送，
    // 彻底消除前端轮询缓存的竞态条件。

    // 确保焦点在遮罩层上
    window.focus();
    if (maskElement) {
      maskElement.focus();
    }

    // 通知后端前端已就绪；后端只做状态登记，不再默认抢系统焦点
    try {
      await invoke("overlay_ready");
      console.debug("[Overlay] 已通知后端前端就绪");
    } catch (e) {
      console.warn("[Overlay] 通知后端就绪失败:", e);
    }
  });

  // 监听后端推送的预截图结果（冻结屏幕背景）
  // Rust 在 overlay 显示前启动截图，完成后主动推送，无竞态条件。
  await listen<CaptureResult>("background-capture-ready", async (event) => {
    const result = event.payload;
    console.debug("[Overlay] 收到预截图结果:", result);

    fullScreenCapture = result;

    // 将文件路径转换为前端可用的 URL 并加载为背景
    const assetUrl = convertFileSrc(result.path);
    if (screenshotBackground) {
      screenshotBackground.style.display = "none";
      const img = new Image();
      img.onload = async () => {
        if (screenshotBackground) {
          screenshotBackground.src = assetUrl;
          screenshotBackground.style.display = "block";
          console.debug("[Overlay] 冻结背景已加载并显示");
        }
        try {
          await invoke("overlay_background_ready");
          console.debug("[Overlay] 已通知后端背景加载完成");
        } catch (error) {
          console.warn("[Overlay] 通知后端背景加载完成失败:", error);
        }
      };
      img.onerror = (e) => {
        console.error("[Overlay] 冻结背景加载失败:", e);
      };
      img.src = assetUrl;
    }
  });

  // 监听重置事件（窗口预加载后再次显示时触发）
  await listen("overlay-reset", async () => {
    console.debug("[Overlay] 收到重置事件，准备新的截图会话");
    resetOverlayState();

    // 重新设置事件监听器（closeWindow 中已清理）
    setupMouseEvents();
    setupKeyboardEvents();
    await notifyOverlayFrontendReady();

    // 注意：这里不要再次调用 captureAndSetBackground。
    // show_overlay_windows 同时会发送 overlay-init，overlay-init 中会触发一次背景截图加载。
    // 若两处都调用，会导致 capture_screen_for_overlay 被重复触发。

    // 重置时也确保焦点
    window.focus();
    if (maskElement) {
      maskElement.focus();
    }
  });

  // 监听备用 Escape 关闭事件（Rust 端全局快捷键备用方案）
  // 当 overlay 窗口失去焦点时，JS 的 keydown 无法捕获 Escape，
  // Rust 端的全局快捷键会触发此事件，让前端有机会先复制截图再关闭
  await listen("overlay-force-close", async () => {
    console.debug("[Overlay] 收到强制关闭事件");
    await closeWindow();
  });

  // 监听外部停止录屏事件（从 RecordingControlApp 或热键停止时触发）
  await listen("overlay-exit-recording", async () => {
    console.debug("[Overlay] 收到外部停止录屏事件，清理录屏模式 CSS");
    if (isRecordingMode) {
      isRecordingMode = false;
      recordingPaused = false;
      if (recordingTimerInterval) {
        clearInterval(recordingTimerInterval);
        recordingTimerInterval = null;
      }
      recordingElapsedSeconds = 0;
      if (recordingControlBar) {
        recordingControlBar.remove();
        recordingControlBar = null;
      }
      recordingTimeElement = null;

      // 恢复遮罩和选区样式
      if (maskElement) {
        maskElement.classList.remove("recording-mode");
      }
      if (selectionElement) {
        selectionElement.classList.remove("recording-border");
      }

      // 关闭 overlay 窗口，避免截图画面残留挡住录制完成预览
      await closeWindow();
    }
  });

  // 设置事件
  setupMouseEvents();
  setupKeyboardEvents();

  await notifyOverlayFrontendReady();

  // 【关键】设置焦点变化事件监听器（Requirements 5.1, 5.2, 5.3）
  // 用于多窗口焦点协调，确保 overlay 和 OCR 面板可以独立操作
  await setupFocusEventListeners();

  // 注意：不再自动显示窗口
  // 预加载模式下，窗口由 Rust 端在热键触发时通过 show_overlay_windows 显示
  // 这样可以避免应用启动时窗口就显示出来的问题

  console.debug("[Overlay] 覆盖窗口初始化完成");
}

/**
 * 捕获全屏截图并设置为背景
 * 
 * 这是实现"冻结屏幕"效果的关键函数。
 * 在显示 overlay 时先捕获全屏，然后将截图设置为背景，
 * 用户在静态背景上选择区域，而不是实时桌面。
 */
// @ts-ignore TS6133 - 保留备用，当前由 Rust 后端通过事件推送背景截图
async function captureAndSetBackground(monitorId: number) {
  console.debug("[Overlay] 开始捕获全屏截图，显示器:", monitorId);

  try {
    // 调用 Rust 命令捕获全屏
    fullScreenCapture = await invoke<CaptureResult>("capture_screen_for_overlay", {
      monitorId: monitorId,
    });

    console.debug("[Overlay] 全屏截图完成:", fullScreenCapture);

    // 将文件路径转换为前端可用的 URL
    const assetUrl = convertFileSrc(fullScreenCapture.path);
    console.debug("[Overlay] 截图 URL:", assetUrl);

    // 设置背景图片
    if (screenshotBackground) {
      // 先隐藏，等加载完成后再显示（避免闪烁）
      screenshotBackground.style.display = "none";

      // 创建新的 Image 对象预加载
      const img = new Image();
      img.onload = () => {
        if (screenshotBackground) {
          screenshotBackground.src = assetUrl;
          screenshotBackground.style.display = "block";
          console.debug("[Overlay] 截图背景已加载并显示");
        }
      };
      img.onerror = (e) => {
        console.error("[Overlay] 截图背景加载失败:", e);
        // 加载失败时仍然显示透明背景（降级处理）
      };
      img.src = assetUrl;
    }
  } catch (error) {
    console.error("[Overlay] 捕获全屏截图失败:", error);
    // 失败时继续使用透明背景（降级处理）
    fullScreenCapture = null;
  }
}

// ============================================
// 静态快照事件监听（Requirements 3.2, 3.3）
// ============================================

/**
 * 设置 snapshot-ready 事件监听器
 * 
 * 当 Rust 后端完成静态快照捕获后，会发送 `snapshot-ready` 事件。
 * 此函数设置监听器，接收快照元数据并存储到全局状态。
 * 
 * **Validates: Requirements 3.2, 3.3**
 * 
 * 注意事项：
 * - listen() 返回 Promise<UnlistenFn>，必须 await
 * - 保存 unlisten 函数用于后续清理
 * - 使用泛型 <SnapshotReadyPayload> 确保类型安全
 */
async function setupSnapshotListener(): Promise<void> {
  console.debug("[Overlay] 设置 snapshot-ready 事件监听器...");

  try {
    // 监听 snapshot-ready 事件
    await listen<SnapshotReadyPayload>("snapshot-ready", (event) => {
      const payload = event.payload;
      if (!overlaySessionActive) {
        console.debug("[Overlay] 忽略非活动会话的 snapshot-ready 事件:", payload.path);
        invoke("cleanup_snapshot", { path: payload.path }).catch((error) => {
          console.warn("[Overlay] 清理过期快照失败（不影响使用）:", error);
        });
        return;
      }

      console.debug("[Overlay] 收到 snapshot-ready 事件:", {
        path: payload.path,
        width: payload.width,
        height: payload.height,
        dpr: payload.dpr,
        monitorCount: payload.monitors.length,
      });

      // 存储快照元数据到全局状态
      snapshotMetadata = payload;

      // 重置加载状态
      snapshotLoaded = false;
      snapshotImage = null;

      // 记录各显示器信息（用于调试多显示器场景）
      if (payload.monitors.length > 1) {
        console.debug("[Overlay] 多显示器快照信息:");
        payload.monitors.forEach((monitor, index) => {
          console.debug(`  显示器 ${index}: id=${monitor.monitor_id}, ` +
            `位置=(${monitor.x}, ${monitor.y}), ` +
            `尺寸=${monitor.width}x${monitor.height}, ` +
            `DPR=${monitor.dpr}`);
        });
      }

      // 【Task 2.4】加载快照图片
      // 调用 loadSnapshotImage 加载图片到 HTMLImageElement
      loadSnapshotImage(payload.path);
    });

    console.debug("[Overlay] snapshot-ready 事件监听器设置完成");
  } catch (error) {
    console.error("[Overlay] 设置 snapshot-ready 监听器失败:", error);
  }
}

// ============================================
// 快照图片加载（Task 2.4: Requirements 3.3, 7.3）
// ============================================

/** 最大重试次数 */
const SNAPSHOT_LOAD_MAX_RETRIES = 2;

/** 重试延迟基数（毫秒），使用指数退避 */
const SNAPSHOT_LOAD_RETRY_DELAY_BASE = 300;

function releaseImageElement(img: HTMLImageElement | null): void {
  if (!img) return;
  img.onload = null;
  img.onerror = null;
  img.src = "";
}

function cancelPendingSnapshotLoad(): void {
  snapshotLoadGeneration++;

  if (snapshotRetryTimer !== null) {
    window.clearTimeout(snapshotRetryTimer);
    snapshotRetryTimer = null;
  }

  releaseImageElement(snapshotLoadingImage);
  snapshotLoadingImage = null;
}

/**
 * 加载快照图片并存储到全局状态
 * 
 * 使用 Tauri 的 convertFileSrc 将本地文件路径转换为 asset:// URL，
 * 然后加载到 HTMLImageElement 中。支持重试逻辑以处理临时性加载失败。
 * 
 * **Validates: Requirements 3.3, 7.3**
 * 
 * @param path - 快照文件的绝对路径（从 Rust 后端获取）
 * 
 * 实现要点：
 * 1. 使用 convertFileSrc() 转换路径为 asset:// URL
 * 2. 创建 HTMLImageElement 并设置 src
 * 3. 处理 onload 事件：设置 snapshotLoaded = true，存储图片引用
 * 4. 处理 onerror 事件：实现重试逻辑（最多 2 次重试）
 * 5. 重试使用指数退避策略，避免频繁请求
 */
function loadSnapshotImage(path: string): void {
  console.debug("[Overlay] 开始加载快照图片:", path);

  cancelPendingSnapshotLoad();
  releaseImageElement(snapshotImage);

  const loadGeneration = ++snapshotLoadGeneration;

  const isCurrentLoad = () =>
    overlaySessionActive &&
    loadGeneration === snapshotLoadGeneration &&
    snapshotMetadata?.path === path;

  // 重置状态
  snapshotLoaded = false;
  snapshotImage = null;

  // 使用 convertFileSrc 将本地路径转换为 asset:// URL
  // 注意：convertFileSrc 已在文件顶部从 @tauri-apps/api/core 导入
  const assetUrl = convertFileSrc(path);
  console.debug("[Overlay] 快照 asset URL:", assetUrl);

  let retryCount = 0;

  /**
   * 尝试加载图片
   * @param url - 要加载的 URL（重试时会添加时间戳参数绕过缓存）
   */
  const attemptLoad = (url: string) => {
    if (!isCurrentLoad()) {
      console.debug("[Overlay] 快照加载已过期，跳过:", path);
      return;
    }

    console.debug(`[Overlay] 尝试加载快照图片 (尝试 ${retryCount + 1}/${SNAPSHOT_LOAD_MAX_RETRIES + 1})`);

    const img = new Image();
    snapshotLoadingImage = img;

    // 设置加载成功回调
    img.onload = () => {
      if (!isCurrentLoad() || snapshotLoadingImage !== img) {
        releaseImageElement(img);
        return;
      }

      console.debug("[Overlay] 快照图片加载成功:", {
        width: img.naturalWidth,
        height: img.naturalHeight,
        src: url.substring(0, 100) + "...", // 截断 URL 避免日志过长
      });

      // 更新全局状态
      snapshotImage = img;
      snapshotLoaded = true;
      snapshotLoadingImage = null;

      // 清理事件处理器，防止内存泄漏
      img.onload = null;
      img.onerror = null;

      // 【Task 2.5】触发重绘以显示快照背景
      // 如果 Canvas 已初始化且有选区，立即重绘以显示快照背景
      if (drawingCtx && drawingCanvas && selectionState.hasSelection) {
        console.debug("[Overlay] 快照已就绪，触发 Canvas 重绘以显示背景");
        redrawCanvas();
      } else {
        console.debug("[Overlay] 快照已就绪，等待选区创建后渲染背景");
      }
    };

    // 设置加载失败回调
    img.onerror = (event) => {
      if (!isCurrentLoad() || snapshotLoadingImage !== img) {
        releaseImageElement(img);
        return;
      }

      console.warn("[Overlay] 快照图片加载失败:", event);

      // 清理当前事件处理器
      img.onload = null;
      img.onerror = null;
      snapshotLoadingImage = null;

      // 检查是否还有重试机会
      if (retryCount < SNAPSHOT_LOAD_MAX_RETRIES) {
        retryCount++;
        
        // 计算指数退避延迟：300ms, 600ms
        const delay = SNAPSHOT_LOAD_RETRY_DELAY_BASE * retryCount;
        console.debug(`[Overlay] 将在 ${delay}ms 后进行第 ${retryCount} 次重试...`);

        // 延迟后重试，添加时间戳参数绕过可能的缓存
        snapshotRetryTimer = window.setTimeout(() => {
          snapshotRetryTimer = null;
          if (!isCurrentLoad()) {
            console.debug("[Overlay] 快照重试已过期，跳过:", path);
            return;
          }

          const retryUrl = `${assetUrl}?retry=${retryCount}&t=${Date.now()}`;
          attemptLoad(retryUrl);
        }, delay);
      } else {
        // 重试次数用尽，降级为透明 Canvas 背景。
        // 区域截图、复制、保存使用 captureResult，不依赖此辅助快照。
        console.warn(`[Overlay] 快照图片加载失败，已重试 ${SNAPSHOT_LOAD_MAX_RETRIES} 次，已降级处理`);

        // 保持 snapshotLoaded = false，让后续逻辑知道加载失败
        // 可以考虑回退到透明背景模式（降级处理）
        snapshotImage = null;
        snapshotLoaded = false;
      }
    };

    // 开始加载
    img.src = url;
  };

  // 开始首次加载尝试
  attemptLoad(assetUrl);
}

/**
 * 清理快照相关状态
 * 
 * 在截图会话结束时调用，重置所有快照相关的全局状态。
 * 这确保下一次截图会话从干净的状态开始。
 */
function cleanupSnapshotState(): void {
  cancelPendingSnapshotLoad();
  releaseImageElement(snapshotImage);
  snapshotImage = null;
  snapshotLoaded = false;
  snapshotMetadata = null;
  console.debug("[Overlay] 快照状态已清理");
}

/**
 * 清理快照临时文件
 * 
 * 在截图会话结束时调用（保存、复制、取消），删除临时快照文件。
 * 这是 Task 6.1 的核心实现，确保临时文件不会堆积。
 * 
 * **Validates: Requirements 3.4**
 * 
 * 实现要点：
 * 1. 先清除 snapshotImage.src 释放 WebView 缓存锁（Windows 避坑）
 * 2. 调用 Rust 后端的 cleanup_snapshot 命令删除文件
 * 3. 使用 fire-and-forget 模式，不阻塞 UI
 * 4. 错误处理：清理失败不影响用户体验，仅记录日志
 * 5. 最后调用 cleanupSnapshotState() 重置前端状态
 * 
 * 调用时机：
 * - handleSave(): 保存成功后
 * - handleCopy(): 复制成功后
 * - cancelSelection(): 用户按 ESC 取消时
 * - closeWindow(): 窗口隐藏时（兜底）
 */
async function cleanupSnapshotFile(): Promise<void> {
  overlaySessionActive = false;

  // 检查是否有快照需要清理
  if (!snapshotMetadata?.path) {
    console.debug("[Overlay] 无快照文件需要清理");
    cleanupSnapshotState();
    return;
  }

  const snapshotPath = snapshotMetadata.path;
  console.debug("[Overlay] 开始清理快照文件:", snapshotPath);

  try {
    // 【避坑】先清除 snapshotImage.src 释放 WebView 缓存锁
    // Windows 上如果 WebView 还在引用文件，删除会失败
    if (snapshotImage) {
      snapshotImage.src = "";
      snapshotImage = null;
    }

    // 调用 Rust 后端删除临时文件
    await invoke("cleanup_snapshot", { path: snapshotPath });
    console.debug("[Overlay] 快照文件清理成功:", snapshotPath);
  } catch (error) {
    // 清理失败不影响用户体验，仅记录警告
    // 后端有启动时清理旧文件的兜底机制
    console.warn("[Overlay] 快照文件清理失败（不影响使用）:", error);
  } finally {
    // 无论成功失败，都重置前端状态
    cleanupSnapshotState();
  }
}

// ============================================
// 快照背景渲染（Task 2.5: Requirements 1.2, 6.2）
// ============================================

/**
 * 渲染快照图片作为 Canvas 背景
 * 
 * 将静态快照图片绘制到 Canvas 上，替代透明覆盖层。
 * 这实现了"冻结屏幕"效果，用户在静态背景上进行标注。
 * 
 * **Validates: Requirements 1.2, 6.2**
 * 
 * @param ctx - Canvas 2D 渲染上下文
 * 
 * 实现要点：
 * 1. 检查快照是否已加载（snapshotLoaded && snapshotImage）
 * 2. 计算选区在全屏快照中的对应区域（考虑显示器偏移）
 * 3. 使用 drawImage 的 9 参数形式进行精确裁剪和绘制
 * 4. 所有坐标使用 Math.round() 避免亚像素模糊
 * 5. 在 DPR 缩放之前绘制，确保 1:1 像素对应
 * 
 * 多显示器处理：
 * - snapshotMetadata.monitors 包含各显示器的物理位置
 * - 当前显示器的位置由 monitorInfo.position 提供
 * - 选区坐标是相对于当前显示器的逻辑坐标
 * - 需要转换为全屏快照中的物理像素坐标
 */
function renderSnapshotBackground(ctx: CanvasRenderingContext2D): void {
  // 检查快照是否已加载
  if (!snapshotLoaded || !snapshotImage || !snapshotMetadata) {
    // 快照未就绪，跳过背景渲染（降级为透明背景）
    return;
  }

  // 检查 Canvas 是否有效
  if (!drawingCanvas) {
    return;
  }

  // 获取当前选区（逻辑像素，相对于当前窗口）
  const selectionRect = getSelectionRect();
  if (selectionRect.width <= 0 || selectionRect.height <= 0) {
    return;
  }

  // 获取当前显示器信息
  const scaleFactor = monitorInfo?.scaleFactor || 1;
  const monitorPhysicalX = monitorInfo?.position.x ?? 0;
  const monitorPhysicalY = monitorInfo?.position.y ?? 0;
  const snapshotOriginX =
    snapshotMetadata.monitors.length > 0
      ? Math.min(...snapshotMetadata.monitors.map((monitor) => monitor.x))
      : 0;
  const snapshotOriginY =
    snapshotMetadata.monitors.length > 0
      ? Math.min(...snapshotMetadata.monitors.map((monitor) => monitor.y))
      : 0;

  // 计算选区在全屏快照中的源区域（物理像素）
  // 选区坐标是相对于当前窗口的逻辑像素，需要：
  // 1. 乘以 scaleFactor 转换为当前显示器上的物理像素
  // 2. 加上当前显示器在虚拟桌面中的物理位置
  // 3. 减去快照画布原点（虚拟桌面 minX/minY），得到快照内部坐标
  const srcX = Math.round(selectionRect.x * scaleFactor + monitorPhysicalX - snapshotOriginX);
  const srcY = Math.round(selectionRect.y * scaleFactor + monitorPhysicalY - snapshotOriginY);
  const srcWidth = Math.round(selectionRect.width * scaleFactor);
  const srcHeight = Math.round(selectionRect.height * scaleFactor);

  // 目标区域：整个 Canvas（物理像素）
  const dstX = 0;
  const dstY = 0;
  const dstWidth = drawingCanvas.width;
  const dstHeight = drawingCanvas.height;

  // 边界检查：确保源区域在快照范围内
  if (srcX < 0 || srcY < 0 || 
      srcX + srcWidth > snapshotImage.naturalWidth ||
      srcY + srcHeight > snapshotImage.naturalHeight) {
    console.warn("[Overlay] 快照背景渲染：源区域超出快照范围", {
      srcX, srcY, srcWidth, srcHeight,
      snapshotWidth: snapshotImage.naturalWidth,
      snapshotHeight: snapshotImage.naturalHeight,
    });
    // 仍然尝试绘制，浏览器会自动裁剪
  }

  // 保存当前变换状态
  ctx.save();
  
  // 重置变换矩阵，确保 1:1 像素绘制
  // 注意：此时 ctx 可能已经被 scale(scaleFactor) 缩放过
  // 我们需要在原始坐标系中绘制背景
  ctx.setTransform(1, 0, 0, 1, 0, 0);

  // 使用 9 参数 drawImage 进行精确裁剪和绘制
  // drawImage(image, sx, sy, sWidth, sHeight, dx, dy, dWidth, dHeight)
  try {
    ctx.drawImage(
      snapshotImage,
      srcX, srcY, srcWidth, srcHeight,  // 源区域（从快照中裁剪）
      dstX, dstY, dstWidth, dstHeight   // 目标区域（填满 Canvas）
    );
  } catch (error) {
    console.error("[Overlay] 快照背景渲染失败:", error);
  }

  // 恢复变换状态
  ctx.restore();
}

// ============================================
// 焦点变化事件监听（Task 4.4: Requirements 5.1, 5.2, 5.3）
// ============================================

/**
 * 设置焦点变化事件监听器
 * 
 * 监听当前窗口的焦点变化，并通过 Tauri Event 广播给其他窗口。
 * 同时监听其他窗口发送的焦点变化事件，以便更新视觉指示器。
 * 
 * **Validates: Requirements 5.1, 5.2, 5.3**
 * 
 * 实现要点：
 * 1. 使用 getCurrentWindow().onFocusChanged() 监听自身焦点变化
 * 2. 焦点变化时通过 emit() 广播 focus-changed 事件
 * 3. 监听其他窗口的 focus-changed 事件
 * 4. 根据焦点状态更新视觉指示器（如遮罩透明度）
 * 5. 在窗口关闭时清理监听器，防止内存泄漏
 * 
 * 避坑要点（来自搜索结果）：
 * - 必须 await onFocusChanged()，否则 unlisten 会是 Promise
 * - 在状态变化前检查是否真的变化了，避免冗余事件
 * - 不要在 blur 事件中强制夺回焦点（流氓软件行为）
 */
async function setupFocusEventListeners(): Promise<void> {
  console.debug("[Overlay] 设置焦点变化事件监听器...");

  const appWindow = getCurrentWindow();
  const windowLabel = appWindow.label;

  try {
    // 1. 监听自身窗口的焦点变化
    // 使用 Tauri 2.0 的 onFocusChanged API（最佳实践）
    await appWindow.onFocusChanged(({ payload: focused }) => {
      // 检查状态是否真的变化了，避免冗余事件
      if (isWindowFocused === focused) {
        return;
      }

      isWindowFocused = focused;
      console.debug(`[Overlay] 窗口焦点变化: ${windowLabel}, focused=${focused}`);

      // 记录焦点重获时间，用于防止重获焦点时误触发选区重置
      if (focused) {
        focusRegainedAt = Date.now();
      } else {
        // 【Fix 3 增强版】焦点丢失时，如果 overlay 正在截图会话中，
        // 立即+延迟双重恢复焦点策略：
        // - 第一次 50ms 后快速恢复（处理大部分焦点抢夺）
        // - 第二次 200ms 后再次检查（防止系统通知等延迟焦点切换）
        if (shouldRestoreOverlayFocus({
          overlaySessionActive,
          ocrInProgress,
          pendingOcrAfterCapture: pendingOcrAfterCapture !== null,
          isRecordingMode,
          hasSelection: selectionState.hasSelection,
          isSelecting: selectionState.isSelecting,
        })) {
          const restoreFocus = async (attempt: number) => {
            if (isWindowFocused) return; // 已恢复，无需操作
            if (!shouldRestoreOverlayFocus({
              overlaySessionActive,
              ocrInProgress,
              pendingOcrAfterCapture: pendingOcrAfterCapture !== null,
              isRecordingMode,
              hasSelection: selectionState.hasSelection,
              isSelecting: selectionState.isSelecting,
            })) return; // 已退出截图或正在 OCR

            console.debug(`[Overlay] 截图会话中焦点丢失，尝试恢复焦点 (attempt=${attempt})`);
            try {
              // 调用 Rust 端的强力焦点恢复（使用 HWND_TOPMOST + AttachThreadInput）
              await invoke('overlay_force_focus');
              window.focus();
            } catch {
              // 如果 Rust 命令不可用，回退到 Tauri API
              try {
                await appWindow.setFocus();
                window.focus();
              } catch (e) {
                console.warn("[Overlay] 恢复焦点失败:", e);
              }
            }
          };

          // 第一次快速恢复（50ms）
          setTimeout(() => restoreFocus(1), 50);
          // 第二次保险恢复（200ms）
          setTimeout(() => restoreFocus(2), 200);
        }
      }

      // 构造焦点变化事件载荷
      const focusEvent: FocusChangeEvent = {
        windowLabel: windowLabel,
        isFocused: focused,
        timestamp: Date.now(),
      };

      // 广播焦点变化事件给所有窗口
      emit(FOCUS_CHANGED_EVENT, focusEvent).catch((error) => {
        console.warn("[Overlay] 发送焦点变化事件失败:", error);
      });

      // 更新视觉指示器
      updateFocusVisualIndicator(focused);
    });

    // 2. 监听其他窗口的焦点变化事件
    // 用于了解其他窗口（如 OCR 面板）的焦点状态
    await listen<FocusChangeEvent>(FOCUS_CHANGED_EVENT, (event) => {
      const { windowLabel: sourceWindow, isFocused } = event.payload;

      // 忽略自己发送的事件
      if (sourceWindow === windowLabel) {
        return;
      }

      console.debug(`[Overlay] 收到焦点变化事件: ${sourceWindow}, focused=${isFocused}`);

      // 可以在这里添加对其他窗口焦点状态的响应逻辑
      // 例如：当 OCR 面板获得焦点时，overlay 可以稍微变暗
      if (sourceWindow.startsWith("ocr-result") && isFocused) {
        // OCR 面板获得焦点，overlay 保持可见但可以添加视觉提示
        console.debug("[Overlay] OCR 面板获得焦点，overlay 保持可见");
      }
    });

    console.debug("[Overlay] 焦点变化事件监听器设置完成");
  } catch (error) {
    console.error("[Overlay] 设置焦点变化事件监听器失败:", error);
  }
}

/**
 * 更新焦点状态的视觉指示器
 * 
 * 当窗口获得或失去焦点时，更新视觉效果以反映当前状态。
 * 这帮助用户了解哪个窗口当前是活动的。
 * 
 * **Validates: Requirements 5.2**
 * 
 * @param focused - 窗口是否获得焦点
 * 
 * 视觉效果：
 * - 获得焦点：正常显示（遮罩透明度正常）
 * - 失去焦点：稍微变暗（遮罩透明度增加），但仍然可见
 */
function updateFocusVisualIndicator(focused: boolean): void {
  if (!maskElement) {
    return;
  }

  if (focused) {
    // 获得焦点：移除失焦样式
    maskElement.classList.remove("unfocused");
    console.debug("[Overlay] 视觉指示器：窗口获得焦点");
  } else {
    // 失去焦点：添加失焦样式（稍微变暗）
    // 注意：不要过度变暗，用户仍需要看到内容
    maskElement.classList.add("unfocused");
    console.debug("[Overlay] 视觉指示器：窗口失去焦点");
  }
}

// ============================================
// 创建遮罩层
// ============================================

function createMaskElement(app: HTMLElement) {
  maskElement = document.createElement("div");
  maskElement.className = "overlay-mask";
  // 添加 tabindex 使元素可以接收焦点和键盘事件
  maskElement.tabIndex = 0;
  app.appendChild(maskElement);

  // 窗口探测高亮框
  windowHighlightElement = document.createElement("div");
  windowHighlightElement.className = "window-highlight";
  windowHighlightElement.style.display = "none";
  app.appendChild(windowHighlightElement);

  selectionElement = document.createElement("div");
  selectionElement.className = "selection-rect";
  selectionElement.style.display = "none";
  app.appendChild(selectionElement);

  // 选区缩放手柄（仅视觉提示，不参与事件）
  const selectionHandles = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
  for (const handle of selectionHandles) {
    const handleEl = document.createElement("div");
    handleEl.className = `selection-handle selection-handle-${handle}`;
    selectionElement.appendChild(handleEl);
  }

  // 创建绘图 Canvas（放在选区内）
  drawingCanvas = document.createElement("canvas");
  drawingCanvas.className = "drawing-canvas";
  drawingCanvas.style.display = "none";
  app.appendChild(drawingCanvas);

  drawingCtx = drawingCanvas.getContext("2d");

  sizeLabelElement = document.createElement("div");
  sizeLabelElement.className = "size-label";
  sizeLabelElement.style.display = "none";
  app.appendChild(sizeLabelElement);
}

/**
 * 设置遮罩层是否透明（选区存在时应透明）
 * 
 * 修复"选区增亮"问题：
 * - 当选区出现时，遮罩层变透明，由 selection-rect 的 box-shadow 提供外部暗色
 * - 这样选区内始终显示原色，Canvas 加载时不会产生亮度跳变
 * - 当选区消失（取消/重选）时，恢复遮罩层的暗色效果
 */
function setMaskSelectionActive(active: boolean): void {
  if (!maskElement) return;
  if (active) {
    maskElement.classList.add("selection-active");
  } else {
    maskElement.classList.remove("selection-active");
  }
}

// ============================================
// 创建底部绘图工具栏
// ============================================

function createBottomToolbar(app: HTMLElement) {
  bottomToolbar = document.createElement("div");
  bottomToolbar.className = "bottom-toolbar";
  bottomToolbar.style.display = "none";

  const tools: Array<{ id: DrawTool; icon: string; label: string }> = [
    { id: "rect", icon: "⬜", label: "矩形" },
    { id: "ellipse", icon: "⭕", label: "椭圆" },
    { id: "arrow", icon: "➡️", label: "箭头" },
    { id: "line", icon: "📏", label: "直线" },
    { id: "pen", icon: "✏️", label: "画笔" },
    { id: "marker", icon: "🖍️", label: "高亮" },
    { id: "text", icon: "🔤", label: "文字" },
    { id: "mosaic", icon: "🔲", label: "马赛克" },
    { id: "step", icon: "①", label: "编号" },
  ];

  for (const tool of tools) {
    const btn = createToolbarButton(tool.icon, tool.label, () => {
      selectTool(tool.id);
    });
    toolButtons.set(tool.id, btn);
    bottomToolbar.appendChild(btn);
  }

  // 拖动支持（同时阻止事件传播到遮罩层）
  setupToolbarDrag(bottomToolbar, false);

  app.appendChild(bottomToolbar);
}

// ============================================
// 创建侧边功能工具栏
// ============================================

function createSideToolbar(app: HTMLElement) {
  sideToolbar = document.createElement("div");
  sideToolbar.className = "side-toolbar";
  sideToolbar.style.display = "none";

  // 撤销
  const undoBtn = createToolbarButton("↩️", "撤销", handleUndo);
  sideToolbar.appendChild(undoBtn);

  // 恢复
  const redoBtn = createToolbarButton("↪️", "恢复", handleRedo);
  sideToolbar.appendChild(redoBtn);

  // 分隔线
  sideToolbar.appendChild(createSeparator());

  // 颜色（显示当前颜色的圆点，而非调色板图标）
  const colorBtn = createColorButton(currentColor, toggleColorPicker);
  colorBtn.id = "color-btn";
  sideToolbar.appendChild(colorBtn);

  // 粗细（显示级别而非像素值）
  const widthBtn = createToolbarButton(`${currentWidthLevel}`, "粗细", toggleWidthPicker);
  widthBtn.id = "width-btn";
  sideToolbar.appendChild(widthBtn);

  // 分隔线
  sideToolbar.appendChild(createSeparator());

  // OCR
  const ocrBtn = createToolbarButton("📝", "识别", handleOcr);
  ocrBtn.classList.add("ocr-btn");
  ocrButton = ocrBtn;
  sideToolbar.appendChild(ocrBtn);

  // 钉住
  const pinBtn = createToolbarButton("📌", "钉住", handlePin);
  pinBtn.classList.add("pin-btn");
  pinButton = pinBtn;
  sideToolbar.appendChild(pinBtn);

  // 录屏
  const recordBtn = createToolbarButton("🎬", "录屏", handleStartRecording);
  recordBtn.classList.add("ocr-btn"); // 复用样式
  sideToolbar.appendChild(recordBtn);

  // 分隔线
  sideToolbar.appendChild(createSeparator());

  // 取消
  const cancelBtn = createToolbarButton("❌", "取消", cancelSelection);
  cancelBtn.classList.add("cancel-btn");
  sideToolbar.appendChild(cancelBtn);

  // 保存
  const saveBtn = createToolbarButton("💾", "保存", handleSave);
  saveBtn.classList.add("save-btn");
  saveButton = saveBtn;
  sideToolbar.appendChild(saveBtn);

  // 拖动支持（同时阻止事件传播到遮罩层）
  setupToolbarDrag(sideToolbar, true);

  app.appendChild(sideToolbar);
}

// ============================================
// 辅助函数：创建按钮和分隔线
// ============================================

function createToolbarButton(icon: string, label: string, onClick: () => void): HTMLButtonElement {
  const btn = document.createElement("button");
  btn.className = "toolbar-btn";
  const iconSpan = document.createElement("span");
  iconSpan.className = "icon";
  iconSpan.textContent = icon;
  const labelSpan = document.createElement("span");
  labelSpan.className = "label";
  labelSpan.textContent = label;
  btn.appendChild(iconSpan);
  btn.appendChild(labelSpan);
  btn.addEventListener("click", onClick);
  return btn;
}

/**
 * 创建颜色按钮（显示当前颜色的圆点）
 * 参考 Python 版本：让用户一眼看到当前选择的颜色
 */
function createColorButton(color: string, onClick: () => void): HTMLButtonElement {
  const btn = document.createElement("button");
  btn.className = "toolbar-btn color-indicator-btn";
  const indicator = document.createElement("span");
  indicator.className = "color-indicator";
  indicator.style.backgroundColor = color;
  const labelSpan = document.createElement("span");
  labelSpan.className = "label";
  labelSpan.textContent = "颜色";
  btn.appendChild(indicator);
  btn.appendChild(labelSpan);
  btn.addEventListener("click", onClick);
  return btn;
}

/**
 * 更新颜色按钮显示当前颜色
 */
function updateColorButton(color: string) {
  const colorBtn = document.getElementById("color-btn");
  if (colorBtn) {
    const indicator = colorBtn.querySelector(".color-indicator") as HTMLElement;
    if (indicator) {
      indicator.style.backgroundColor = color;
    }
  }
}

function createSeparator(): HTMLDivElement {
  const sep = document.createElement("div");
  sep.className = "separator";
  return sep;
}

function setOcrButtonDisabled(disabled: boolean) {
  if (ocrButton) ocrButton.disabled = disabled;
}

/**
 * 设置操作按钮的禁用状态（截图进行中时使用）
 */
function setActionButtonsDisabled(disabled: boolean) {
  const buttons = [ocrButton, pinButton, saveButton];
  for (const btn of buttons) {
    if (btn) btn.disabled = disabled;
  }
  if (!disabled && ocrInProgress) {
    setOcrButtonDisabled(true);
  }
}

// ============================================
// 创建颜色选择器弹窗
// ============================================

function createColorPickerPopup(app: HTMLElement) {
  colorPickerPopup = document.createElement("div");
  colorPickerPopup.className = "color-picker-popup";

  const grid = document.createElement("div");
  grid.className = "color-grid";

  for (const color of PRESET_COLORS) {
    const item = document.createElement("button");
    item.className = "color-item";
    item.style.backgroundColor = color;
    item.dataset.color = color; // 存储十六进制颜色值用于比较
    if (color === currentColor) {
      item.classList.add("active");
    }
    item.addEventListener("click", () => {
      selectColor(color);
    });
    grid.appendChild(item);
  }

  colorPickerPopup.appendChild(grid);
  colorPickerPopup.addEventListener("mousedown", (e) => e.stopPropagation());
  app.appendChild(colorPickerPopup);
}

// ============================================
// 创建粗细选择器弹窗
// ============================================

function createWidthPickerPopup(app: HTMLElement) {
  widthPickerPopup = document.createElement("div");
  widthPickerPopup.className = "width-picker-popup";

  // 创建 1-10 级别选择器
  for (let level = 1; level <= 10; level++) {
    const actualWidth = getActualWidth(level);
    const item = document.createElement("button");
    item.className = "width-item";
    if (level === currentWidthLevel) {
      item.classList.add("active");
    }
    // 显示级别和对应的线条宽度预览
    const widthLine = document.createElement("span");
    widthLine.className = "width-line";
    widthLine.style.height = `${Math.min(actualWidth, 8)}px`;
    const levelSpan = document.createElement("span");
    levelSpan.textContent = String(level);
    item.appendChild(widthLine);
    item.appendChild(levelSpan);
    item.addEventListener("click", () => {
      selectWidth(level);
    });
    widthPickerPopup.appendChild(item);
  }

  widthPickerPopup.addEventListener("mousedown", (e) => e.stopPropagation());
  app.appendChild(widthPickerPopup);
}

// ============================================
// 创建 Toast 提示
// ============================================

function createToast(app: HTMLElement) {
  toastElement = document.createElement("div");
  toastElement.className = "toast-message";
  app.appendChild(toastElement);
}

function showToast(message: string, duration = 1500) {
  if (!toastElement) return;
  toastElement.textContent = message;
  toastElement.classList.add("show");
  setTimeout(() => {
    toastElement?.classList.remove("show");
  }, duration);
}

// ============================================
// 工具选择
// ============================================

function selectTool(tool: DrawTool) {
  const previousTool = currentTool;
  currentTool = currentTool === tool ? "none" : tool;

  // 更新按钮状态
  toolButtons.forEach((btn, t) => {
    btn.classList.toggle("active", t === currentTool);
  });

  // 切换到新工具时，恢复该工具的记忆颜色和粗细
  if (currentTool !== "none" && currentTool !== previousTool) {
    // 恢复颜色
    const memorizedColor = toolColorMemory.get(currentTool);
    if (memorizedColor && memorizedColor !== currentColor) {
      currentColor = memorizedColor;
      updateColorButton(currentColor);
      // 更新颜色选择器中的选中状态
      colorPickerPopup?.querySelectorAll(".color-item").forEach((item) => {
        item.classList.toggle("active", (item as HTMLElement).dataset.color === currentColor);
      });
    }

    // 恢复粗细
    const memorizedWidth = toolWidthMemory.get(currentTool);
    if (memorizedWidth !== undefined && memorizedWidth !== currentWidthLevel) {
      currentWidthLevel = memorizedWidth;
      currentWidth = getActualWidth(memorizedWidth);
      updateWidthButton(currentWidthLevel);
      // 更新粗细选择器中的选中状态
      widthPickerPopup?.querySelectorAll(".width-item").forEach((item, index) => {
        item.classList.toggle("active", index + 1 === currentWidthLevel);
      });
    }
  }

  console.debug("[Overlay] 选择工具:", currentTool, "颜色:", currentColor, "粗细级别:", currentWidthLevel);
}

function selectColor(color: string) {
  currentColor = color;

  // 保存到当前工具的颜色记忆
  if (currentTool !== "none") {
    toolColorMemory.set(currentTool, color);
  }

  // 更新颜色选择器中的选中状态（使用 dataset.color 比较，避免 RGB/Hex 格式差异）
  colorPickerPopup?.querySelectorAll(".color-item").forEach((item) => {
    item.classList.toggle("active", (item as HTMLElement).dataset.color === color);
  });

  // 更新颜色按钮显示
  updateColorButton(color);

  // 如果有选中的图形，同步修改其颜色
  if (selectedOperationId !== null) {
    const selectedOp = drawOperations.find(op => op.id === selectedOperationId);
    if (selectedOp) {
      // 记录撤销操作（颜色修改）
      const previousColor = selectedOp.color;
      if (previousColor !== color) {
        selectedOp.color = color;
        undoStack.push({
          type: "create", // 使用 create 类型记录完整操作用于撤销
          operationId: selectedOp.id,
          operation: { ...selectedOp, color: previousColor, points: selectedOp.points.map(p => ({ ...p })) },
        });
        redoStack = [];
        redrawCanvas();
        showToast("颜色已更新");
      }
    }
  }

  hideAllPopups();
  console.debug("[Overlay] 选择颜色:", color, "工具:", currentTool);
}

function selectWidth(level: number) {
  currentWidthLevel = level;
  currentWidth = getActualWidth(level);

  // 更新粗细选择器中的选中状态
  widthPickerPopup?.querySelectorAll(".width-item").forEach((item, index) => {
    item.classList.toggle("active", index + 1 === level);
  });

  updateWidthButton(level);
  hideAllPopups();
  console.debug("[Overlay] 选择粗细级别:", level, "实际像素:", currentWidth);
}

function toggleColorPicker() {
  const isShowing = colorPickerPopup?.classList.contains("show");
  hideAllPopups();

  if (!isShowing && colorPickerPopup && sideToolbar) {
    // 定位在侧边栏左侧
    const sideRect = sideToolbar.getBoundingClientRect();
    colorPickerPopup.style.right = `${window.innerWidth - sideRect.left + 8}px`;
    colorPickerPopup.style.top = `${sideRect.top + 100}px`;
    colorPickerPopup.classList.add("show");
  }
}

function toggleWidthPicker() {
  const isShowing = widthPickerPopup?.classList.contains("show");
  hideAllPopups();

  if (!isShowing && widthPickerPopup && sideToolbar) {
    // 定位在侧边栏左侧
    const sideRect = sideToolbar.getBoundingClientRect();
    widthPickerPopup.style.right = `${window.innerWidth - sideRect.left + 8}px`;
    widthPickerPopup.style.top = `${sideRect.top + 150}px`;
    widthPickerPopup.classList.add("show");
  }
}

function hideAllPopups() {
  colorPickerPopup?.classList.remove("show");
  widthPickerPopup?.classList.remove("show");
}

// ============================================
// 鼠标事件
// ============================================

/** 鼠标事件是否已绑定（防止重复注册） */
let mouseEventsActive = false;

function setupMouseEvents() {
  if (!maskElement) return;
  if (mouseEventsActive) {
    cleanupMouseEvents();
  }

  maskElement.addEventListener("mousedown", handleMouseDown);
  maskElement.addEventListener("mousemove", handleMouseMove);
  maskElement.addEventListener("mouseup", handleMouseUp);
  maskElement.addEventListener("dblclick", handleDoubleClick);
  maskElement.addEventListener("contextmenu", handleContextMenu);
  maskElement.addEventListener("wheel", handleWheel, { passive: false });

  // 工具栏拖动事件（挂在 document 上，确保拖出工具栏也能响应）
  document.addEventListener("mousemove", handleToolbarDragMove);
  document.addEventListener("mouseup", handleToolbarDragEnd);
  mouseEventsActive = true;
}

/**
 * 清理鼠标事件监听器（隐藏 overlay 时调用）
 */
function cleanupMouseEvents() {
  if (!mouseEventsActive) return;

  if (maskElement) {
    maskElement.removeEventListener("mousedown", handleMouseDown);
    maskElement.removeEventListener("mousemove", handleMouseMove);
    maskElement.removeEventListener("mouseup", handleMouseUp);
    maskElement.removeEventListener("dblclick", handleDoubleClick);
    maskElement.removeEventListener("contextmenu", handleContextMenu);
    maskElement.removeEventListener("wheel", handleWheel);
  }

  document.removeEventListener("mousemove", handleToolbarDragMove);
  document.removeEventListener("mouseup", handleToolbarDragEnd);
  mouseEventsActive = false;
}

// ============================================
// 鼠标滚轮调整粗细
// ============================================

/**
 * 处理鼠标滚轮事件
 * 滚轮向上：减小粗细/字体/直径
 * 滚轮向下：增大粗细/字体/直径
 */
function handleWheel(e: WheelEvent) {
  // 仅在有选区时生效
  if (!selectionState.hasSelection) return;

  const delta = e.deltaY;
  if (delta === 0) return;

  e.preventDefault();

  const rect = getSelectionRect();
  const localX = e.clientX - rect.x;
  const localY = e.clientY - rect.y;

  // 优先调整鼠标下的图形，其次调整选中图形
  const itemUnderCursor = findOperationAt(localX, localY);
  const targetOp = itemUnderCursor ??
    (selectedOperationId !== null
      ? drawOperations.find(op => op.id === selectedOperationId)
      : null);

  if (targetOp) {
    switch (targetOp.tool) {
      case "text":
        adjustTextFontSize(targetOp, delta);
        return;
      case "step":
        adjustStepDiameter(targetOp, delta);
        return;
      default:
        adjustOperationWidth(targetOp, delta);
        return;
    }
  }

  // 没有目标图形时，调整全局粗细级别
  adjustGlobalWidthLevel(delta);
}

/**
 * 调整文字字体大小
 */
function adjustTextFontSize(op: DrawOperation, delta: number) {
  const step = delta > 0 ? -TEXT_FONT_SIZE_STEP : TEXT_FONT_SIZE_STEP;
  const currentSize = op.width * 6;
  const newSize = Math.max(TEXT_FONT_SIZE_MIN, Math.min(TEXT_FONT_SIZE_MAX, currentSize + step));

  if (newSize !== currentSize) {
    op.width = Math.round(newSize / 6);
    currentWidthLevel = Math.max(1, Math.min(10, Math.round((newSize - TEXT_FONT_SIZE_MIN) / 2) + 1));
    updateWidthButton(currentWidthLevel);
    redrawCanvas();
  }
}

/**
 * 调整步骤编号直径
 */
function adjustStepDiameter(op: DrawOperation, delta: number) {
  const currentDiameter = op.width > 10 ? op.width : 28;
  const step = delta > 0 ? -STEP_DIAMETER_STEP : STEP_DIAMETER_STEP;
  const newDiameter = Math.max(STEP_DIAMETER_MIN, Math.min(STEP_DIAMETER_MAX, currentDiameter + step));

  if (newDiameter !== currentDiameter) {
    op.width = newDiameter;
    currentWidthLevel = getStepLevelFromDiameter(newDiameter);
    updateWidthButton(currentWidthLevel);
    redrawCanvas();
  }
}

/**
 * 调整普通图形的线条粗细
 */
function adjustOperationWidth(op: DrawOperation, delta: number) {
  const currentLevel = getWidthLevel(op.width);
  const step = delta > 0 ? -1 : 1;
  const newLevel = Math.max(1, Math.min(10, currentLevel + step));

  if (newLevel !== currentLevel) {
    op.width = getActualWidth(newLevel);
    currentWidth = op.width;
    currentWidthLevel = newLevel;
    updateWidthButton(currentWidthLevel);
    redrawCanvas();
  }
}

/**
 * 调整全局粗细级别（无目标图形时）
 */
function adjustGlobalWidthLevel(delta: number) {
  const step = delta > 0 ? -1 : 1;
  const newLevel = Math.max(1, Math.min(10, currentWidthLevel + step));

  if (newLevel !== currentWidthLevel) {
    currentWidthLevel = newLevel;
    currentWidth = getActualWidth(newLevel);
    updateWidthButton(currentWidthLevel);
  }
}

/**
 * 更新粗细按钮显示
 */
function updateWidthButton(level: number) {
  const widthBtn = document.getElementById("width-btn");
  if (widthBtn) {
    widthBtn.textContent = "";
    const iconSpan = document.createElement("span");
    iconSpan.className = "icon";
    iconSpan.textContent = String(level);
    const labelSpan = document.createElement("span");
    labelSpan.className = "label";
    labelSpan.textContent = "粗细";
    widthBtn.appendChild(iconSpan);
    widthBtn.appendChild(labelSpan);
  }
}

/**
 * 开始编辑选区（移动/缩放）
 */
function beginSelectionEdit(mode: SelectionEditMode, handle: SelectionResizeHandle, e: MouseEvent, rect: BoundingRect) {
  selectionEditMode = mode;
  selectionResizeHandle = handle;
  selectionEditStartX = e.clientX;
  selectionEditStartY = e.clientY;
  selectionOriginalRect = { ...rect };

  // 编辑选区时先隐藏工具栏和绘图层
  hideToolbars();
  if (drawingCanvas) drawingCanvas.style.display = "none";

  // 避免旧截图被误用
  selectionEditPreviousCapture = captureResult;
  captureResult = null;
  queuedCaptureRect = null;
  queuedCaptureTriggerOcr = false;
  pendingOcrAfterCapture = null;
  pendingOcrAfterCurrent = null;
  resetOcrCache();
}

/**
 * 编辑选区时实时更新
 */
function updateSelectionEdit(e: MouseEvent) {
  if (!selectionOriginalRect) return;

  const deltaX = e.clientX - selectionEditStartX;
  const deltaY = e.clientY - selectionEditStartY;

  let nextRect: BoundingRect;
  if (selectionEditMode === "moving") {
    nextRect = clampSelectionRect({
      x: selectionOriginalRect.x + deltaX,
      y: selectionOriginalRect.y + deltaY,
      width: selectionOriginalRect.width,
      height: selectionOriginalRect.height,
    });
  } else {
    nextRect = resizeSelectionRect(selectionOriginalRect, selectionResizeHandle, deltaX, deltaY);
  }

  applySelectionRect(nextRect);
}

/**
 * 结束选区编辑并重新捕获截图
 */
async function finishSelectionEdit() {
  if (!selectionOriginalRect) return;

  const originalRect = selectionOriginalRect;
  const previousCapture = selectionEditPreviousCapture;

  selectionEditMode = "idle";
  selectionResizeHandle = "";
  selectionOriginalRect = null;
  selectionEditPreviousCapture = null;

  const rect = getSelectionRect();
  const unchanged =
    rect.x === originalRect.x &&
    rect.y === originalRect.y &&
    rect.width === originalRect.width &&
    rect.height === originalRect.height;

  if (unchanged && previousCapture) {
    captureResult = previousCapture;
    initDrawingCanvas(rect);
    showToolbars(rect);
    setActionButtonsDisabled(captureInProgress);
    return;
  }

  // 选区变化，关闭旧的 OCR 结果面板
  closeOcrPanelSilently();

  // 重新初始化绘图层与工具栏位置
  resetDrawingState();
  initDrawingCanvas(rect);
  showToolbars(rect);

  // 重新捕获最新选区
  await captureSelection(rect, { triggerOcr: AUTO_OCR_ON_SELECTION });
}

/**
 * 双击事件处理
 * 参考 C++ 版本: 双击左键 + 已有选区 → 直接复制截图到剪贴板
 */
async function handleDoubleClick(e: MouseEvent) {
  if (e.button !== 0) return;

  if (selectionState.hasSelection) {
    console.debug("[Overlay] 双击保存截图");

    // 取消正在进行的绘图（第二次点击可能已经开始了新绘图）
    if (isDrawing) {
      isDrawing = false;
      currentDrawPoints = [];
    }

    // 取消正在进行的文字输入
    if (inlineEditor.active) {
      finishInlineTextInput(false);
    }

    // 【修复】双击的 mousedown/mouseup 会反复触发 beginSelectionEdit("moving") 和 finishSelectionEdit()，
    // 导致 captureResult 被清空、排队截图请求堆积、重复保存。
    // 这里需要：1) 回滚意外的编辑操作  2) 清除排队请求  3) 等待进行中的截图完成
    if (selectionEditMode !== "idle") {
      console.debug("[Overlay] 双击回滚意外的选区编辑");
      if (selectionEditPreviousCapture) {
        captureResult = selectionEditPreviousCapture;
      }
      selectionEditMode = "idle";
      selectionResizeHandle = "";
      selectionOriginalRect = null;
      selectionEditPreviousCapture = null;
      const rect = getSelectionRect();
      showToolbars(rect);
      if (drawingCanvas) drawingCanvas.style.display = "";
    }

    // 清除排队的截图请求（由双击的 mouseup → finishSelectionEdit → captureSelection 产生）
    queuedCaptureRect = null;
    queuedCaptureTriggerOcr = false;

    // 如果截图正在进行中（调整选区后的截图还没完成），等待完成
    if (!captureResult && captureInProgress) {
      console.debug("[Overlay] 双击时截图正在进行中，等待完成...");
      const maxWait = 3000;
      const startTime = Date.now();
      while (captureInProgress && Date.now() - startTime < maxWait) {
        await new Promise(resolve => setTimeout(resolve, 50));
      }
      console.debug("[Overlay] 等待截图结束，captureResult:", captureResult ? "存在" : "null");
    }

    // 撤销双击第一次点击意外创建的标注操作（适用于所有绘图工具）
    // 双击的第一次 mousedown+mouseup 会创建一个极小的标注（如一个点状高亮、一个微小矩形等），
    // 这不是用户的意图，需要撤销它
    if (currentTool !== "none" && undoStack.length > 0) {
      const lastAction = undoStack[undoStack.length - 1];
      if (lastAction.type === "create") {
        handleUndo(true);
      }
    }

    // 清除编辑选中状态
    selectedOperationId = null;
    editMode = "idle";

    // 复制到剪贴板并关闭窗口
    await handleCopy();
  }
}

function handleMouseDown(e: MouseEvent) {
  if (e.button !== 0) return;

  hideAllPopups();

  // 如果正在进行文字输入，先完成它
  if (inlineEditor.active) {
    finishInlineTextInput(true);
  }

  // 如果已有选区
  if (selectionState.hasSelection) {
    const rect = getSelectionRect();
    const localX = e.clientX - rect.x;
    const localY = e.clientY - rect.y;

    // 优先检查选区缩放手柄（手柄区域延伸到选区边界外，必须在 inSelection 之前检测）
    if (canEditSelection()) {
      const handle = getSelectionResizeHandleAt(localX, localY, rect);
      if (handle) {
        beginSelectionEdit("resizing", handle, e, rect);
        return;
      }
    }

    const inSelection =
      e.clientX >= rect.x &&
      e.clientX <= rect.x + rect.width &&
      e.clientY >= rect.y &&
      e.clientY <= rect.y + rect.height;

    if (inSelection) {
      // 选区编辑（移动）
      if (canEditSelection()) {
        beginSelectionEdit("moving", "", e, rect);
        return;
      }

      // 检测是否点击了选中项的缩放手柄
      if (selectedOperationId !== null) {
        const selectedOp = drawOperations.find(op => op.id === selectedOperationId);
        if (selectedOp) {
          const handle = getResizeHandleAt(selectedOp, localX, localY);
          if (handle) {
            // 开始缩放
            editMode = "resizing";
            activeResizeHandle = handle;
            editStartX = localX;
            editStartY = localY;
            originalBounds = getBoundingRect(selectedOp);
            originalPoints = selectedOp.points.map(p => ({ ...p }));
            return;
          }

          // 检测是否点击在选中项内部
          if (operationContainsPoint(selectedOp, localX, localY)) {
            // 开始移动
            editMode = "moving";
            editStartX = localX;
            editStartY = localY;
            originalPoints = selectedOp.points.map(p => ({ ...p }));
            return;
          }
        }
      }

      // 检测是否点击了其他标注
      const clickedOp = findOperationAt(localX, localY);
      if (clickedOp) {
        // 选中该标注
        selectedOperationId = clickedOp.id;
        editMode = "selected";
        redrawCanvas();
        return;
      }

      // 空白区域点击
      if (selectedOperationId !== null) {
        // 取消选中
        deselectOperation();
        // 如果没有选择工具，不继续绘图
        if (currentTool === "none") {
          return;
        }
        // 有工具时继续往下执行 startDrawing
      }

      // 有工具时开始绘图
      if (currentTool !== "none") {
        startDrawing(localX, localY);
        return;
      }

      return;
    }

    if (!inSelection) {
      // 焦点保护：如果窗口刚从其他窗口（如 OCR 面板）重获焦点，
      // 第一次点击选区外不重置选区，避免误操作
      const timeSinceFocusRegain = Date.now() - focusRegainedAt;
      if (timeSinceFocusRegain < FOCUS_REGAIN_GUARD_MS) {
        console.debug(`[Overlay] 焦点保护：窗口刚重获焦点 ${timeSinceFocusRegain}ms，忽略选区外点击`);
        return;
      }
      // 点击选区外，重新开始选区
      resetSelectionForReselect();
    } else {
      return;
    }
  }

  // 开始框选（同时记录探测到的窗口，在 mouseup 时决定使用哪个）
  selectionState.isSelecting = true;
  selectionState.startX = e.clientX;
  selectionState.startY = e.clientY;
  selectionState.endX = e.clientX;
  selectionState.endY = e.clientY;

  // 隐藏窗口高亮
  hideWindowHighlight();

  if (selectionElement) selectionElement.style.display = "block";
  if (sizeLabelElement) sizeLabelElement.style.display = "block";

  // 选区出现时遮罩变透明，让选区内显示原色（修复增亮跳变）
  setMaskSelectionActive(true);

  updateSelectionRect();
}

function handleMouseMove(e: MouseEvent) {
  if (selectionState.isSelecting) {
    selectionState.endX = e.clientX;
    selectionState.endY = e.clientY;
    updateSelectionRect();
    // 框选时隐藏窗口高亮
    hideWindowHighlight();
    return;
  }

  // 选区编辑中（移动/缩放）
  if (selectionEditMode !== "idle") {
    updateSelectionEdit(e);
    return;
  }

  // 没有选区时，进行窗口探测
  if (!selectionState.hasSelection) {
    detectWindowAtPosition(e.clientX, e.clientY);
    return;
  }

  const rect = getSelectionRect();
  const localX = e.clientX - rect.x;
  const localY = e.clientY - rect.y;

  // 移动状态
  if (editMode === "moving" && selectedOperationId !== null) {
    const selectedOp = drawOperations.find(op => op.id === selectedOperationId);
    if (selectedOp) {
      const deltaX = localX - editStartX;
      const deltaY = localY - editStartY;

      // 恢复到原始位置再移动
      for (let i = 0; i < selectedOp.points.length; i++) {
        selectedOp.points[i].x = originalPoints[i].x + deltaX;
        selectedOp.points[i].y = originalPoints[i].y + deltaY;
      }

      redrawCanvas();
    }
    return;
  }

  // 缩放状态
  if (editMode === "resizing" && selectedOperationId !== null && originalBounds) {
    const selectedOp = drawOperations.find(op => op.id === selectedOperationId);
    if (selectedOp) {
      // 恢复原始点
      for (let i = 0; i < selectedOp.points.length; i++) {
        selectedOp.points[i].x = originalPoints[i].x;
        selectedOp.points[i].y = originalPoints[i].y;
      }

      // 计算新边界
      const newBounds = calculateNewBounds(originalBounds, activeResizeHandle, localX, localY);

      // 应用缩放
      resizeOperation(selectedOp, originalBounds, newBounds);

      redrawCanvas();
    }
    return;
  }

  // 绘图状态
  if (isDrawing) {
    continueDrawing(localX, localY);
    return;
  }

  // 空闲状态：更新光标和悬停
  updateCursor(localX, localY);
}

async function handleMouseUp(e: MouseEvent) {
  if (selectionEditMode !== "idle") {
    await finishSelectionEdit();
    return;
  }

  if (selectionState.isSelecting) {
    selectionState.isSelecting = false;
    selectionState.endX = e.clientX;
    selectionState.endY = e.clientY;

    const rect = getSelectionRect();

    // 检查选区是否有效（太小视为点击）
    if (rect.width < 5 || rect.height < 5) {
      // 如果有探测到的窗口，使用窗口区域作为选区（点击选择窗口）
      if (detectedWindow) {
        console.debug("[Overlay] 点击选择探测到的窗口:", detectedWindow.title);
        if (selectionElement) selectionElement.style.display = "none";
        if (sizeLabelElement) sizeLabelElement.style.display = "none";
        setMaskSelectionActive(false); // 选区消失，恢复遮罩
        await selectDetectedWindow();
        return;
      }
      // 没有探测到窗口，提示用户拖拽
      if (selectionElement) selectionElement.style.display = "none";
      if (sizeLabelElement) sizeLabelElement.style.display = "none";
      setMaskSelectionActive(false); // 选区消失，恢复遮罩
      console.debug("[Overlay] 选区太小，请拖拽选择区域");
      showToast("请拖拽选择区域");
      return;
    }

    selectionState.hasSelection = true;

    // 优化：先初始化绘图 Canvas 和显示工具栏，提升响应速度
    initDrawingCanvas(rect);
    showToolbars(rect);

    // 然后执行截图捕获（异步，不阻塞 UI）
    await captureSelection(rect, { triggerOcr: AUTO_OCR_ON_SELECTION });
    return;
  }

  // 移动结束
  if (editMode === "moving" && selectedOperationId !== null) {
    const selectedOp = drawOperations.find(op => op.id === selectedOperationId);
    if (selectedOp) {
      // 检查是否真的移动了
      const hasMoved = originalPoints.some((orig, i) =>
        selectedOp.points[i].x !== orig.x || selectedOp.points[i].y !== orig.y
      );

      if (hasMoved) {
        // 记录撤销操作
        undoStack.push({
          type: "move",
          operationId: selectedOp.id,
          previousPoints: originalPoints,
          newPoints: selectedOp.points.map(p => ({ ...p })),
        });
        redoStack = [];
      }
    }

    editMode = "selected";
    originalPoints = [];
    return;
  }

  // 缩放结束
  if (editMode === "resizing" && selectedOperationId !== null) {
    const selectedOp = drawOperations.find(op => op.id === selectedOperationId);
    if (selectedOp) {
      // 检查是否真的缩放了
      const hasResized = originalPoints.some((orig, i) =>
        selectedOp.points[i].x !== orig.x || selectedOp.points[i].y !== orig.y
      );

      if (hasResized) {
        // 记录撤销操作
        undoStack.push({
          type: "resize",
          operationId: selectedOp.id,
          previousPoints: originalPoints,
          newPoints: selectedOp.points.map(p => ({ ...p })),
        });
        redoStack = [];
      }
    }

    editMode = "selected";
    activeResizeHandle = "";
    originalBounds = null;
    originalPoints = [];
    return;
  }

  // 绘图结束
  if (isDrawing) {
    const rect = getSelectionRect();
    const x = e.clientX - rect.x;
    const y = e.clientY - rect.y;
    endDrawing(x, y);
  }
}

function handleContextMenu(e: MouseEvent) {
  e.preventDefault();
  if (selectionState.hasSelection) {
    resetSelectionForReselect();
  } else {
    cancelSelection();
  }
}

// ============================================
// 键盘事件
// ============================================

/** 键盘事件是否已绑定（防止重复注册） */
let keyboardEventsActive = false;

function setupKeyboardEvents() {
  if (keyboardEventsActive) return;

  // 使用 capture 阶段监听，确保优先捕获键盘事件
  // 这是解决焦点问题的关键：即使焦点不在特定元素上，也能捕获按键
  window.addEventListener("keydown", handleKeyDown, { capture: true });

  // 同时在 document 上监听作为备用
  document.addEventListener("keydown", handleKeyDown, { capture: true });

  keyboardEventsActive = true;
  console.debug("[Overlay] 键盘事件监听已设置（capture 模式）");
}

/**
 * 清理键盘事件监听器（隐藏 overlay 时调用）
 */
function cleanupKeyboardEvents() {
  if (!keyboardEventsActive) return;

  window.removeEventListener("keydown", handleKeyDown, { capture: true });
  document.removeEventListener("keydown", handleKeyDown, { capture: true });
  keyboardEventsActive = false;
}

async function handleKeyDown(e: KeyboardEvent) {
  // 优先处理内联文字编辑
  if (inlineEditor.active) {
    if (handleTextEditKey(e)) {
      return;
    }
  }

  if (e.key === "Escape") {
    e.preventDefault();
    e.stopPropagation();

    // 录屏模式下，Escape 停止录制（不关闭 overlay）
    if (isRecordingMode) {
      console.debug("[Overlay] 录屏模式下 Escape，停止录制");
      stopRecording();
      return;
    }

    console.debug("[Overlay] 检测到 Escape 按键");
    // 如果有选中项，先取消选中
    if (selectedOperationId !== null) {
      deselectOperation();
      return;
    }
    cancelSelection();
  } else if (e.ctrlKey && e.key.toLowerCase() === "s") {
    e.preventDefault();
    if (selectionState.hasSelection) await handleSave();
  } else if (e.ctrlKey && e.key.toLowerCase() === "c") {
    e.preventDefault();
    if (selectionState.hasSelection) await handleCopy();
  } else if (e.key === "Enter") {
    if (selectionState.hasSelection) await handleCopy();
  } else if (e.ctrlKey && e.key.toLowerCase() === "z") {
    e.preventDefault();
    handleUndo();
  } else if (e.ctrlKey && e.key.toLowerCase() === "y") {
    e.preventDefault();
    handleRedo();
  } else if (e.key === "Delete" || e.key === "Backspace") {
    // 删除选中项
    if (selectedOperationId !== null) {
      e.preventDefault();
      deleteSelectedOperation();
    }
  }
}

function deleteSelectedOperation() {
  if (selectedOperationId === null) return;

  const index = drawOperations.findIndex(op => op.id === selectedOperationId);
  if (index === -1) return;

  const removed = drawOperations.splice(index, 1)[0];

  // 记录撤销操作
  undoStack.push({
    type: "delete",
    operationId: removed.id,
    operation: { ...removed, points: removed.points.map(p => ({ ...p })) },
  });
  redoStack = [];

  // 如果删除的是编号，回退编号计数器
  if (removed.tool === "step") {
    stepCounter = Math.max(1, stepCounter - 1);
  }

  deselectOperation();
  showToast("已删除");
}

// ============================================
// 选区更新
// ============================================

function updateSelectionRect() {
  if (!selectionElement || !sizeLabelElement) return;

  const rect = getSelectionRect();

  selectionElement.style.left = `${rect.x}px`;
  selectionElement.style.top = `${rect.y}px`;
  selectionElement.style.width = `${rect.width}px`;
  selectionElement.style.height = `${rect.height}px`;

  const scaleFactor = monitorInfo?.scaleFactor || 1;
  const physicalWidth = Math.round(rect.width * scaleFactor);
  const physicalHeight = Math.round(rect.height * scaleFactor);
  sizeLabelElement.textContent = `${physicalWidth} × ${physicalHeight}`;

  sizeLabelElement.style.left = `${rect.x}px`;
  sizeLabelElement.style.top = `${rect.y + rect.height + 8}px`;
}

function getSelectionRect() {
  const x = Math.min(selectionState.startX, selectionState.endX);
  const y = Math.min(selectionState.startY, selectionState.endY);
  const width = Math.abs(selectionState.endX - selectionState.startX);
  const height = Math.abs(selectionState.endY - selectionState.startY);
  return { x, y, width, height };
}

/**
 * 判断是否允许编辑选区
 */
function canEditSelection(): boolean {
  return selectionState.hasSelection && currentTool === "none" && selectedOperationId === null && drawOperations.length === 0;
}

/**
 * 根据本地坐标判断是否命中选区缩放手柄
 */
function getSelectionResizeHandleAt(localX: number, localY: number, rect: BoundingRect): SelectionResizeHandle {
  const withinX = localX >= -SELECTION_HANDLE_MARGIN && localX <= rect.width + SELECTION_HANDLE_MARGIN;
  const withinY = localY >= -SELECTION_HANDLE_MARGIN && localY <= rect.height + SELECTION_HANDLE_MARGIN;
  if (!withinX || !withinY) return "";

  const nearLeft = Math.abs(localX) <= SELECTION_HANDLE_MARGIN;
  const nearRight = Math.abs(localX - rect.width) <= SELECTION_HANDLE_MARGIN;
  const nearTop = Math.abs(localY) <= SELECTION_HANDLE_MARGIN;
  const nearBottom = Math.abs(localY - rect.height) <= SELECTION_HANDLE_MARGIN;

  if (nearLeft && nearTop) return "nw";
  if (nearRight && nearTop) return "ne";
  if (nearLeft && nearBottom) return "sw";
  if (nearRight && nearBottom) return "se";
  if (nearTop) return "n";
  if (nearBottom) return "s";
  if (nearLeft) return "w";
  if (nearRight) return "e";
  return "";
}

/**
 * 将选区限制在窗口范围内，并保证最小尺寸
 */
function clampSelectionRect(rect: BoundingRect): BoundingRect {
  let width = Math.max(SELECTION_MIN_SIZE, rect.width);
  let height = Math.max(SELECTION_MIN_SIZE, rect.height);
  let x = rect.x;
  let y = rect.y;

  if (width > window.innerWidth) {
    width = window.innerWidth;
    x = 0;
  }
  if (height > window.innerHeight) {
    height = window.innerHeight;
    y = 0;
  }

  x = Math.min(Math.max(0, x), window.innerWidth - width);
  y = Math.min(Math.max(0, y), window.innerHeight - height);

  return { x, y, width, height };
}

/**
 * 将选区状态更新为指定矩形
 */
function applySelectionRect(rect: BoundingRect) {
  selectionState.isSelecting = false;
  selectionState.hasSelection = rect.width > 0 && rect.height > 0;
  selectionState.startX = rect.x;
  selectionState.startY = rect.y;
  selectionState.endX = rect.x + rect.width;
  selectionState.endY = rect.y + rect.height;

  if (selectionElement) selectionElement.style.display = "block";
  if (sizeLabelElement) sizeLabelElement.style.display = "block";

  // 选区出现时遮罩变透明（修复增亮跳变）
  setMaskSelectionActive(true);

  updateSelectionRect();
}

/**
 * 根据拖拽信息计算新的选区
 */
function resizeSelectionRect(
  rect: BoundingRect,
  handle: SelectionResizeHandle,
  deltaX: number,
  deltaY: number
): BoundingRect {
  let { x, y, width, height } = rect;

  switch (handle) {
    case "e":
      width += deltaX;
      break;
    case "w":
      x += deltaX;
      width -= deltaX;
      break;
    case "s":
      height += deltaY;
      break;
    case "n":
      y += deltaY;
      height -= deltaY;
      break;
    case "se":
      width += deltaX;
      height += deltaY;
      break;
    case "sw":
      x += deltaX;
      width -= deltaX;
      height += deltaY;
      break;
    case "ne":
      y += deltaY;
      height -= deltaY;
      width += deltaX;
      break;
    case "nw":
      x += deltaX;
      y += deltaY;
      width -= deltaX;
      height -= deltaY;
      break;
    default:
      break;
  }

  // 保证最小尺寸
  if (width < SELECTION_MIN_SIZE) {
    if (handle === "w" || handle === "nw" || handle === "sw") {
      x -= SELECTION_MIN_SIZE - width;
    }
    width = SELECTION_MIN_SIZE;
  }
  if (height < SELECTION_MIN_SIZE) {
    if (handle === "n" || handle === "nw" || handle === "ne") {
      y -= SELECTION_MIN_SIZE - height;
    }
    height = SELECTION_MIN_SIZE;
  }

  return clampSelectionRect({ x, y, width, height });
}

// ============================================
// 工具栏拖动
// ============================================

const DRAG_THRESHOLD = 4; // 拖动阈值（像素），超过此距离才认为是拖动

function setupToolbarDrag(toolbar: HTMLDivElement, isSide: boolean) {
  toolbar.addEventListener("mousedown", (e: MouseEvent) => {
    e.stopPropagation();

    // 只响应左键
    if (e.button !== 0) return;

    const rect = toolbar.getBoundingClientRect();
    toolbarDragState = {
      toolbar,
      isSide,
      startMouseX: e.clientX,
      startMouseY: e.clientY,
      startLeft: rect.left,
      startTop: rect.top,
      isDragging: false,
    };
  });
}

function handleToolbarDragMove(e: MouseEvent) {
  if (!toolbarDragState) return;

  const dx = e.clientX - toolbarDragState.startMouseX;
  const dy = e.clientY - toolbarDragState.startMouseY;

  // 未达到拖动阈值，不启动拖动
  if (!toolbarDragState.isDragging) {
    if (Math.abs(dx) < DRAG_THRESHOLD && Math.abs(dy) < DRAG_THRESHOLD) return;
    toolbarDragState.isDragging = true;
    toolbarDragState.toolbar.style.cursor = "grabbing";
  }

  const margin = 8;
  const toolbar = toolbarDragState.toolbar;
  const tw = toolbar.offsetWidth;
  const th = toolbar.offsetHeight;

  // 计算新位置，限制在视口内
  let newLeft = toolbarDragState.startLeft + dx;
  let newTop = toolbarDragState.startTop + dy;
  newLeft = Math.max(margin, Math.min(newLeft, window.innerWidth - tw - margin));
  newTop = Math.max(margin, Math.min(newTop, window.innerHeight - th - margin));

  toolbar.style.left = `${newLeft}px`;
  toolbar.style.top = `${newTop}px`;
}

function handleToolbarDragEnd(_e: MouseEvent) {
  if (!toolbarDragState) return;

  const state = toolbarDragState;
  state.toolbar.style.cursor = "";

  if (state.isDragging) {
    // 记录手动位置
    const rect = state.toolbar.getBoundingClientRect();
    const pos = { left: rect.left, top: rect.top };

    if (state.isSide) {
      sideToolbarManualPos = pos;
    } else {
      bottomToolbarManualPos = pos;
    }

    // 阻止本次拖动触发按钮点击
    const preventClick = (ev: Event) => {
      ev.stopPropagation();
      ev.preventDefault();
    };
    state.toolbar.addEventListener("click", preventClick, { capture: true, once: true });
  }

  toolbarDragState = null;
}

// ============================================
// 工具栏显示/隐藏
// ============================================

function showToolbars(rect: { x: number; y: number; width: number; height: number }) {
  const margin = 8;
  const sideToolbarWidth = 60;

  // 侧边工具栏位置计算（先计算，因为底部工具栏需要避让）
  let sideLeft = 0;
  let sideTop = 0;
  let sideOnRight = true;
  let sideHeight = 0;

  if (sideToolbar) {
    sideHeight = sideToolbar.offsetHeight;

    // 如果用户手动拖动过，使用手动位置
    if (sideToolbarManualPos) {
      sideLeft = sideToolbarManualPos.left;
      sideTop = sideToolbarManualPos.top;
      // 判断侧边栏在选区哪一侧（用于底部工具栏避让参考）
      sideOnRight = sideLeft > rect.x + rect.width / 2;
    } else {
      const spaceRight = window.innerWidth - rect.x - rect.width - margin;
      const spaceLeft = rect.x - margin;

      // 优先放在选区右侧
      if (spaceRight >= sideToolbarWidth) {
        sideLeft = rect.x + rect.width + margin;
        sideOnRight = true;
      } else if (spaceLeft >= sideToolbarWidth) {
        // 其次放在选区左侧
        sideLeft = rect.x - sideToolbarWidth - margin;
        sideOnRight = false;
      } else if (spaceRight >= spaceLeft) {
        // 空间不够时，贴屏幕右侧边缘（工具栏会叠在选区内部）
        sideLeft = window.innerWidth - sideToolbarWidth - margin;
        sideOnRight = true;
      } else {
        sideLeft = Math.max(margin, rect.x - sideToolbarWidth - margin);
        sideOnRight = false;
      }

      // 垂直位置：与选区顶部对齐
      sideTop = rect.y;
      if (sideTop + sideHeight > window.innerHeight - margin) {
        sideTop = window.innerHeight - sideHeight - margin;
      }
      if (sideTop < margin) sideTop = margin;
    }

    sideToolbar.style.top = `${sideTop}px`;
    sideToolbar.style.left = `${sideLeft}px`;
    sideToolbar.style.display = "flex";
  }

  // 底部工具栏位置计算（考虑与侧边栏的重叠避让）
  if (bottomToolbar) {
    // 如果用户手动拖动过，使用手动位置
    if (bottomToolbarManualPos) {
      bottomToolbar.style.top = `${bottomToolbarManualPos.top}px`;
      bottomToolbar.style.left = `${bottomToolbarManualPos.left}px`;
      bottomToolbar.style.display = "flex";
    } else {
      const toolbarHeight = 56;
      const toolbarWidth = bottomToolbar.offsetWidth;
      const spaceBelow = window.innerHeight - rect.y - rect.height - margin;
      const spaceAbove = rect.y - margin;

      // 计算垂直位置
      let top: number;
      if (spaceBelow >= toolbarHeight) {
        top = rect.y + rect.height + margin;
      } else if (spaceAbove >= toolbarHeight) {
        top = rect.y - toolbarHeight - margin;
      } else if (spaceBelow >= spaceAbove) {
        // 空间不够时，贴屏幕底部边缘（工具栏会叠在选区内部）
        top = window.innerHeight - toolbarHeight - margin;
      } else {
        top = Math.max(margin, rect.y - toolbarHeight - margin);
      }

      // 计算水平位置：与选区左侧对齐
      let left = rect.x;
      if (left < margin) left = margin;
      if (left + toolbarWidth > window.innerWidth - margin) {
        left = window.innerWidth - toolbarWidth - margin;
      }

      // 检测与侧边栏是否重叠，并调整位置
      if (sideToolbar && sideHeight > 0) {
        const bottomRight = left + toolbarWidth;
        const bottomBottom = top + toolbarHeight;
        const sideRight = sideLeft + sideToolbarWidth;
        const sideBottom = sideTop + sideHeight;

        // 检查矩形是否相交
        const hasOverlap = !(
          bottomRight <= sideLeft ||   // 底部工具栏在侧边栏左侧
          left >= sideRight ||         // 底部工具栏在侧边栏右侧
          bottomBottom <= sideTop ||   // 底部工具栏在侧边栏上方
          top >= sideBottom            // 底部工具栏在侧边栏下方
        );

        if (hasOverlap) {
          // 尝试水平避让
          if (sideOnRight) {
            // 侧边栏在右侧，底部工具栏向左移动
            const newLeft = sideLeft - toolbarWidth - margin;
            if (newLeft >= margin) {
              left = newLeft;
            } else {
              // 左侧空间不够，尝试移到侧边栏下方
              const belowSideTop = sideBottom + margin;
              if (belowSideTop + toolbarHeight <= window.innerHeight - margin) {
                top = belowSideTop;
                left = rect.x;
                if (left < margin) left = margin;
                if (left + toolbarWidth > window.innerWidth - margin) {
                  left = window.innerWidth - toolbarWidth - margin;
                }
              }
            }
          } else {
            // 侧边栏在左侧，底部工具栏向右移动
            const newLeft = sideRight + margin;
            if (newLeft + toolbarWidth <= window.innerWidth - margin) {
              left = newLeft;
            } else {
              // 右侧空间不够，尝试移到侧边栏下方
              const belowSideTop = sideBottom + margin;
              if (belowSideTop + toolbarHeight <= window.innerHeight - margin) {
                top = belowSideTop;
                left = rect.x;
                if (left < margin) left = margin;
                if (left + toolbarWidth > window.innerWidth - margin) {
                  left = window.innerWidth - toolbarWidth - margin;
                }
              }
            }
          }
        }
      }

      bottomToolbar.style.top = `${top}px`;
      bottomToolbar.style.left = `${left}px`;
      bottomToolbar.style.display = "flex";
    }
  }
}

function hideToolbars() {
  if (bottomToolbar) bottomToolbar.style.display = "none";
  if (sideToolbar) sideToolbar.style.display = "none";
  // 重置手动拖动位置，下次 showToolbars 会重新自动定位
  bottomToolbarManualPos = null;
  sideToolbarManualPos = null;
  hideAllPopups();
}

// ============================================
// 绘图 Canvas 初始化
// ============================================

function initDrawingCanvas(rect: { x: number; y: number; width: number; height: number }) {
  if (!drawingCanvas || !drawingCtx) return;

  const scaleFactor = monitorInfo?.scaleFactor || 1;

  // 设置 Canvas 位置和大小
  drawingCanvas.style.position = "fixed";
  drawingCanvas.style.left = `${rect.x}px`;
  drawingCanvas.style.top = `${rect.y}px`;
  drawingCanvas.style.width = `${rect.width}px`;
  drawingCanvas.style.height = `${rect.height}px`;
  drawingCanvas.style.display = "block";
  drawingCanvas.style.pointerEvents = "none";
  drawingCanvas.style.zIndex = "50";

  // Canvas 内部尺寸使用物理像素
  drawingCanvas.width = Math.round(rect.width * scaleFactor);
  drawingCanvas.height = Math.round(rect.height * scaleFactor);

  // 设置缩放以匹配 DPR
  drawingCtx.scale(scaleFactor, scaleFactor);

  console.debug("[Overlay] 绘图 Canvas 初始化:", rect.width, "x", rect.height);
}

function resetDrawingState() {
  drawOperations = [];
  undoStack = [];
  redoStack = [];
  stepCounter = 1;
  isDrawing = false;
  currentDrawPoints = [];
  operationIdCounter = 0;

  // 重置编辑状态
  editMode = "idle";
  selectedOperationId = null;
  hoveredOperationId = null;
  activeResizeHandle = "";
  originalBounds = null;
  originalPoints = [];

  // 重置内联编辑器
  stopCursorBlink();
  removeImeInputElement();
  inlineEditor.active = false;
  inlineEditor.text = "";
  inlineEditor.cursorPos = 0;
  inlineEditor.editingItem = null;

  if (drawingCtx && drawingCanvas) {
    drawingCtx.clearRect(0, 0, drawingCanvas.width, drawingCanvas.height);
  }
}

/**
 * 重置整个覆盖窗口状态（用于窗口预加载后再次显示时）
 * 当热键再次触发时，需要完全重置状态，准备新的截图会话
 */
function resetOverlayState() {
  overlaySessionActive = true;
  restoreOverlayInteractiveSurfaces();

  // 重置录屏模式状态（避免上次录屏后残留状态导致截图功能失效）
  isRecordingMode = false;
  recordingPaused = false;
  if (recordingTimerInterval) {
    clearInterval(recordingTimerInterval);
    recordingTimerInterval = null;
  }
  recordingElapsedSeconds = 0;
  if (recordingControlBar) {
    recordingControlBar.remove();
    recordingControlBar = null;
  }
  recordingTimeElement = null;

  // 确保录屏相关窗口已关闭
  invoke("close_recording_border").catch(() => {});
  invoke("close_recording_control").catch(() => {});
  suspendAutoOcr = false;

  // 重置选区状态
  selectionState = {
    isSelecting: false,
    hasSelection: false,
    startX: 0,
    startY: 0,
    endX: 0,
    endY: 0,
  };

  selectionEditMode = "idle";
  selectionResizeHandle = "";
  selectionOriginalRect = null;
  selectionEditPreviousCapture = null;
  captureInProgress = false;
  queuedCaptureRect = null;
  queuedCaptureTriggerOcr = false;
  pendingOcrAfterCapture = null;
  pendingOcrAfterCurrent = null;
  resetOcrCache();
  setActionButtonsDisabled(false);

  // 重置截图结果
  captureResult = null;

  // 清除上一次的冻结背景（防止窗口显示时闪现旧画面）
  if (screenshotBackground) {
    screenshotBackground.style.display = "none";
    screenshotBackground.src = "";
  }
  fullScreenCapture = null;

  // 重置静态快照状态（Requirements 3.2, 3.3）
  cleanupSnapshotState();

  // 重置绘图状态
  resetDrawingState();

  // 重置工具选择
  currentTool = "none";
  toolButtons.forEach((btn) => btn.classList.remove("active"));

  // 重置窗口探测状态
  detectedWindow = null;
  windowDetectEnabled = true;
  lastDetectTime = 0;

  // 隐藏所有 UI 元素
  if (selectionElement) selectionElement.style.display = "none";
  if (sizeLabelElement) sizeLabelElement.style.display = "none";
  if (drawingCanvas) drawingCanvas.style.display = "none";
  hideWindowHighlight();
  hideToolbars();
  hideAllPopups();

  // 选区消失，恢复遮罩层暗色
  setMaskSelectionActive(false);

  // 重置光标
  if (maskElement) {
    maskElement.style.cursor = "crosshair";
    // 确保遮罩层获得焦点
    maskElement.focus();
  }

  // 关键：确保窗口和 document 获得焦点，以便接收键盘事件（如 ESC）
  window.focus();
  document.body.focus();

  // 使用 Tauri API 确保窗口获得焦点
  getCurrentWindow().setFocus().catch((e) => {
    console.warn("[Overlay] 设置窗口焦点失败:", e);
  });

  console.debug("[Overlay] 状态已重置，准备新的截图会话");
}

// ============================================
// 绘图操作
// ============================================

function startDrawing(x: number, y: number) {
  if (currentTool === "none") return;

  // 取消选中
  deselectOperation();

  // 文字工具特殊处理
  if (currentTool === "text") {
    startInlineTextInput(x, y);
    return;
  }

  isDrawing = true;
  editMode = "drawing";
  drawStartX = x;
  drawStartY = y;
  currentDrawPoints = [{ x, y }];

  // 清空 redo 栈
  redoStack = [];
}

function continueDrawing(x: number, y: number) {
  if (!isDrawing || !drawingCtx || !drawingCanvas) return;

  currentDrawPoints.push({ x, y });

  // 重绘所有内容
  redrawCanvas();

  // 绘制当前正在进行的操作（预览）
  drawPreview(x, y);
}

function endDrawing(x: number, y: number) {
  if (!isDrawing) return;

  isDrawing = false;
  editMode = "idle";
  currentDrawPoints.push({ x, y });

  // 创建绘图操作
  const operation: DrawOperation = {
    id: generateOperationId(),
    tool: currentTool,
    color: currentColor,
    width: currentWidth,
    points: [...currentDrawPoints],
  };

  // 编号工具特殊处理：保存编号和直径
  if (currentTool === "step") {
    operation.stepNumber = stepCounter++;
    operation.width = getStepDiameter(currentWidthLevel);
  }

  drawOperations.push(operation);

  // 记录撤销操作
  undoStack.push({
    type: "create",
    operationId: operation.id,
    operation: { ...operation, points: operation.points.map(p => ({ ...p })) },
  });
  redoStack = [];

  currentDrawPoints = [];

  // 重绘 Canvas
  redrawCanvas();
}

function drawPreview(x: number, y: number) {
  if (!drawingCtx) return;

  const ctx = drawingCtx;
  ctx.save();

  ctx.strokeStyle = currentColor;
  ctx.fillStyle = currentColor;
  ctx.lineWidth = currentWidth;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  switch (currentTool) {
    case "rect":
      drawRect(ctx, drawStartX, drawStartY, x, y, false);
      break;
    case "ellipse":
      drawEllipse(ctx, drawStartX, drawStartY, x, y, false);
      break;
    case "arrow":
      drawArrow(ctx, drawStartX, drawStartY, x, y);
      break;
    case "line":
      drawLine(ctx, drawStartX, drawStartY, x, y);
      break;
    case "pen":
      drawPenPath(ctx, currentDrawPoints);
      break;
    case "marker":
      // 高亮工具：矩形半透明填充（参考 Python/C++ 版本）
      drawMarkerRect(ctx, drawStartX, drawStartY, x, y);
      break;
    case "mosaic":
      drawMosaicPreview(ctx, drawStartX, drawStartY, x, y);
      break;
    case "step":
      drawStep(ctx, x, y, stepCounter, getStepDiameter(currentWidthLevel));
      break;
  }

  ctx.restore();
}

function redrawCanvas() {
  if (!drawingCtx || !drawingCanvas) return;

  const ctx = drawingCtx;
  const scaleFactor = monitorInfo?.scaleFactor || 1;

  // 清空 Canvas
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, drawingCanvas.width, drawingCanvas.height);

  // 【Task 2.5】渲染快照背景（Requirements 1.2, 6.2）
  // 在应用 DPR 缩放之前绘制背景，确保 1:1 像素对应
  // 这实现了"冻结屏幕"效果，用户在静态背景上进行标注
  renderSnapshotBackground(ctx);

  // 应用 DPR 缩放，后续标注绑制使用逻辑坐标
  ctx.scale(scaleFactor, scaleFactor);

  renderDrawOperations(ctx);

  // 绘制悬停高亮
  if (hoveredOperationId !== null && hoveredOperationId !== selectedOperationId) {
    const hoveredOp = drawOperations.find(op => op.id === hoveredOperationId);
    if (hoveredOp) {
      drawSelectionHandles(ctx, hoveredOp, true);
    }
  }

  // 绘制选中框
  if (selectedOperationId !== null) {
    const selectedOp = drawOperations.find(op => op.id === selectedOperationId);
    if (selectedOp) {
      drawSelectionHandles(ctx, selectedOp, false);
    }
  }

  // 绘制内联文字编辑器（光标和正在输入的文字）
  drawInlineEditor(ctx);
}

function renderDrawOperations(ctx: CanvasRenderingContext2D) {
  // 重绘所有操作（标注层）
  for (const op of drawOperations) {
    ctx.save();
    ctx.strokeStyle = op.color;
    ctx.fillStyle = op.color;
    ctx.lineWidth = op.width;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    const points = op.points;
    if (points.length < 2 && op.tool !== "step" && op.tool !== "text") {
      ctx.restore();
      continue;
    }

    const startX = points[0]?.x || 0;
    const startY = points[0]?.y || 0;
    const endX = points[points.length - 1]?.x || 0;
    const endY = points[points.length - 1]?.y || 0;

    switch (op.tool) {
      case "rect":
        drawRect(ctx, startX, startY, endX, endY, false);
        break;
      case "ellipse":
        drawEllipse(ctx, startX, startY, endX, endY, false);
        break;
      case "arrow":
        drawArrow(ctx, startX, startY, endX, endY);
        break;
      case "line":
        drawLine(ctx, startX, startY, endX, endY);
        break;
      case "pen":
        drawPenPath(ctx, points);
        break;
      case "marker":
        // 高亮工具：矩形半透明填充
        drawMarkerRect(ctx, startX, startY, endX, endY);
        break;
      case "mosaic":
        drawMosaic(ctx, startX, startY, endX, endY);
        break;
      case "step":
        // 使用保存的直径（width > 10 表示直径，否则使用默认值）
        const stepDiameter = op.width > 10 ? op.width : 28;
        drawStep(ctx, endX, endY, op.stepNumber || 1, stepDiameter);
        break;
      case "text":
        if (op.text) {
          drawText(ctx, startX, startY, op.text, op.color, op.width);
        }
        break;
    }

    ctx.restore();
  }
}

// ============================================
// 绘图基础函数
// ============================================

function drawRect(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number, fill: boolean) {
  const x = Math.min(x1, x2);
  const y = Math.min(y1, y2);
  const w = Math.abs(x2 - x1);
  const h = Math.abs(y2 - y1);

  if (fill) {
    ctx.fillRect(x, y, w, h);
  } else {
    ctx.strokeRect(x, y, w, h);
  }
}

function drawEllipse(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number, fill: boolean) {
  const cx = (x1 + x2) / 2;
  const cy = (y1 + y2) / 2;
  const rx = Math.abs(x2 - x1) / 2;
  const ry = Math.abs(y2 - y1) / 2;

  ctx.beginPath();
  ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);

  if (fill) {
    ctx.fill();
  } else {
    ctx.stroke();
  }
}

function drawArrow(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number) {
  const headLength = Math.max(10, ctx.lineWidth * 3);
  const angle = Math.atan2(y2 - y1, x2 - x1);

  // 画线
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();

  // 画箭头
  ctx.beginPath();
  ctx.moveTo(x2, y2);
  ctx.lineTo(
    x2 - headLength * Math.cos(angle - Math.PI / 6),
    y2 - headLength * Math.sin(angle - Math.PI / 6)
  );
  ctx.lineTo(
    x2 - headLength * Math.cos(angle + Math.PI / 6),
    y2 - headLength * Math.sin(angle + Math.PI / 6)
  );
  ctx.closePath();
  ctx.fill();
}

function drawLine(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number) {
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
}

function drawPenPath(ctx: CanvasRenderingContext2D, points: Array<{ x: number; y: number }>) {
  if (points.length < 2) return;

  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);

  for (let i = 1; i < points.length; i++) {
    ctx.lineTo(points[i].x, points[i].y);
  }
  ctx.stroke();
}

/**
 * 绘制高亮矩形（半透明填充，无边框）
 * 参考 Python 版本和 C++ 版本的实现
 */
function drawMarkerRect(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number) {
  const x = Math.min(x1, x2);
  const y = Math.min(y1, y2);
  const w = Math.abs(x2 - x1);
  const h = Math.abs(y2 - y1);

  ctx.save();
  ctx.globalAlpha = 0.4;
  ctx.fillRect(x, y, w, h);
  ctx.restore();
}

function drawMosaic(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number) {
  const x = Math.min(x1, x2);
  const y = Math.min(y1, y2);
  const w = Math.abs(x2 - x1);
  const h = Math.abs(y2 - y1);
  const blockSize = 10;

  // 马赛克效果：使用基于坐标的确定性灰度值，避免重绘时跳动
  for (let bx = 0; bx < w; bx += blockSize) {
    for (let by = 0; by < h; by += blockSize) {
      // 用坐标生成稳定的伪随机灰度值（每次重绘结果一致）
      const hash = ((x + bx) * 2654435761 + (y + by) * 2246822519) >>> 0;
      const gray = (hash % 100) + 100;
      ctx.fillStyle = `rgb(${gray}, ${gray}, ${gray})`;
      ctx.fillRect(x + bx, y + by, blockSize, blockSize);
    }
  }
}

function drawMosaicPreview(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number) {
  const x = Math.min(x1, x2);
  const y = Math.min(y1, y2);
  const w = Math.abs(x2 - x1);
  const h = Math.abs(y2 - y1);

  ctx.strokeStyle = "#666";
  ctx.setLineDash([5, 5]);
  ctx.strokeRect(x, y, w, h);
  ctx.setLineDash([]);
}

function drawStep(ctx: CanvasRenderingContext2D, x: number, y: number, num: number, diameter: number = 28) {
  const radius = diameter / 2;

  // 画圆
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fill();

  // 画数字（字体大小根据直径调整）
  ctx.fillStyle = "#FFFFFF";
  const fontSize = Math.max(10, Math.round(radius * 0.9));
  ctx.font = `bold ${fontSize}px Arial`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(String(num), x, y);
}

function drawText(ctx: CanvasRenderingContext2D, x: number, y: number, text: string, color: string, widthLevel: number) {
  ctx.fillStyle = color;
  // 使用与内联编辑器一致的字体大小计算
  const fontSize = getTextFontSize(widthLevel);
  ctx.font = `${fontSize}px "Microsoft YaHei", sans-serif`;
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  ctx.fillText(text, x, y);
}

// ============================================
// 文字输入处理
// ============================================

/**
 * 开始内联文字输入（直接在 Canvas 上输入，与 Python 版本一致）
 */
function startInlineTextInput(x: number, y: number, editingItem: DrawOperation | null = null) {
  // 计算字体大小
  const fontSize = getTextFontSize(currentWidthLevel);
  const initialText = editingItem?.text || "";

  inlineEditor = {
    active: true,
    position: { x, y },
    text: initialText,
    cursorPos: initialText.length,
    cursorVisible: true,
    color: editingItem?.color || currentColor,
    fontSize: fontSize,
    editingItem: editingItem,
    inputElement: null,
    isComposing: false,
  };

  // 创建真实 input 元素以支持 IME 输入（中文、日文、韩文等）
  createImeInputElement(x, y, fontSize, initialText);

  // 启动光标闪烁定时器（canvas 上的光标闪烁）
  startCursorBlink();

  // 重绘以显示编辑器
  redrawCanvas();
}

/**
 * 创建用于 IME 输入的真实 input 元素
 * 
 * 浏览器的 IME（输入法）只在真实 input/textarea 元素上工作。
 * 创建一个透明但能接收焦点的 input，接收所有键盘和 IME 输入，
 * 然后同步到 inlineEditor 状态并在 canvas 上渲染。
 */
function createImeInputElement(x: number, y: number, fontSize: number, initialText: string) {
  // 清理之前可能残留的 input
  removeImeInputElement();

  const rect = getSelectionRect();
  const input = document.createElement("input");
  input.type = "text";
  input.value = initialText;

  // 定位在文字编辑位置（与 canvas 对齐），但设为透明
  // 使用 fixed 定位与 canvas 坐标系一致
  input.style.cssText = `
    position: fixed;
    left: ${rect.x + x}px;
    top: ${rect.y + y}px;
    font-size: ${fontSize}px;
    font-family: "Microsoft YaHei", sans-serif;
    color: transparent;
    background: transparent;
    border: none;
    outline: none;
    padding: 0;
    margin: 0;
    min-width: 2px;
    width: ${Math.max(200, (initialText.length + 5) * fontSize * 0.6)}px;
    height: ${fontSize * 1.4}px;
    caret-color: transparent;
    z-index: 300;
    opacity: 0;
    pointer-events: auto;
  `;

  // IME 合成事件
  input.addEventListener("compositionstart", () => {
    inlineEditor.isComposing = true;
  });

  input.addEventListener("compositionupdate", (e) => {
    // 合成过程中，显示候选文本
    if (e.data) {
      // Text parts computed for future IME composition rendering
      void inlineEditor.text.slice(0, inlineEditor.cursorPos);
      void inlineEditor.text.slice(inlineEditor.cursorPos);
      // 临时显示合成文本（用 input.value 同步）
      // 实际文本等 compositionend 再更新
    }
    redrawCanvas();
  });

  input.addEventListener("compositionend", (_e) => {
    inlineEditor.isComposing = false;
    // 合成完成，同步最终文本
    syncFromInputElement();
    redrawCanvas();
  });

  // input 事件：捕获所有文本变化（包括 IME 合成后的结果）
  input.addEventListener("input", () => {
    if (!inlineEditor.isComposing) {
      syncFromInputElement();
      redrawCanvas();
    }
  });

  // 按键事件：处理 Enter、Escape 等控制键
  input.addEventListener("keydown", (e) => {
    if (inlineEditor.isComposing) return; // IME 合成中，不处理

    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      finishInlineTextInput(false);
      return;
    }

    if (e.key === "Enter") {
      e.preventDefault();
      e.stopPropagation();
      finishInlineTextInput(true);
      return;
    }
  });

  // 失去焦点时完成输入（点击其他地方）
  input.addEventListener("blur", () => {
    // 延迟处理，防止在 composition 期间触发
    setTimeout(() => {
      if (inlineEditor.active && !inlineEditor.isComposing) {
        finishInlineTextInput(true);
      }
    }, 100);
  });

  document.body.appendChild(input);
  inlineEditor.inputElement = input;

  // 聚焦 input，触发 IME
  requestAnimationFrame(() => {
    input.focus();
    input.setSelectionRange(initialText.length, initialText.length);
  });
}

/**
 * 从 input 元素同步文本到 inlineEditor 状态
 */
function syncFromInputElement() {
  if (!inlineEditor.inputElement) return;
  const newText = inlineEditor.inputElement.value;
  inlineEditor.text = newText;
  inlineEditor.cursorPos = inlineEditor.inputElement.selectionStart ?? newText.length;
  
  // 动态调整 input 宽度
  const estimatedWidth = Math.max(200, (newText.length + 5) * inlineEditor.fontSize * 0.6);
  inlineEditor.inputElement.style.width = `${estimatedWidth}px`;
}

/**
 * 移除 IME input 元素
 */
function removeImeInputElement() {
  if (inlineEditor.inputElement) {
    inlineEditor.inputElement.remove();
    inlineEditor.inputElement = null;
  }
  inlineEditor.isComposing = false;
}

/**
 * 根据粗细级别获取文字字体大小
 */
function getTextFontSize(level: number): number {
  // 级别 1-10 对应字体大小 12-48px
  const minSize = 12;
  const maxSize = 48;
  const clampedLevel = Math.max(1, Math.min(10, level));
  return minSize + (clampedLevel - 1) * (maxSize - minSize) / 9;
}

/**
 * 完成内联文字输入
 */
function finishInlineTextInput(save: boolean = true) {
  if (!inlineEditor.active) return;

  // 从 input 元素同步最终文本（确保获取最新内容）
  syncFromInputElement();

  // 停止光标闪烁
  stopCursorBlink();

  // 清理 IME input 元素
  removeImeInputElement();

  if (save && inlineEditor.text.trim()) {
    if (inlineEditor.editingItem) {
      // 更新已有文字
      inlineEditor.editingItem.text = inlineEditor.text;
    } else {
      // 创建新文字
      const operation: DrawOperation = {
        id: generateOperationId(),
        tool: "text",
        color: inlineEditor.color,
        width: currentWidthLevel,
        points: [{ x: inlineEditor.position.x, y: inlineEditor.position.y }],
        text: inlineEditor.text,
      };

      drawOperations.push(operation);

      // 记录撤销操作
      undoStack.push({
        type: "create",
        operationId: operation.id,
        operation: { ...operation, points: operation.points.map(p => ({ ...p })) },
      });
      redoStack = [];
    }
  }

  // 重置编辑器状态
  inlineEditor.active = false;
  inlineEditor.text = "";
  inlineEditor.cursorPos = 0;
  inlineEditor.editingItem = null;

  redrawCanvas();
}

/**
 * 启动光标闪烁定时器
 */
function startCursorBlink() {
  stopCursorBlink();
  cursorBlinkTimer = window.setInterval(() => {
    if (inlineEditor.active) {
      inlineEditor.cursorVisible = !inlineEditor.cursorVisible;
      redrawCanvas();
    }
  }, 500);
}

/**
 * 停止光标闪烁定时器
 */
function stopCursorBlink() {
  if (cursorBlinkTimer !== null) {
    clearInterval(cursorBlinkTimer);
    cursorBlinkTimer = null;
  }
}

/**
 * 处理文字编辑按键
 * 
 * 有真实 input 元素时，大部分输入由 input 处理（包括 IME 合成）。
 * 这里仅处理从 window/document 级别捕获的事件，用于：
 * - 确保 input 元素保持焦点
 * - 处理 Escape/Enter 等控制键（作为后备，input 上也有监听）
 * - IME 合成期间不拦截任何按键
 */
function handleTextEditKey(e: KeyboardEvent): boolean {
  if (!inlineEditor.active) return false;

  // IME 合成期间，不拦截任何按键，让 input 元素原生处理
  if (inlineEditor.isComposing || e.isComposing) {
    return true; // 返回 true 阻止 overlay 的其他快捷键处理
  }

  const key = e.key;

  // Escape：取消输入
  if (key === "Escape") {
    finishInlineTextInput(false);
    e.preventDefault();
    return true;
  }

  // Enter：确认输入
  if (key === "Enter") {
    finishInlineTextInput(true);
    e.preventDefault();
    return true;
  }

  // 如果有 input 元素，确保焦点在 input 上，让 input 处理其余按键
  if (inlineEditor.inputElement) {
    if (document.activeElement !== inlineEditor.inputElement) {
      inlineEditor.inputElement.focus();
    }
    // 不拦截按键，让 input 元素原生处理（Backspace、方向键、字符输入等）
    return true;
  }

  // 以下是无 input 元素时的后备处理（不应该触发，但保留兼容性）
  if (key === "Backspace") {
    if (inlineEditor.cursorPos > 0) {
      inlineEditor.text =
        inlineEditor.text.slice(0, inlineEditor.cursorPos - 1) +
        inlineEditor.text.slice(inlineEditor.cursorPos);
      inlineEditor.cursorPos--;
      redrawCanvas();
    }
    e.preventDefault();
    return true;
  }

  if (key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
    inlineEditor.text =
      inlineEditor.text.slice(0, inlineEditor.cursorPos) +
      key +
      inlineEditor.text.slice(inlineEditor.cursorPos);
    inlineEditor.cursorPos++;
    redrawCanvas();
    e.preventDefault();
    return true;
  }

  return true; // 阻止其他快捷键在文字编辑期间触发
}

/**
 * 绘制内联文字编辑器（文字 + 光标）
 * 
 * 当有真实 input 元素时，文本从 input 同步渲染到 canvas 上，
 * 光标由 input 元素自身显示（不在 canvas 上画光标）。
 */
function drawInlineEditor(ctx: CanvasRenderingContext2D) {
  if (!inlineEditor.active) return;

  const { position, text, cursorPos, cursorVisible, color, fontSize } = inlineEditor;

  ctx.save();
  ctx.fillStyle = color;
  ctx.font = `${fontSize}px "Microsoft YaHei", sans-serif`;
  ctx.textAlign = "left";
  ctx.textBaseline = "top";

  // 绘制已确认的文字
  if (text) {
    ctx.fillText(text, position.x, position.y);
  }

  // 绘制光标（仅在没有真实 input 元素时使用 canvas 光标）
  if (!inlineEditor.inputElement && cursorVisible) {
    const textBeforeCursor = text.slice(0, cursorPos);
    const cursorX = position.x + ctx.measureText(textBeforeCursor).width;
    const cursorY = position.y;
    const cursorHeight = fontSize * 1.2;

    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cursorX, cursorY);
    ctx.lineTo(cursorX, cursorY + cursorHeight);
    ctx.stroke();
  }

  // 绘制光标（有 input 元素时也画一个，因为 input 是透明的）
  if (inlineEditor.inputElement) {
    const textBeforeCursor = text.slice(0, cursorPos);
    const cursorX = position.x + ctx.measureText(textBeforeCursor).width;
    const cursorY = position.y;
    const cursorHeight = fontSize * 1.2;

    // 闪烁效果
    if (cursorVisible) {
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(cursorX, cursorY);
      ctx.lineTo(cursorX, cursorY + cursorHeight);
      ctx.stroke();
    }
  }

  ctx.restore();
}

// ============================================
// 窗口探测功能
// ============================================

/**
 * 探测鼠标位置下的窗口
 * 使用节流控制调用频率（50ms）
 */
async function detectWindowAtPosition(screenX: number, screenY: number) {
  if (!windowDetectEnabled) return;

  // 节流控制
  const now = Date.now();
  if (now - lastDetectTime < DETECT_THROTTLE_MS) return;
  lastDetectTime = now;

  try {
    const scaleFactor = monitorInfo?.scaleFactor || 1;
    const monitorX = monitorInfo?.position.x || 0;
    const monitorY = monitorInfo?.position.y || 0;

    // 转换为物理像素坐标
    const physicalX = Math.round(screenX * scaleFactor) + monitorX;
    const physicalY = Math.round(screenY * scaleFactor) + monitorY;

    console.debug("[Overlay] 窗口探测: 视口坐标", { screenX, screenY },
                "物理坐标", { physicalX, physicalY },
                "显示器", { monitorX, monitorY, scaleFactor });

    const result = await invoke<DetectedWindow | null>("detect_window_at", {
      x: physicalX,
      y: physicalY,
    });

    console.debug("[Overlay] 窗口探测结果:", result);

    if (result) {
      detectedWindow = result;
      showWindowHighlight(result.physicalRect);
    } else {
      detectedWindow = null;
      hideWindowHighlight();
    }
  } catch (error) {
    console.error("[Overlay] 窗口探测失败:", error);
    detectedWindow = null;
    hideWindowHighlight();
  }
}

/**
 * 显示窗口高亮框
 *
 * 修复 DPR 不匹配问题：直接使用物理像素坐标进行转换
 * - physicalRect: 物理像素坐标（从 Rust 端获取）
 * - 使用 monitorInfo.scaleFactor 统一转换到视口逻辑坐标
 */
function showWindowHighlight(physicalRect: { x: number; y: number; width: number; height: number }) {
  if (!windowHighlightElement || !monitorInfo) {
    console.warn("[Overlay] showWindowHighlight: 元素或显示器信息缺失",
                 { hasElement: !!windowHighlightElement, hasMonitor: !!monitorInfo });
    return;
  }

  const scaleFactor = monitorInfo.scaleFactor;
  const monitorPhysX = monitorInfo.position.x;
  const monitorPhysY = monitorInfo.position.y;

  // 使用物理像素坐标统一转换到视口逻辑坐标
  // 这样避免了 Rust 端窗口 DPR 与显示器 scaleFactor 不匹配的问题
  const localX = (physicalRect.x - monitorPhysX) / scaleFactor;
  const localY = (physicalRect.y - monitorPhysY) / scaleFactor;
  const localWidth = physicalRect.width / scaleFactor;
  const localHeight = physicalRect.height / scaleFactor;

  console.debug("[Overlay] showWindowHighlight:", {
    物理rect: physicalRect,
    显示器物理位置: { monitorPhysX, monitorPhysY },
    scaleFactor,
    本地坐标: { localX, localY, localWidth, localHeight }
  });

  windowHighlightElement.style.left = `${localX}px`;
  windowHighlightElement.style.top = `${localY}px`;
  windowHighlightElement.style.width = `${localWidth}px`;
  windowHighlightElement.style.height = `${localHeight}px`;
  windowHighlightElement.style.display = "block";

  // 更新尺寸标签（直接使用物理尺寸）
  if (sizeLabelElement) {
    sizeLabelElement.textContent = `${physicalRect.width} × ${physicalRect.height}`;
    sizeLabelElement.style.left = `${localX}px`;
    sizeLabelElement.style.top = `${localY + localHeight + 8}px`;
    sizeLabelElement.style.display = "block";
  }
}

/**
 * 隐藏窗口高亮框
 */
function hideWindowHighlight() {
  if (windowHighlightElement) {
    windowHighlightElement.style.display = "none";
  }
}

/**
 * 使用探测到的窗口作为选区
 *
 * 修复 DPR 不匹配问题：使用 physicalRect 统一转换
 * 优化：先显示工具栏，再执行截图（提升响应速度）
 */
async function selectDetectedWindow() {
  if (!detectedWindow || !monitorInfo) return false;

  // 使用物理像素坐标，避免 DPR 不匹配问题
  const physicalRect = detectedWindow.physicalRect;
  const scaleFactor = monitorInfo.scaleFactor;
  const monitorPhysX = monitorInfo.position.x;
  const monitorPhysY = monitorInfo.position.y;

  // 转换为视口逻辑坐标
  const localX = (physicalRect.x - monitorPhysX) / scaleFactor;
  const localY = (physicalRect.y - monitorPhysY) / scaleFactor;
  const localWidth = physicalRect.width / scaleFactor;
  const localHeight = physicalRect.height / scaleFactor;

  // 设置选区状态
  selectionState.startX = localX;
  selectionState.startY = localY;
  selectionState.endX = localX + localWidth;
  selectionState.endY = localY + localHeight;
  selectionState.hasSelection = true;

  console.debug("[Overlay] selectDetectedWindow:", {
    physicalRect,
    scaleFactor,
    monitorPos: { monitorPhysX, monitorPhysY },
    localCoords: { localX, localY, localWidth, localHeight }
  });

  // 隐藏窗口高亮
  hideWindowHighlight();
  detectedWindow = null;

  // 更新选区显示
  updateSelectionRect();

  const selRect = getSelectionRect();

  // 优化：先初始化绘图 Canvas 和显示工具栏，提升响应速度
  initDrawingCanvas(selRect);
  showToolbars(selRect);

  // 然后执行截图捕获（异步，不阻塞 UI）
  await captureSelection(selRect, { triggerOcr: AUTO_OCR_ON_SELECTION });

  return true;
}

// ============================================
// 编辑功能 - ID生成
// ============================================

function generateOperationId(): number {
  return ++operationIdCounter;
}

// ============================================
// 编辑功能 - 边界计算
// ============================================

function getBoundingRect(op: DrawOperation): BoundingRect {
  const points = op.points;
  if (points.length === 0) {
    return { x: 0, y: 0, width: 0, height: 0 };
  }

  // 编号工具：以中心点为圆心，使用保存的直径
  if (op.tool === "step") {
    const diameter = op.width > 10 ? op.width : 28;
    const radius = diameter / 2;
    const p = points[points.length - 1];
    return {
      x: p.x - radius,
      y: p.y - radius,
      width: radius * 2,
      height: radius * 2,
    };
  }

  // 文字工具：估算文字边界
  if (op.tool === "text" && op.text) {
    const p = points[0];
    const fontSize = op.width * 6;
    const textWidth = op.text.length * fontSize * 0.6; // 估算宽度
    return {
      x: p.x,
      y: p.y,
      width: Math.max(textWidth, 20),
      height: fontSize * 1.2,
    };
  }

  // 画笔工具：包含所有点的边界
  if (op.tool === "pen" || op.tool === "marker") {
    let minX = Infinity, minY = Infinity;
    let maxX = -Infinity, maxY = -Infinity;
    for (const p of points) {
      minX = Math.min(minX, p.x);
      minY = Math.min(minY, p.y);
      maxX = Math.max(maxX, p.x);
      maxY = Math.max(maxY, p.y);
    }
    // 添加线宽边距
    const padding = op.width / 2;
    return {
      x: minX - padding,
      y: minY - padding,
      width: maxX - minX + op.width,
      height: maxY - minY + op.width,
    };
  }

  // 其他工具（rect, ellipse, arrow, line, mosaic）：起点和终点构成的矩形
  const startX = points[0].x;
  const startY = points[0].y;
  const endX = points[points.length - 1].x;
  const endY = points[points.length - 1].y;

  const x = Math.min(startX, endX);
  const y = Math.min(startY, endY);
  const width = Math.abs(endX - startX);
  const height = Math.abs(endY - startY);

  return { x, y, width, height };
}

// ============================================
// 编辑功能 - 点击检测
// ============================================

function pointToLineDistance(px: number, py: number, x1: number, y1: number, x2: number, y2: number): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lengthSquared = dx * dx + dy * dy;

  if (lengthSquared === 0) {
    // 线段为点
    return Math.sqrt((px - x1) ** 2 + (py - y1) ** 2);
  }

  // 投影参数 t
  let t = ((px - x1) * dx + (py - y1) * dy) / lengthSquared;
  t = Math.max(0, Math.min(1, t));

  // 最近点
  const nearestX = x1 + t * dx;
  const nearestY = y1 + t * dy;

  return Math.sqrt((px - nearestX) ** 2 + (py - nearestY) ** 2);
}

function operationContainsPoint(op: DrawOperation, x: number, y: number): boolean {
  const tolerance = 8; // 点击容差
  const points = op.points;

  if (points.length < 1) return false;

  // 编号工具：圆形区域（使用保存的直径）
  if (op.tool === "step") {
    const p = points[points.length - 1];
    const diameter = op.width > 10 ? op.width : 28;
    const radius = diameter / 2;
    const dist = Math.sqrt((x - p.x) ** 2 + (y - p.y) ** 2);
    return dist <= radius + tolerance;
  }

  // 文字工具：边界矩形
  if (op.tool === "text") {
    const rect = getBoundingRect(op);
    return x >= rect.x - tolerance && x <= rect.x + rect.width + tolerance &&
           y >= rect.y - tolerance && y <= rect.y + rect.height + tolerance;
  }

  // 直线和箭头：点到线段的距离
  if (op.tool === "line" || op.tool === "arrow") {
    if (points.length < 2) return false;
    const dist = pointToLineDistance(
      x, y,
      points[0].x, points[0].y,
      points[points.length - 1].x, points[points.length - 1].y
    );
    return dist <= op.width / 2 + tolerance;
  }

  // 画笔工具：检测是否靠近任意线段
  if (op.tool === "pen") {
    for (let i = 1; i < points.length; i++) {
      const dist = pointToLineDistance(
        x, y,
        points[i - 1].x, points[i - 1].y,
        points[i].x, points[i].y
      );
      if (dist <= op.width / 2 + tolerance) return true;
    }
    return false;
  }

  // 矩形、椭圆、高亮、马赛克：边界矩形
  const rect = getBoundingRect(op);
  return x >= rect.x - tolerance && x <= rect.x + rect.width + tolerance &&
         y >= rect.y - tolerance && y <= rect.y + rect.height + tolerance;
}

function findOperationAt(x: number, y: number): DrawOperation | null {
  // 从后向前查找（后绘制的在上层）
  for (let i = drawOperations.length - 1; i >= 0; i--) {
    if (operationContainsPoint(drawOperations[i], x, y)) {
      return drawOperations[i];
    }
  }
  return null;
}

// ============================================
// 编辑功能 - 缩放手柄检测
// ============================================

const HANDLE_SIZE = 8;

function getResizeHandleAt(op: DrawOperation, x: number, y: number): ResizeHandle {
  const rect = getBoundingRect(op);
  const hs = HANDLE_SIZE;

  // 左上角
  if (x >= rect.x - hs && x <= rect.x + hs &&
      y >= rect.y - hs && y <= rect.y + hs) {
    return "tl";
  }
  // 右上角
  if (x >= rect.x + rect.width - hs && x <= rect.x + rect.width + hs &&
      y >= rect.y - hs && y <= rect.y + hs) {
    return "tr";
  }
  // 左下角
  if (x >= rect.x - hs && x <= rect.x + hs &&
      y >= rect.y + rect.height - hs && y <= rect.y + rect.height + hs) {
    return "bl";
  }
  // 右下角
  if (x >= rect.x + rect.width - hs && x <= rect.x + rect.width + hs &&
      y >= rect.y + rect.height - hs && y <= rect.y + rect.height + hs) {
    return "br";
  }

  return "";
}

// ============================================
// 编辑功能 - 移动和缩放
// ============================================

function calculateNewBounds(oldBounds: BoundingRect, handle: ResizeHandle, x: number, y: number): BoundingRect {
  const newBounds = { ...oldBounds };

  switch (handle) {
    case "tl":
      newBounds.width += newBounds.x - x;
      newBounds.height += newBounds.y - y;
      newBounds.x = x;
      newBounds.y = y;
      break;
    case "tr":
      newBounds.width = x - newBounds.x;
      newBounds.height += newBounds.y - y;
      newBounds.y = y;
      break;
    case "bl":
      newBounds.width += newBounds.x - x;
      newBounds.x = x;
      newBounds.height = y - newBounds.y;
      break;
    case "br":
      newBounds.width = x - newBounds.x;
      newBounds.height = y - newBounds.y;
      break;
  }

  // 确保最小尺寸
  const minSize = 10;
  if (newBounds.width < minSize) {
    if (handle === "tl" || handle === "bl") {
      newBounds.x = oldBounds.x + oldBounds.width - minSize;
    }
    newBounds.width = minSize;
  }
  if (newBounds.height < minSize) {
    if (handle === "tl" || handle === "tr") {
      newBounds.y = oldBounds.y + oldBounds.height - minSize;
    }
    newBounds.height = minSize;
  }

  return newBounds;
}

function resizeOperation(op: DrawOperation, oldBounds: BoundingRect, newBounds: BoundingRect) {
  // 计算缩放比例
  const scaleX = oldBounds.width > 0 ? newBounds.width / oldBounds.width : 1;
  const scaleY = oldBounds.height > 0 ? newBounds.height / oldBounds.height : 1;

  // 文字工具特殊处理：缩放时同步调整字体大小
  if (op.tool === "text") {
    // 使用较大的缩放比例（让用户拉伸任意方向都能放大字体）
    const scale = Math.max(scaleX, scaleY);
    const currentFontSize = op.width * 6;
    const newFontSize = currentFontSize * scale;
    const clampedSize = Math.max(TEXT_FONT_SIZE_MIN, Math.min(TEXT_FONT_SIZE_MAX, newFontSize));
    op.width = Math.round(clampedSize / 6);

    // 同步更新工具栏粗细按钮显示
    const newWidthLevel = Math.max(1, Math.min(10, Math.round((clampedSize - TEXT_FONT_SIZE_MIN) / 2) + 1));
    currentWidthLevel = newWidthLevel;
    updateWidthButton(currentWidthLevel);

    // 更新文字位置（锚点在左上角）
    if (op.points.length > 0) {
      op.points[0].x = newBounds.x;
      op.points[0].y = newBounds.y;
    }
    return;
  }

  // 其他工具：缩放所有点
  for (const p of op.points) {
    const relX = p.x - oldBounds.x;
    const relY = p.y - oldBounds.y;
    p.x = newBounds.x + relX * scaleX;
    p.y = newBounds.y + relY * scaleY;
  }
}

// ============================================
// 编辑功能 - 选中框渲染
// ============================================

function drawSelectionHandles(ctx: CanvasRenderingContext2D, op: DrawOperation, isHovered: boolean) {
  const rect = getBoundingRect(op);
  const hs = HANDLE_SIZE;

  ctx.save();

  // 虚线边框
  ctx.strokeStyle = isHovered ? "#4A90D9" : "#0078D7";
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 4]);
  ctx.strokeRect(rect.x - 2, rect.y - 2, rect.width + 4, rect.height + 4);
  ctx.setLineDash([]);

  // 四角手柄（仅选中状态显示）
  if (!isHovered) {
    ctx.fillStyle = "#FFFFFF";
    ctx.strokeStyle = "#0078D7";
    ctx.lineWidth = 1;

    const handles = [
      { x: rect.x - hs / 2, y: rect.y - hs / 2 },           // tl
      { x: rect.x + rect.width - hs / 2, y: rect.y - hs / 2 },     // tr
      { x: rect.x - hs / 2, y: rect.y + rect.height - hs / 2 },    // bl
      { x: rect.x + rect.width - hs / 2, y: rect.y + rect.height - hs / 2 }, // br
    ];

    for (const h of handles) {
      ctx.fillRect(h.x, h.y, hs, hs);
      ctx.strokeRect(h.x, h.y, hs, hs);
    }
  }

  ctx.restore();
}

// ============================================
// 编辑功能 - 光标更新
// ============================================

function updateCursor(x: number, y: number) {
  if (!maskElement) return;

  // 如果正在移动或缩放，保持当前光标
  if (editMode === "moving") {
    maskElement.style.cursor = "move";
    return;
  }
  if (editMode === "resizing") {
    setCursorForHandle(activeResizeHandle);
    return;
  }

  // 选区编辑光标（没有标注时）
  if (canEditSelection()) {
    const selectionRect = getSelectionRect();
    const handle = getSelectionResizeHandleAt(x, y, selectionRect);
    if (handle) {
      setCursorForSelectionHandle(handle);
      return;
    }

    const inSelection = x >= 0 && y >= 0 && x <= selectionRect.width && y <= selectionRect.height;
    if (inSelection) {
      maskElement.style.cursor = "move";
      return;
    }
  }

  // 检测是否在选中项的手柄上
  if (selectedOperationId !== null) {
    const selectedOp = drawOperations.find(op => op.id === selectedOperationId);
    if (selectedOp) {
      const handle = getResizeHandleAt(selectedOp, x, y);
      if (handle) {
        setCursorForHandle(handle);
        return;
      }
      // 在选中项内部
      if (operationContainsPoint(selectedOp, x, y)) {
        maskElement.style.cursor = "move";
        return;
      }
    }
  }

  // 检测悬停
  const hoverOp = findOperationAt(x, y);
  if (hoverOp) {
    hoveredOperationId = hoverOp.id;
    maskElement.style.cursor = "pointer";
    redrawCanvas();
    return;
  }

  // 清除悬停
  if (hoveredOperationId !== null) {
    hoveredOperationId = null;
    redrawCanvas();
  }

  // 默认十字光标
  maskElement.style.cursor = "crosshair";
}

function setCursorForHandle(handle: ResizeHandle) {
  if (!maskElement) return;
  switch (handle) {
    case "tl":
    case "br":
      maskElement.style.cursor = "nwse-resize";
      break;
    case "tr":
    case "bl":
      maskElement.style.cursor = "nesw-resize";
      break;
    default:
      maskElement.style.cursor = "default";
  }
}

function setCursorForSelectionHandle(handle: SelectionResizeHandle) {
  if (!maskElement) return;
  switch (handle) {
    case "nw":
    case "se":
      maskElement.style.cursor = "nwse-resize";
      break;
    case "ne":
    case "sw":
      maskElement.style.cursor = "nesw-resize";
      break;
    case "n":
    case "s":
      maskElement.style.cursor = "ns-resize";
      break;
    case "e":
    case "w":
      maskElement.style.cursor = "ew-resize";
      break;
    default:
      maskElement.style.cursor = "default";
  }
}

// ============================================
// 编辑功能 - 取消选中
// ============================================

function deselectOperation() {
  selectedOperationId = null;
  editMode = "idle";
  activeResizeHandle = "";
  redrawCanvas();
}

// ============================================
// 截图捕获
// ============================================

async function captureSelection(
  rect: { x: number; y: number; width: number; height: number },
  options: { triggerOcr?: boolean } = {}
) {
  const shouldTriggerOcr = options.triggerOcr ?? false;

  if (captureInProgress) {
    queuedCaptureRect = { ...rect };
    queuedCaptureTriggerOcr = queuedCaptureTriggerOcr || shouldTriggerOcr;
    return;
  }

  captureInProgress = true;
  setActionButtonsDisabled(true);

  try {
    const scaleFactor = monitorInfo?.scaleFactor || 1;
    const monitorX = monitorInfo?.position.x || 0;
    const monitorY = monitorInfo?.position.y || 0;

    const physicalRect = {
      x: Math.round(rect.x * scaleFactor) + monitorX,
      y: Math.round(rect.y * scaleFactor) + monitorY,
      width: Math.round(rect.width * scaleFactor),
      height: Math.round(rect.height * scaleFactor),
    };

    console.debug("[Overlay] 捕获区域（物理像素）:", physicalRect);

    captureResult = await invoke<CaptureResult>("capture_region", { rect: physicalRect });
    console.debug("[Overlay] 截图成功:", captureResult);
    resetOcrCache();

    if (shouldRestoreOverlayFocusAfterCapture({
      overlaySessionActive,
      pendingOcrAfterCapture: pendingOcrAfterCapture !== null,
      triggerOcr: shouldTriggerOcr,
    })) {
      try {
        const currentWindow = getCurrentWindow();
        await currentWindow.setFocus();
        window.focus();
        if (maskElement) maskElement.focus();
      } catch (focusErr) {
        console.warn("[Overlay] 截图完成后重新聚焦失败:", focusErr);
      }
    }
  } catch (error) {
    console.error("[Overlay] 截图失败:", error);
    showToast("截图失败: " + error);
  } finally {
    captureInProgress = false;

    if (queuedCaptureRect) {
      const nextRect = queuedCaptureRect;
      queuedCaptureRect = null;
      const nextTrigger = queuedCaptureTriggerOcr;
      queuedCaptureTriggerOcr = false;
      await captureSelection(nextRect, { triggerOcr: nextTrigger });
      return;
    }

    setActionButtonsDisabled(false);

    const pendingRequest = pendingOcrAfterCapture;
    const autoRequest = shouldTriggerOcr ? OCR_REQUEST_AUTO : null;
    pendingOcrAfterCapture = null;

    const requestToRun = pendingRequest ?? autoRequest;
    if (shouldScheduleQueuedOcrAfterCapture({
      overlaySessionActive,
      hasCaptureResult: captureResult !== null,
      hasQueuedRequest: requestToRun !== null,
    }) && requestToRun) {
      scheduleOcrRequest(requestToRun);
    } else if (requestToRun) {
      console.debug("[Overlay] overlay 会话已结束或截图结果不可用，已取消排队 OCR");
    }
  }
}

function clearAutoOcrTimer() {
  if (autoOcrTimer !== null) {
    window.clearTimeout(autoOcrTimer);
    autoOcrTimer = null;
  }
}

function scheduleOcrRequest(request: OcrRequestOptions) {
  if (!captureResult) return;

  // 手动 OCR 立即触发；自动 OCR 做短延迟，避免和复制抢资源
  if (request.reason !== "auto") {
    void doOcr(request);
    return;
  }

  clearAutoOcrTimer();

  if (isCopyInProgress || suspendAutoOcr) {
    console.debug("[Overlay] 自动 OCR 已暂停（复制优先）");
    return;
  }

  autoOcrTimer = window.setTimeout(() => {
    autoOcrTimer = null;

    if (!captureResult || !selectionState.hasSelection) {
      return;
    }

    if (isCopyInProgress || suspendAutoOcr) {
      console.debug("[Overlay] 自动 OCR 延迟触发被取消（复制优先）");
      return;
    }

    void doOcr(request);
  }, AUTO_OCR_DEFER_MS);
}

// ============================================
// 操作处理函数
// ============================================

// 截图保存配置缓存
interface ScreenshotSaveConfig {
  saveLocation: string;
  autoSave: boolean;
}
let cachedSaveConfig: ScreenshotSaveConfig | null = null;

/**
 * 获取截图保存配置（带缓存）
 */
async function getSaveConfig(): Promise<ScreenshotSaveConfig> {
  if (!cachedSaveConfig) {
    try {
      cachedSaveConfig = await invoke<ScreenshotSaveConfig>("get_screenshot_save_config");
    } catch (error) {
      console.warn("[Overlay] 获取保存配置失败，使用默认值:", error);
      cachedSaveConfig = {
        saveLocation: "",
        autoSave: false,
      };
    }
  }
  return cachedSaveConfig;
}

async function handleSave() {
  if (!captureResult) {
    showToast("请先选择截图区域");
    return;
  }

  try {
    // 合成最终图像
    const finalImageData = await compositeImage();

    // 获取保存配置
    const config = await getSaveConfig();

    // 构建元数据
    const metadata: SaveScreenshotMetadata = {
      captureMode: "region",
      monitorId: monitorInfo?.monitorId,
      hasAnnotations: drawOperations.length > 0,
    };

    // 如果有探测到的窗口信息，添加到元数据
    if (detectedWindow) {
      metadata.windowTitle = detectedWindow.title;
    }

    // 如果开启了自动保存，使用新的组合命令保存并添加历史记录
    if (config.autoSave) {
      // 【性能优化】使用文件路径传递，避免 Array.from() 的巨型 JSON 序列化
      let saveFilePath: string;
      if (drawOperations.length > 0) {
        // 有标注：先写入临时文件
        saveFilePath = replaceTempImageExtension(captureResult.path, '_save.png');
        await writeFile(saveFilePath, finalImageData);
      } else {
        // 无标注：直接使用原始文件路径
        saveFilePath = captureResult.path;
      }

      const result = await invoke<SaveScreenshotResult>("save_screenshot_with_history_from_file", {
        filePath: saveFilePath,
        format: "png",
        metadata: metadata,
      });

      showToast("已保存到历史截图!");
      console.debug("[Overlay] 保存并添加历史记录成功:", result);

      // 【修复】立即清理事件监听器，避免延迟关闭期间触发窗口检测
      cleanupMouseEvents();
      cleanupKeyboardEvents();

      // 清理快照临时文件
      await cleanupSnapshotFile();
      setTimeout(closeWindow, 500);
      return;
    }

    // 否则弹出保存对话框
    const filePath = await save({
      defaultPath: `screenshot_${Date.now()}.png`,
      filters: [
        { name: "PNG 图片", extensions: ["png"] },
        { name: "JPEG 图片", extensions: ["jpg", "jpeg"] },
      ],
    });

    if (!filePath) return;

    await writeFile(filePath, finalImageData);

    showToast("保存成功!");

    // 【修复】立即清理事件监听器，避免延迟关闭期间触发窗口检测
    cleanupMouseEvents();
    cleanupKeyboardEvents();

    // 【Task 6.1】清理快照临时文件（Requirements 3.4）
    await cleanupSnapshotFile();
    setTimeout(closeWindow, 500);
  } catch (error) {
    console.error("[Overlay] 保存失败:", error);
    showToast("保存失败: " + error);
  }
}

// 防止 handleCopy 重入（双击可能触发多次调用）
let isCopyInProgress = false;

async function handleCopy() {
  // 防重入：如果正在复制中，直接返回
  if (isCopyInProgress) {
    console.debug("[Overlay] handleCopy 已在执行中，跳过重复调用");
    return;
  }

  if (!captureResult) {
    showToast("请先选择截图区域");
    return;
  }

  isCopyInProgress = true;
  suspendAutoOcr = true;
  clearAutoOcrTimer();
  queuedCaptureTriggerOcr = false;
  pendingOcrAfterCapture = null;
  pendingOcrAfterCurrent = null;

  try {
    // 复制优先：先确保剪贴板写入完成，再做低优先任务

    let clipboardFilePath: string;

    if (drawOperations.length > 0) {
      // 有绘图操作：合成 Canvas → 导出 PNG → 写入临时文件 → 传路径
      const compositeResult = await createCompositeCanvas();
      const pngData = await canvasToPng(compositeResult.canvas);

      // 使用 writeFile（plugin-fs 的二进制 IPC，比 Array.from + JSON 快几十倍）
      clipboardFilePath = captureResult.path.replace(/\.\w+$/i, '_composite.png');
      await writeFile(clipboardFilePath, pngData);
      console.debug("[Overlay] 合成图像已写入临时文件:", clipboardFilePath);
    } else {
      // 无绘图操作：文件已在磁盘上，直接传路径
      clipboardFilePath = captureResult.path;
    }

    // 立即关闭窗口，剪贴板复制在后台完成（不阻塞 UI）
    closeWindow().catch((err) => {
      console.warn("[Overlay] 复制后关闭窗口失败:", err);
    });

    // 有标注时必须读合成文件；无标注时走内存缓存零拷贝
    invoke("copy_last_capture_to_clipboard", {
      filePath: clipboardFilePath,
      useMemoryCache: drawOperations.length === 0,
    }).catch((err) => {
      console.error("[Overlay] 剪贴板复制失败:", err);
    });

    // 低优先：会话清理与历史保存放后台，不阻塞复制
    cleanupSnapshotFile().catch(err => {
      console.warn("[Overlay] 复制后清理快照失败（不影响使用）:", err);
    });

    // 检查工作台窗口是否打开
    let workbenchOpen = false;
    try {
      const workbenchWindow = await WebviewWindow.getByLabel("workbench");
      if (workbenchWindow) {
        workbenchOpen = await workbenchWindow.isVisible();
      }
    } catch {
      // 窗口不存在，忽略
    }

    // 后台保存到历史记录
    if (!workbenchOpen) {
      const historyFilePath = clipboardFilePath;
      invoke<SaveScreenshotResult>("save_screenshot_with_history_from_file", {
        filePath: historyFilePath,
        format: "png",
        metadata: {
          captureMode: "region",
          monitorId: monitorInfo?.monitorId,
          hasAnnotations: drawOperations.length > 0,
          windowTitle: detectedWindow?.title,
        },
      }).then(result => {
        console.debug("[Overlay] 复制时自动保存到历史记录:", result);
      }).catch(historyError => {
        console.warn("[Overlay] 保存到历史记录失败（复制操作不受影响）:", historyError);
      });
    } else {
      console.debug("[Overlay] 工作台已打开，跳过保存到历史记录");
    }
  } catch (error) {
    console.error("[Overlay] 复制失败:", error);
    showToast("复制失败: " + error);
  } finally {
    // 注意：不重置 isCopyInProgress，因为整个窗口即将关闭
    // 如果窗口没关闭（错误场景），300ms 后重置
    setTimeout(() => {
      isCopyInProgress = false;
      suspendAutoOcr = false;
    }, 300);
  }
}

/**
 * 合成图像的结果（包含 Canvas 和 RGBA 数据）
 */
interface CompositeResult {
  canvas: HTMLCanvasElement;
  ctx: CanvasRenderingContext2D;
  width: number;
  height: number;
}

/**
 * 【性能优化】创建合成 Canvas（不导出为 PNG）
 * 
 * 返回 Canvas 对象，调用方可以：
 * - 获取 RGBA 数据用于剪贴板（快速）
 * - 导出为 PNG 用于保存文件（需要时才做）
 */
async function createCompositeCanvas(): Promise<CompositeResult> {
  if (!captureResult) {
    throw new Error("没有截图结果");
  }

  // 创建合成 Canvas
  const compositeCanvas = document.createElement("canvas");
  const ctx = compositeCanvas.getContext("2d");
  if (!ctx) throw new Error("无法创建 Canvas 上下文");

  compositeCanvas.width = captureResult.width;
  compositeCanvas.height = captureResult.height;

  // 加载原始截图
  const imageData = await readFile(captureResult.path);
  const blob = new Blob([imageData], { type: "image/png" });
  const url = URL.createObjectURL(blob);

  await new Promise<void>((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      resolve();
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("加载图像失败"));
    };
    img.src = url;
  });

  // 绘制标注层
  // 注意：不要直接绘制 drawingCanvas，避免快照背景导致的 Canvas taint
  const scaleFactor = monitorInfo?.scaleFactor || 1;
  if (drawOperations.length > 0 || inlineEditor.active) {
    ctx.save();
    ctx.scale(scaleFactor, scaleFactor);
    renderDrawOperations(ctx);
    drawInlineEditor(ctx);
    ctx.restore();
  }

  return {
    canvas: compositeCanvas,
    ctx,
    width: compositeCanvas.width,
    height: compositeCanvas.height,
  };
}

/**
 * 从 Canvas 导出 PNG 数据
 */
async function canvasToPng(canvas: HTMLCanvasElement): Promise<Uint8Array> {
  return new Promise<Uint8Array>((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          reject(new Error("导出图像失败"));
          return;
        }
        blob.arrayBuffer().then((buffer) => {
          resolve(new Uint8Array(buffer));
        });
      },
      "image/png"
    );
  });
}

/**
 * 合成图像并导出为 PNG（兼容旧接口）
 */
async function compositeImage(): Promise<Uint8Array> {
  if (!captureResult) {
    throw new Error("没有截图结果");
  }

  // 如果没有绘图操作，直接返回原始图像
  if (drawOperations.length === 0) {
    return await readFile(captureResult.path);
  }

  const { canvas } = await createCompositeCanvas();
  return canvasToPng(canvas);
}

function handleUndo(silent = false) {
  if (undoStack.length === 0) {
    showToast("没有可撤销的操作");
    return;
  }

  const action = undoStack.pop()!;

  switch (action.type) {
    case "create": {
      // 撤销创建：删除操作
      const index = drawOperations.findIndex(op => op.id === action.operationId);
      if (index !== -1) {
        const removed = drawOperations.splice(index, 1)[0];
        // 如果撤销的是编号，回退编号计数器
        if (removed.tool === "step") {
          stepCounter = Math.max(1, stepCounter - 1);
        }
        // 如果删除的是选中项，取消选中
        if (selectedOperationId === removed.id) {
          deselectOperation();
        }
      }
      break;
    }
    case "move":
    case "resize": {
      // 撤销移动/缩放：恢复原始点
      const op = drawOperations.find(op => op.id === action.operationId);
      if (op && action.previousPoints) {
        for (let i = 0; i < op.points.length && i < action.previousPoints.length; i++) {
          op.points[i].x = action.previousPoints[i].x;
          op.points[i].y = action.previousPoints[i].y;
        }
      }
      break;
    }
    case "delete": {
      // 撤销删除：恢复操作
      if (action.operation) {
        drawOperations.push({ ...action.operation, points: action.operation.points.map(p => ({ ...p })) });
      }
      break;
    }
  }

  redoStack.push(action);
  redrawCanvas();
  if (!silent) showToast("已撤销");
}

function handleRedo() {
  if (redoStack.length === 0) {
    showToast("没有可恢复的操作");
    return;
  }

  const action = redoStack.pop()!;

  switch (action.type) {
    case "create": {
      // 恢复创建：重新添加操作
      if (action.operation) {
        drawOperations.push({ ...action.operation, points: action.operation.points.map(p => ({ ...p })) });
        // 如果恢复的是编号，增加编号计数器
        if (action.operation.tool === "step") {
          stepCounter = (action.operation.stepNumber || 0) + 1;
        }
      }
      break;
    }
    case "move":
    case "resize": {
      // 恢复移动/缩放：应用新点
      const op = drawOperations.find(op => op.id === action.operationId);
      if (op && action.newPoints) {
        for (let i = 0; i < op.points.length && i < action.newPoints.length; i++) {
          op.points[i].x = action.newPoints[i].x;
          op.points[i].y = action.newPoints[i].y;
        }
      }
      break;
    }
    case "delete": {
      // 恢复删除：重新删除操作
      const index = drawOperations.findIndex(op => op.id === action.operationId);
      if (index !== -1) {
        const removed = drawOperations.splice(index, 1)[0];
        if (selectedOperationId === removed.id) {
          deselectOperation();
        }
      }
      break;
    }
  }

  undoStack.push(action);
  redrawCanvas();
  showToast("已恢复");
}

function getCurrentOcrCaptureKey(): string | null {
  if (!captureResult) return null;
  return captureResult.imageHash || captureResult.path || null;
}

function resetOcrCache() {
  lastOcrResult = null;
  lastOcrCaptureKey = null;
  lastOcrImagePath = null;
}

function hasCachedOcrForCurrentCapture(): boolean {
  const key = getCurrentOcrCaptureKey();
  return !!(lastOcrResult && key && lastOcrCaptureKey === key);
}

function setElementTransparent(element: HTMLElement | null): void {
  if (!element) return;

  element.style.transition = "none";
  element.style.opacity = "0";
  element.style.background = "transparent";
  element.style.pointerEvents = "none";
}

function restoreOverlayInteractiveSurface(element: HTMLElement | null): void {
  if (!element) return;

  element.style.transition = "";
  element.style.opacity = "";
  element.style.background = "";
  element.style.pointerEvents = "";
}

function restoreOverlayInteractiveSurfaces(): void {
  restoreOverlayInteractiveSurface(document.documentElement);
  restoreOverlayInteractiveSurface(document.body);
  restoreOverlayInteractiveSurface(document.getElementById("overlay-app"));
  restoreOverlayInteractiveSurface(maskElement);
  restoreOverlayInteractiveSurface(selectionElement);
  restoreOverlayInteractiveSurface(sizeLabelElement);
  restoreOverlayInteractiveSurface(bottomToolbar);
  restoreOverlayInteractiveSurface(sideToolbar);
  restoreOverlayInteractiveSurface(drawingCanvas);

  if (screenshotBackground) {
    screenshotBackground.style.opacity = "";
    screenshotBackground.style.pointerEvents = "none";
  }
}

function clearDrawingCanvasForTeardown(): void {
  if (drawingCanvas && drawingCtx) {
    drawingCtx.clearRect(0, 0, drawingCanvas.width, drawingCanvas.height);
  }

  if (drawingCanvas) {
    setElementTransparent(drawingCanvas);
    drawingCanvas.style.display = "none";
  }
}

async function prepareOverlayForOcrTeardown(): Promise<void> {
  if (shouldDeactivateOverlaySessionForOcrTeardown()) {
    overlaySessionActive = false;
  }
  clearAutoOcrTimer();
  pendingOcrAfterCapture = null;
  suspendAutoOcr = true;

  cleanupKeyboardEvents();
  cleanupMouseEvents();
  hideToolbars();
  hideAllPopups();
  hideWindowHighlight();
  finishInlineTextInput(false);

  setElementTransparent(document.documentElement);
  setElementTransparent(document.body);
  setElementTransparent(document.getElementById("overlay-app"));
  setElementTransparent(maskElement);
  setElementTransparent(selectionElement);
  setElementTransparent(sizeLabelElement);
  setElementTransparent(bottomToolbar);
  setElementTransparent(sideToolbar);
  clearDrawingCanvasForTeardown();

  if (screenshotBackground) {
    setElementTransparent(screenshotBackground);
    screenshotBackground.style.display = "none";
    screenshotBackground.src = "";
  }
  fullScreenCapture = null;

  await waitForOverlayVisualTeardown();
}

async function hideOverlayForOcr(): Promise<void> {
  await prepareOverlayForOcrTeardown();

  try {
    await invoke("hide_overlay_windows");
    console.debug("[Overlay] OCR 前已隐藏 overlay，避免透明置顶窗口与 OCR 同时占用桌面渲染");
  } catch (error) {
    console.error("[Overlay] OCR 前隐藏 overlay 失败:", error);
    throw new Error("OCR 前隐藏覆盖窗口失败，已取消识别以避免桌面黑屏");
  }

  if (snapshotMetadata?.path) {
    await cleanupSnapshotFile();
  }
}

async function destroyCurrentOverlayAfterTeardownFailure(error: unknown): Promise<void> {
  if (!shouldDestroyCurrentOverlayAfterTeardownFailure({
    overlayVisuallyTornDown: true,
    backendTeardownFailed: true,
  })) {
    return;
  }

  console.error("[Overlay] overlay 已透明化但后端 teardown/OCR 失败，强制销毁当前 overlay:", error);
  try {
    await getCurrentWindow().destroy();
  } catch (destroyError) {
    console.error("[Overlay] teardown 失败后的当前 overlay 销毁也失败:", destroyError);
  }
}

async function presentOcrResult(
  result: OcrResult,
  request: OcrRequestOptions,
  imagePath?: string
) {
  let copyFailed = false;
  if (request.copyText && result.text.trim()) {
    try {
      await writeText(result.text);
    } catch (error) {
      copyFailed = true;
      console.warn("[Overlay] OCR 文本复制失败，继续打开结果面板:", error);
    }
  }

  // OCR 完成 toast 已移除，保持界面简洁

  if (request.openPanel) {
    try {
      const resolvedImagePath = imagePath ?? captureResult?.path;
      await invoke("open_ocr_panel_no_focus", {
        text: result.text,
        boxes: result.boxes,
        elapse: result.elapse,
        imagePath: resolvedImagePath ?? null,
        image_path: resolvedImagePath ?? null,
      });
      console.debug("[Overlay] OCR 面板已打开（不抢占焦点）");
    } catch (windowError) {
      console.warn("[Overlay] 打开 OCR 结果面板失败（结果已缓存）:", windowError);
    }
  }

  if (copyFailed && !request.openPanel) {
    throw new Error("OCR 文本复制失败");
  }
}

async function presentCachedOcrResult(
  result: OcrResult,
  request: OcrRequestOptions,
  imagePath?: string
): Promise<void> {
  if (shouldRunOcrInBackendAfterOverlayHidden(request)) {
    if (shouldTeardownOverlayBeforeBackendOcr(request)) {
      await prepareOverlayForOcrTeardown();
    }

    try {
      await invoke("present_ocr_result_after_overlay_hidden", {
        text: result.text,
        boxes: result.boxes,
        elapse: result.elapse,
        imagePath: imagePath ?? null,
        openPanel: request.openPanel,
        copyText: request.copyText,
      });
    } catch (error) {
      await destroyCurrentOverlayAfterTeardownFailure(error);
      throw error;
    }
    return;
  }

  if (shouldHideOverlayBeforeCachedOcrResult(request)) {
    await hideOverlayForOcr();
  }

  await presentOcrResult(result, request, imagePath);
}

function handleOcr() {
  if (!selectionState.hasSelection) {
    showToast("请先选择截图区域");
    return;
  }

  suspendAutoOcr = false;
  clearAutoOcrTimer();

  if (ocrInProgress) {
    pendingOcrAfterCurrent = OCR_REQUEST_MANUAL;
    return;
  }

  if (captureInProgress) {
    pendingOcrAfterCapture = OCR_REQUEST_MANUAL;
    return;
  }

  if (!captureResult) {
    pendingOcrAfterCapture = OCR_REQUEST_MANUAL;
    const rect = getSelectionRect();
    captureSelection(rect).catch((error) => {
      console.error("[Overlay] 触发 OCR 前捕获失败:", error);
    });
    return;
  }

  if (hasCachedOcrForCurrentCapture()) {
    const cached = lastOcrResult;
    if (cached && cached.text && cached.text.trim()) {
      presentCachedOcrResult(cached, OCR_REQUEST_MANUAL, lastOcrImagePath ?? undefined).catch((error) => {
        console.warn("[Overlay] 复用 OCR 缓存失败:", error);
      });
      return;
    }
  }

  // 异步执行 OCR
  doOcr(OCR_REQUEST_MANUAL);
}

async function doOcr(request: OcrRequestOptions) {
  if (request.reason === "auto" && (isCopyInProgress || suspendAutoOcr)) {
    console.debug("[Overlay] 自动 OCR 被跳过（复制优先）");
    return;
  }

  if (shouldDeferOcrUntilCaptureComplete({
    captureInProgress,
    pendingOcrAfterCapture: pendingOcrAfterCapture !== null,
    hasCaptureResult: captureResult !== null,
  })) {
    pendingOcrAfterCapture =
      request.reason === "manual" ? request : (pendingOcrAfterCapture ?? request);
    console.debug("[Overlay] 截图裁剪尚未完成，OCR 已延后到 capture_region 结束后执行");
    return;
  }

  if (!captureResult) {
    showToast("请先选择截图区域");
    return;
  }

  const ocrCommand = overlayOcrCommandName(request);
  let overlayHiddenForOcr = false;

  try {
    if (ocrInProgress) {
      pendingOcrAfterCurrent = request;
      return;
    }

    ocrInProgress = true;
    setOcrButtonDisabled(true);

    // 如果有绘图操作，需要先保存合成后的图像
    let imagePath = captureResult.path;

    if (drawOperations.length > 0) {
      // 【性能优化】使用 writeFile 二进制 IPC，避免 Array.from() 的 JSON 序列化开销
      const pngData = await compositeImage();
      imagePath = replaceTempImageExtension(captureResult.path, '_composite_ocr.png');
      await writeFile(imagePath, pngData);
    }

    overlayHiddenForOcr = true;
    await prepareOverlayForOcrTeardown();
    console.debug("[Overlay] 调用安全 OCR, 图像路径:", imagePath);

    const result = await invoke<OcrResult>(ocrCommand, {
      imagePath,
      engine: null,
      openPanel: request.openPanel,
      copyText: request.copyText,
    });

    console.debug("[Overlay] OCR 结果:", result);

    lastOcrResult = result;
    lastOcrCaptureKey = getCurrentOcrCaptureKey();
    lastOcrImagePath = imagePath;
    return;

  } catch (error) {
    console.error("[Overlay] OCR 失败:", error);
    if (overlayHiddenForOcr) {
      await destroyCurrentOverlayAfterTeardownFailure(error);
      return;
    }

    const overlayStillVisible = overlayHiddenForOcr
      ? await getCurrentWindow().isVisible().catch(() => false)
      : true;

    if (overlayStillVisible) {
      showToast(formatOcrUserError(error));
      setOcrButtonDisabled(false);
    }
  } finally {
    ocrInProgress = false;
    if (!overlayHiddenForOcr) {
      setOcrButtonDisabled(false);
    }

    if (overlayHiddenForOcr) {
      pendingOcrAfterCurrent = null;
      return;
    }

    if (pendingOcrAfterCurrent) {
      const pendingRequest = pendingOcrAfterCurrent;
      pendingOcrAfterCurrent = null;
      if (hasCachedOcrForCurrentCapture() && lastOcrResult) {
        void presentOcrResult(lastOcrResult, pendingRequest, lastOcrImagePath ?? undefined);
      } else if (captureResult) {
        void doOcr(pendingRequest);
      }
    }
  }
}

// ============================================
// 录屏模式状态
// ============================================

let isRecordingMode = false;
let recordingTimerInterval: number | null = null;
let recordingElapsedSeconds = 0;
let recordingControlBar: HTMLDivElement | null = null;
let recordingTimeElement: HTMLSpanElement | null = null;
let recordingPaused = false;

/**
 * 处理录屏按钮点击
 *
 * 将 overlay 从截图模式平滑过渡到录屏模式：
 * - 遮罩变透明，选区边框变红色闪烁
 * - 工具栏替换为录制控件（时间+暂停+停止）
 * - overlay 变为穿透鼠标模式（可操作桌面）
 */
async function handleStartRecording() {
  if (!selectionState.hasSelection) {
    showToast("请先选择录制区域");
    return;
  }


  try {
    const rect = getSelectionRect();
    const dpr = monitorInfo?.scaleFactor || 1;

    // 转换为物理像素坐标
    const physicalRegion = {
      x: Math.round(rect.x * dpr),
      y: Math.round(rect.y * dpr),
      width: Math.round(rect.width * dpr),
      height: Math.round(rect.height * dpr),
    };

    // 1. 隐藏截图模式 UI
    hideToolbars();
    hideAllPopups();
    if (drawingCanvas) drawingCanvas.style.display = "none";
    if (sizeLabelElement) sizeLabelElement.style.display = "none";

    // 隐藏截图背景（让真实桌面显示）
    const bg = document.getElementById("screenshot-background");
    if (bg) bg.style.display = "none";

    // 2. 遮罩变透明
    if (maskElement) {
      maskElement.classList.add("recording-mode");
    }

    // 3. 选区边框变红色录制样式
    if (selectionElement) {
      selectionElement.classList.add("recording-border");
      // 隐藏缩放手柄
      const handles = selectionElement.querySelectorAll(".selection-handle");
      handles.forEach(h => (h as HTMLElement).style.display = "none");
    }

    // 4. 设置 overlay 为穿透+排除捕获模式
    await invoke("set_overlay_recording_mode", { enabled: true });

    // 5. 打开独立的录屏区域边框窗口（不设排除捕获，保证用户始终可见）
    const monitorX = monitorInfo?.position?.x ?? 0;
    const monitorY = monitorInfo?.position?.y ?? 0;
    await invoke("open_recording_border", {
      x: rect.x + monitorX,
      y: rect.y + monitorY,
      width: rect.width,
      height: rect.height,
    });

    // 6. 打开独立的录制控制窗口（不受 overlay 穿透影响）
    await invoke("open_recording_control");

    // 7. 开始录制
    await invoke("start_recording", {
      params: {
        region: physicalRegion,
        fps: 30,
        quality: "medium",
      },
    });

    // 7. 启动计时器
    isRecordingMode = true;
    recordingPaused = false;
    recordingElapsedSeconds = 0;
    startRecordingTimer();

    console.debug("[Overlay] 录屏模式已启动");
  } catch (error) {
    console.error("[Overlay] 启动录屏失败:", error);
    showToast("录屏失败: " + error);
    // 恢复截图模式
    exitRecordingMode();
  }
}

/**
 * 启动录制计时器
 */
function startRecordingTimer() {
  if (recordingTimerInterval) clearInterval(recordingTimerInterval);
  recordingTimerInterval = window.setInterval(() => {
    if (!recordingPaused) {
      recordingElapsedSeconds++;
      if (recordingTimeElement) {
        const mins = Math.floor(recordingElapsedSeconds / 60);
        const secs = recordingElapsedSeconds % 60;
        recordingTimeElement.textContent =
          `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
      }
    }
  }, 1000);
}

/**
 * 停止录制
 */
async function stopRecording() {
  try {
    const result = await invoke<{
      outputPath: string;
      duration: number;
      frameCount: number;
      fileSize: number;
      droppedFrames: number;
    }>("stop_recording");

    console.debug("[Overlay] 录屏完成:", result);

    // 退出录屏模式（必须 await，避免与 closeWindow 竞争）
    await exitRecordingMode();

    // 检查录屏是否成功（0 字节表示编码器失败）
    if (result.fileSize === 0 || result.frameCount === 0) {
      console.error("[Overlay] 录屏失败：输出文件为 0 字节，编码器可能初始化失败");
      try {
        const { message } = await import("@tauri-apps/plugin-dialog");
        await message("视频编码器初始化失败，录屏文件无效。\n\n可能的原因：\n• 显卡驱动未安装或版本过低\n• FFmpeg 不支持当前硬件编码器\n\n已自动切换为 CPU 软件编码，请重新录制。", {
          title: "录屏失败",
          kind: "error",
        });
      } catch {
        // dialog 插件不可用时静默失败
      }
      await closeWindow();
      return;
    }

    // 丢帧率超过 30% 时在预览中提示用户
    const totalFrames = result.frameCount + result.droppedFrames;
    const dropRate = totalFrames > 0 ? result.droppedFrames / totalFrames : 0;
    if (dropRate > 0.3) {
      console.warn(`[Overlay] 录屏丢帧率较高: ${(dropRate * 100).toFixed(1)}% (${result.droppedFrames}/${totalFrames})`);
    }

    // 先打开预览（当前 overlay 窗口 IPC 仍存活）
    await invoke("open_recording_preview", {
      outputPath: result.outputPath,
      duration: result.duration,
      fileSize: result.fileSize,
    });

    // 最后关闭 overlay
    await closeWindow();
  } catch (e) {
    console.error("[Overlay] 停止录制失败:", e);
    await exitRecordingMode();
    await closeWindow();
  }
}

/**
 * 退出录屏模式，恢复 overlay 正常状态
 */
async function exitRecordingMode() {
  isRecordingMode = false;

  // 停止计时器
  if (recordingTimerInterval) {
    clearInterval(recordingTimerInterval);
    recordingTimerInterval = null;
  }

  // 移除录制控制栏（遗留的内嵌版本）
  if (recordingControlBar) {
    recordingControlBar.remove();
    recordingControlBar = null;
  }
  recordingTimeElement = null;

  // 关闭独立的录制控制窗口
  try {
    await invoke("close_recording_control");
  } catch (e) {
    console.warn("[Overlay] 关闭录制控制窗口失败:", e);
  }

  // 关闭录屏区域边框窗口
  try {
    await invoke("close_recording_border");
  } catch (e) {
    console.warn("[Overlay] 关闭录屏边框窗口失败:", e);
  }

  // 恢复遮罩
  if (maskElement) {
    maskElement.classList.remove("recording-mode");
  }

  // 恢复选区样式
  if (selectionElement) {
    selectionElement.classList.remove("recording-border");
  }

  // 恢复 overlay 正常模式（取消穿透+恢复捕获）
  try {
    await invoke("set_overlay_recording_mode", { enabled: false });
  } catch (e) {
    console.warn("[Overlay] 恢复正常模式失败:", e);
  }
}

async function handlePin() {
  if (!captureResult) {
    showToast("请先选择截图区域");
    return;
  }

  try {
    // 获取选区位置（逻辑像素）
    const rect = getSelectionRect();
    
    // 如果有绘图操作，需要先保存合成后的图像
    let imagePath = captureResult.path;
    
    if (drawOperations.length > 0) {
      // 【性能优化】使用 writeFile 二进制 IPC，避免 Array.from() 的 JSON 序列化开销
      const compositeData = await compositeImage();
      imagePath = replaceTempImageExtension(captureResult.path, '_composite_pin.png');
      await writeFile(imagePath, compositeData);
    }

    // 计算钉图窗口位置
    // 注意：Tauri 窗口位置使用逻辑像素，需要加上显示器偏移
    const monitorOffsetX = monitorInfo?.position.x || 0;
    const monitorOffsetY = monitorInfo?.position.y || 0;
    const dpr = monitorInfo?.scaleFactor || 1;

    // 钉图窗口位置（逻辑像素，加上显示器偏移）
    // 窗口尺寸使用物理像素除以 DPR 转换为逻辑像素
    const pinRect = {
      x: Math.round(rect.x + monitorOffsetX),
      y: Math.round(rect.y + monitorOffsetY),
      width: Math.round(captureResult.width / dpr),
      height: Math.round(captureResult.height / dpr),
    };

    console.debug("[Overlay] 创建钉图窗口:", { imagePath, pinRect, dpr });

    // 【性能优化】立即反馈，不等待窗口创建完成
    showToast("正在钉住截图...");

    // 立即隐藏选区 UI，避免 overlay 仍显示选区框和尺寸标签
    setMaskSelectionActive(false); // 恢复遮罩
    if (selectionElement) selectionElement.style.display = "none";
    if (sizeLabelElement) sizeLabelElement.style.display = "none";
    if (drawingCanvas) drawingCanvas.style.display = "none";
    hideToolbars();

    // 【性能优化】异步创建钉图窗口，不阻塞 overlay 关闭
    invoke<string>("create_pin_window", {
      imagePath: imagePath,
      rect: pinRect,
    }).then(windowLabel => {
      console.debug("[Overlay] 钉图窗口创建成功:", windowLabel);
    }).catch(error => {
      console.error("[Overlay] 创建钉图窗口失败:", error);
    });

    // 【性能优化】先关闭覆盖层，不等待窗口创建完成
    // closeWindow 内部会处理快照清理（cleanupSnapshotFile）
    closeWindow();
  } catch (error) {
    console.error("[Overlay] 钉图准备失败:", error);
    showToast("钉图失败: " + error);
  }
}

/**
 * 静默关闭 OCR 结果面板
 * 
 * 在选区重置或选区变化时调用，关闭已打开的 OCR 面板。
 * 不抛出异常，失败时仅输出警告日志。
 */
function closeOcrPanelSilently() {
  invoke("close_ocr_result_window").catch((e) => {
    console.warn("[Overlay] 关闭 OCR 面板失败（可能未打开）:", e);
  });
}

function resetSelectionForReselect() {
  selectionState.isSelecting = false;
  selectionState.hasSelection = false;
  captureResult = null;
  queuedCaptureRect = null;
  queuedCaptureTriggerOcr = false;
  pendingOcrAfterCapture = null;
  selectionEditMode = "idle";
  selectionResizeHandle = "";
  selectionOriginalRect = null;
  selectionEditPreviousCapture = null;
  pendingOcrAfterCurrent = null;
  resetOcrCache();
  clearAutoOcrTimer();
  suspendAutoOcr = false;

  resetDrawingState();

  if (selectionElement) selectionElement.style.display = "none";
  if (sizeLabelElement) sizeLabelElement.style.display = "none";
  if (drawingCanvas) drawingCanvas.style.display = "none";

  // 选区消失，恢复遮罩层暗色
  setMaskSelectionActive(false);

  hideToolbars();
  hideAllPopups();
  hideWindowHighlight();

  // 关闭 OCR 结果面板：选区已重置，旧的 OCR 结果不再有效
  closeOcrPanelSilently();
}

// handleReselect 已移除 — 点击选区外即可自动重选

async function cancelSelection() {
  selectionState.isSelecting = false;
  selectionState.hasSelection = false;
  captureResult = null;
  queuedCaptureRect = null;
  pendingOcrAfterCapture = null;
  selectionEditMode = "idle";
  selectionResizeHandle = "";
  selectionOriginalRect = null;
  selectionEditPreviousCapture = null;
  pendingOcrAfterCurrent = null;
  resetOcrCache();
  clearAutoOcrTimer();
  suspendAutoOcr = false;

  resetDrawingState();

  if (selectionElement) selectionElement.style.display = "none";
  if (sizeLabelElement) sizeLabelElement.style.display = "none";
  if (drawingCanvas) drawingCanvas.style.display = "none";

  // 选区消失，恢复遮罩层暗色
  setMaskSelectionActive(false);

  hideToolbars();
  finishInlineTextInput(false);
  
  await closeWindow();
}

async function closeWindow() {
  try {
    overlaySessionActive = false;
    clearAutoOcrTimer();
    suspendAutoOcr = false;

    // 清理全局事件监听器（隐藏期间不需要响应键盘/鼠标事件）
    cleanupKeyboardEvents();
    cleanupMouseEvents();

    await prepareOverlayForOcrTeardown();

    // 【Task 6.1】兜底清理：确保快照文件被清理（Requirements 3.4）
    // 如果其他路径（save/copy/cancel）已经清理过，这里会快速返回
    if (snapshotMetadata?.path) {
      await cleanupSnapshotFile();
    }
    
    // 隐藏所有 overlay 窗口（多显示器场景）
    await invoke("hide_overlay_windows");
  } catch (e) {
    console.error("[Overlay] 隐藏窗口失败:", e);
    // 如果后端清理失败，至少强制销毁当前窗口，避免透明壳残留
    try {
      const currentWindow = getCurrentWindow();
      await currentWindow.destroy();
    } catch (e2) {
      console.error("[Overlay] 销毁当前窗口也失败:", e2);
    }
  }
}

// ============================================
// 启动
// ============================================

initOverlay().catch((e) => {
  console.error("[Overlay] 初始化失败:", e);
});
