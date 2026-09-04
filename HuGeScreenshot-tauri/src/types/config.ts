/**
 * 应用配置类型定义
 * 对应 Rust: src-tauri/src/database/settings.rs
 */

import type { TranslateProvider } from './sidecar'

/** 通用设置 */
export interface GeneralConfig {
  /** 界面语言 */
  language: 'zh-CN' | 'en-US'
  /** 主题 */
  theme: 'light' | 'dark' | 'system'
  /** 开机自启动 */
  autoStart: boolean
  /** 最小化到托盘 */
  minimizeToTray: boolean
  /** 关闭时最小化而非退出 */
  closeToTray: boolean
}

/** 热键设置 */
export interface HotkeyConfig {
  /** 截图热键 */
  screenshot: string
  /** 工作台热键 */
  workbench: string
  /** OCR 热键 */
  ocr: string
  /** 录屏热键 */
  recording: string
  /** 贴图热键 */
  pin: string
  /** 鼠标高亮热键 */
  mouseHighlight: string
}

/** 截图设置 */
export interface ScreenshotConfig {
  /** 保存位置 */
  saveLocation: string
  /** 包含鼠标光标 */
  includeMouseCursor: boolean
  /** 截图后自动复制 */
  autoCopy: boolean
  /** 截图后自动保存 */
  autoSave: boolean
}

/** 标注设置 */
export interface AnnotationConfig {
  /** 默认描边颜色 */
  defaultStrokeColor: string
  /** 默认描边宽度 */
  defaultStrokeWidth: number
  /** 默认字体大小 */
  defaultFontSize: number
  /** 默认字体 */
  defaultFontFamily: string
  /** 默认马赛克大小 */
  defaultMosaicSize: number
}

/** OCR 引擎 */
export type OcrEngine = 'local' | 'baiduAccurate'

/** OCR 设置 */
export interface OcrConfig {
  /** 默认 OCR 引擎 */
  engine: OcrEngine
  /** 默认语言 */
  defaultLanguage: string
  /** 自动翻译 */
  autoTranslate: boolean
  /** 翻译提供商 */
  translateProvider: TranslateProvider
  /** 翻译目标语言 */
  translateTargetLang: string
  /** 百度 OCR API Key */
  baiduApiKey: string
  /** 百度 OCR Secret Key */
  baiduSecretKey: string
  /** 百度 OCR 是否检测文字方向 */
  baiduDetectDirection: boolean
  /** 百度 OCR 是否返回置信度 */
  baiduProbability: boolean
}

/** 录屏设置 */
export interface RecordingConfig {
  /** 默认帧率 */
  defaultFps: number
  /** 录制系统音频 */
  systemAudio: boolean
  /** 录制麦克风 */
  micAudio: boolean
  /** 输出目录 */
  outputDir: string
}

/** Pin Image (贴图) Settings */
export interface PinImageConfig {
  /** Default opacity (0.1-1.0) */
  defaultOpacity: number
  /** Enable mouse-through by default */
  mouseThrough: boolean
  /** Remember window position */
  rememberPosition: boolean
}

/** 鼠标高亮主题类型 */
export type MouseHighlightTheme = 'classic_yellow' | 'business_blue' | 'vibrant_red' | 'fresh_green'

/** 鼠标高亮主题定义 */
export interface MouseHighlightThemeColors {
  name: string
  circleColor: string
  leftClickColor: string
  rightClickColor: string
}

/** 预定义的鼠标高亮主题 */
export const MOUSE_HIGHLIGHT_THEMES: Record<MouseHighlightTheme, MouseHighlightThemeColors> = {
  classic_yellow: {
    name: '经典黄色',
    circleColor: '#FFD700',
    leftClickColor: '#FFD700',
    rightClickColor: '#FF6B6B',
  },
  business_blue: {
    name: '商务蓝色',
    circleColor: '#4A90E2',
    leftClickColor: '#4A90E2',
    rightClickColor: '#E24A4A',
  },
  vibrant_red: {
    name: '活力红色',
    circleColor: '#FF4757',
    leftClickColor: '#FF4757',
    rightClickColor: '#FFA502',
  },
  fresh_green: {
    name: '清新绿色',
    circleColor: '#2ECC71',
    leftClickColor: '#2ECC71',
    rightClickColor: '#9B59B6',
  },
}

/** 鼠标高亮参数范围常量 */
export const MOUSE_HIGHLIGHT_LIMITS = {
  circleRadius: { min: 10, max: 100, default: 40 },
  circleThickness: { min: 1, max: 10, default: 3 },
  spotlightRadius: { min: 50, max: 500, default: 150 },
  spotlightDarkness: { min: 0, max: 100, default: 60 },
  cursorScale: { min: 1.0, max: 5.0, default: 2.0 },
  rippleDuration: { min: 100, max: 2000, default: 500 },
} as const

/** Mouse Highlight Settings - 鼠标高亮设置 */
export interface MouseHighlightConfig {
  /** 功能总开关 */
  enabled: boolean
  /** 启动时恢复上次状态 */
  restoreOnStartup: boolean

  /** 效果开关 */
  circleEnabled: boolean       // 光圈效果
  spotlightEnabled: boolean    // 聚光灯效果
  cursorMagnifyEnabled: boolean // 指针放大效果
  clickEffectEnabled: boolean  // 点击涟漪效果

  /** 配色主题 */
  theme: MouseHighlightTheme

  /** 光圈参数 */
  circleRadius: number         // 半径 (10-100 px)
  circleThickness: number      // 线条粗细 (1-10 px)

