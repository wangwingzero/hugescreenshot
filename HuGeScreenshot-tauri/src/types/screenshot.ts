/**
 * 截图相关类型定义
 * 对应 Rust: src-tauri/src/screenshot/
 */

/** 矩形区域 */
export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

/** 截图捕获结果 */
export interface CaptureResult {
  /** asset:// 可访问的临时文件路径 */
  path: string
  /** 物理像素宽度 */
  width: number
  /** 物理像素高度 */
  height: number
  /** 设备像素比 (DPR) */
  dpr: number
  /** 显示器 ID */
  monitorId: number
  /** 显示器 X 坐标（虚拟屏幕坐标系，可能为负） */
  x: number
  /** 显示器 Y 坐标（虚拟屏幕坐标系，可能为负） */
  y: number
  /** 图片 MD5 哈希（用于去重） */
  imageHash?: string
  /** 文件大小（字节） */
  fileSize?: number
  /** 捕获耗时（毫秒） */
  captureTimeMs?: number
  /** 使用的捕获引擎（"dxgi" 或 "screenshots-rs"） */
  captureEngine?: string
}

/** 显示器信息 */
export interface MonitorInfo {
  /** 显示器 ID */
  id: number
  /** 显示器名称 */
  name: string
  /** 位置 (逻辑像素) */
  position: { x: number; y: number }
  /** 尺寸 (逻辑像素) */
  size: { width: number; height: number }
  /** 缩放因子 (DPR) */
  scaleFactor: number
  /** 是否主显示器 */
  isPrimary: boolean
}

/** 窗口信息 */
export interface WindowInfo {
  /** 窗口句柄 */
  hwnd: number
  /** 窗口标题 */
  title: string
  /** 窗口类名 */
  className: string
  /** 逻辑像素坐标 */
  rect: Rect
  /** 物理像素坐标 */
  physicalRect: Rect
}

/** 用户选择的区域 */
export interface SelectionRegion {
  /** 逻辑像素 X */
  x: number
  /** 逻辑像素 Y */
  y: number
  /** 逻辑像素宽度 */
  width: number
  /** 逻辑像素高度 */
  height: number
  /** 所在显示器 ID */
  monitorId: number
  /** 物理像素矩形 (用于裁剪) */
  physicalRect: Rect
}

/** 截图模式 */
export type CaptureMode = 'region' | 'window' | 'fullscreen' | 'scrolling'

/** 截图状态 */
export type CaptureState = 'idle' | 'capturing' | 'selecting' | 'annotating' | 'exporting'