  /** 聚光灯参数 */
  spotlightRadius: number      // 半径 (50-500 px)
  spotlightDarkness: number    // 暗部透明度 (0-100 %)

  /** 指针放大参数 */
  cursorScale: number          // 放大倍数 (1.0-5.0 x)

  /** 涟漪参数 */
  rippleDuration: number       // 动画时长 (100-2000 ms)
}

/** Web to Markdown Settings */
export interface WebToMarkdownConfig {
  /** Include images in conversion */
  includeImages: boolean
  /** Include links in conversion */
  includeLinks: boolean
  /** Timeout in seconds */
  timeout: number
  /** Default save directory */
  saveDir: string
}

/** 文件转 Markdown 转换引擎类型 */
export type FileToMarkdownEngine = 'local' | 'mineru'

/** File to Markdown Settings */
export interface FileToMarkdownConfig {
  /** 转换引擎：'local'（本地 MarkItDown）| 'mineru'（MinerU API） */
  engine: FileToMarkdownEngine
  /** MinerU API token（仅 engine='mineru' 时需要） */
  apiToken: string
  /** Model version: 'pipeline' | 'vlm'（仅 engine='mineru' 时需要） */
  modelVersion: 'pipeline' | 'vlm'
  /** Default save directory */
  saveDir: string
}

/** Notification Settings */
export interface NotificationConfig {
  /** Show startup notification */
  startup: boolean
  /** Show screenshot save notification */
  screenshotSave: boolean
  /** Show pin image notification */
  pinImage: boolean
  /** Show recording complete notification */
  recordingComplete: boolean
  /** Show software update notification */
  softwareUpdate: boolean
}

/** Update Settings */
export interface UpdateConfig {
  /** Auto check for updates */
  autoCheck: boolean
  /** Last check timestamp */
  lastCheckTime: string
  /** Skip version */
  skipVersion: string
}

/** Advanced Settings */
export interface AdvancedConfig {
  /** Proxy enabled */
  proxyEnabled: boolean
  /** Proxy type: 'http' | 'socks5' */
  proxyType: 'http' | 'socks5'
  /** Proxy host */
  proxyHost: string
  /** Proxy port */
  proxyPort: number
  /** Enable debug logging */
  debugLogging: boolean
  /** Debug log path */
  debugLogPath: string
  /** Portable mode */
  portableMode: boolean
}

/** 完整应用配置 */
export interface AppConfig {
  general: GeneralConfig
  hotkeys: HotkeyConfig
  screenshot: ScreenshotConfig
  annotation: AnnotationConfig
  ocr: OcrConfig
  recording: RecordingConfig
  pinImage: PinImageConfig
  mouseHighlight: MouseHighlightConfig
  webToMarkdown: WebToMarkdownConfig
  fileToMarkdown: FileToMarkdownConfig
  notification: NotificationConfig
  update: UpdateConfig
  advanced: AdvancedConfig
}

/** 默认配置 */
export const DEFAULT_CONFIG: AppConfig = {
  general: {
    language: 'zh-CN',
    theme: 'system',
    autoStart: false,
    minimizeToTray: true,
    closeToTray: true,
  },
  hotkeys: {
    screenshot: 'Alt+X',
    workbench: 'Alt+P',
    ocr: 'Ctrl+Shift+O',
    recording: 'Ctrl+Shift+R',
    pin: 'Ctrl+Shift+P',
    mouseHighlight: 'Alt+M',
  },
  screenshot: {
    saveLocation: '',
    includeMouseCursor: false,
    autoCopy: true,
    autoSave: false,
  },
  annotation: {
    defaultStrokeColor: '#FF0000',
    defaultStrokeWidth: 2,
    defaultFontSize: 16,
    defaultFontFamily: 'Microsoft YaHei',
    defaultMosaicSize: 10,
  },
  ocr: {
    engine: 'local',
    defaultLanguage: 'auto',
    autoTranslate: false,
    translateProvider: 'google',
    translateTargetLang: 'zh',
    baiduApiKey: '',
    baiduSecretKey: '',
    baiduDetectDirection: true,
    baiduProbability: true,
  },
  recording: {
    defaultFps: 30,
    systemAudio: true,
    micAudio: false,
    outputDir: '',
  },
  pinImage: {
    defaultOpacity: 1.0,
    mouseThrough: false,
    rememberPosition: true,
  },
  mouseHighlight: {
    enabled: false,
    restoreOnStartup: true,
    circleEnabled: true,
    spotlightEnabled: false,
    cursorMagnifyEnabled: false,
    clickEffectEnabled: true,
    theme: 'classic_yellow',
    circleRadius: 40,
    circleThickness: 3,
    spotlightRadius: 150,
    spotlightDarkness: 60,
    cursorScale: 2.0,
    rippleDuration: 500,
  },
  webToMarkdown: {
    includeImages: true,
    includeLinks: true,
    timeout: 30,
    saveDir: '',
  },
  fileToMarkdown: {
    engine: 'local',
    apiToken: '',
    modelVersion: 'vlm',
    saveDir: '',
  },
  notification: {
    startup: true,
    screenshotSave: true,
    pinImage: true,
    recordingComplete: true,
    softwareUpdate: true,
  },
  update: {
    autoCheck: true,
    lastCheckTime: '',
    skipVersion: '',
  },
  advanced: {
    proxyEnabled: false,
    proxyType: 'http',
    proxyHost: '',
    proxyPort: 8080,
    debugLogging: false,
    debugLogPath: '',
    portableMode: false,
  },
}
