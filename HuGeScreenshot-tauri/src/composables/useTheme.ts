/**
 * 主题管理 Composable
 *
 * 提供主题切换功能：
 * - 深色/浅色/跟随系统
 * - 自动检测系统主题
 * - 持久化主题设置到 localStorage
 * - 防止 FOUC (Flash of Unstyled Content)
 *
 * @validates Requirements 5.4
 */

import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useSettingsStore } from '@/stores/settings'

export type Theme = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

/** localStorage 存储键名 */
const THEME_STORAGE_KEY = 'huge-theme'

/** 系统主题媒体查询 */
const darkModeQuery = typeof window !== 'undefined' 
  ? window.matchMedia('(prefers-color-scheme: dark)')
  : null

/** 当前系统主题（全局共享） */
const systemTheme = ref<ResolvedTheme>(
  darkModeQuery?.matches ? 'dark' : 'light'
)

/** 是否已初始化系统主题监听器 */
let isSystemThemeListenerInitialized = false

/** 系统主题监听器引用计数（支持多个 useTheme 实例共享监听器） */
let listenerRefCount = 0

/** 监听系统主题变化 */
function handleSystemThemeChange(e: MediaQueryListEvent): void {
  systemTheme.value = e.matches ? 'dark' : 'light'
}

/**
 * 初始化系统主题监听器（引用计数，支持多消费者）
 */
function initSystemThemeListener(): void {
  if (!darkModeQuery) return
  
  if (!isSystemThemeListenerInitialized) {
    darkModeQuery.addEventListener('change', handleSystemThemeChange)
    isSystemThemeListenerInitialized = true
  }
  listenerRefCount++
}

/**
 * 释放系统主题监听器引用（最后一个消费者释放时移除监听器）
 */
function releaseSystemThemeListener(): void {
  if (!darkModeQuery) return
  
  listenerRefCount = Math.max(0, listenerRefCount - 1)
  if (listenerRefCount === 0 && isSystemThemeListenerInitialized) {
    darkModeQuery.removeEventListener('change', handleSystemThemeChange)
    isSystemThemeListenerInitialized = false
  }
}

/**
 * 应用主题到 DOM
 * @param theme 要应用的主题
 */
function applyThemeToDOM(theme: ResolvedTheme): void {
  if (typeof document === 'undefined') return
  
  const html = document.documentElement

  // 更新 data-theme 属性
  html.setAttribute('data-theme', theme)

  // 更新 class
  html.classList.remove('light', 'dark')
  html.classList.add(theme)

  // 更新 color-scheme（让浏览器原生控件也跟随主题）
  html.style.colorScheme = theme
}

/**
 * 保存主题偏好到 localStorage
 * @param theme 用户选择的主题
 */
function saveThemePreference(theme: Theme): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(THEME_STORAGE_KEY, theme)
}

/**
 * 从 localStorage 读取主题偏好
 */
function loadThemePreference(): Theme | null {
  if (typeof localStorage === 'undefined') return null
  const stored = localStorage.getItem(THEME_STORAGE_KEY)
  if (stored === 'light' || stored === 'dark' || stored === 'system') {
    return stored
  }
  return null
}

/**
 * 主题管理 Composable
 * 
 * 使用示例：
 * ```vue
 * <script setup>
 * import { useTheme } from '@/composables/useTheme'
 * 
 * const { isDark, setTheme, toggleTheme } = useTheme()
 * </script>
 * 
 * <template>
 *   <button @click="toggleTheme">
 *     {{ isDark ? '🌙' : '☀️' }}
 *   </button>
 * </template>
 * ```
 */
export function useTheme() {
  const settingsStore = useSettingsStore()

  /** 用户选择的主题 */
  const userTheme = computed<Theme>(() => settingsStore.general.theme)

  /** 实际应用的主题 */
  const resolvedTheme = computed<ResolvedTheme>(() => {
    if (userTheme.value === 'system') {
      return systemTheme.value
    }
    return userTheme.value
  })

  /** 是否为深色主题 */
  const isDark = computed(() => resolvedTheme.value === 'dark')

  /** 是否为浅色主题 */
  const isLight = computed(() => resolvedTheme.value === 'light')

  /**
   * 设置主题
   * @param theme 主题类型：'light' | 'dark' | 'system'
   */
  function setTheme(theme: Theme): void {
    settingsStore.updateGeneral({ theme })
    saveThemePreference(theme)
  }

  /**
   * 切换深色/浅色主题
   * 如果当前是跟随系统，则切换到当前系统主题的相反值
   */
  function toggleTheme(): void {
    if (userTheme.value === 'system') {
      // 如果当前是跟随系统，切换到当前系统主题的相反值
      setTheme(systemTheme.value === 'dark' ? 'light' : 'dark')
    } else {
      setTheme(userTheme.value === 'dark' ? 'light' : 'dark')
    }
  }

  /**
   * 手动应用当前主题到 DOM
   */
  function applyTheme(): void {
    applyThemeToDOM(resolvedTheme.value)
  }

  // 监听主题变化，自动应用
  watch(resolvedTheme, (newTheme) => {
    applyThemeToDOM(newTheme)
  }, { immediate: true })

  // 组件挂载时初始化
  onMounted(() => {
    initSystemThemeListener()
    applyTheme()
  })

  // 组件卸载时释放监听器引用
  onUnmounted(() => {
    releaseSystemThemeListener()
  })

  return {
    /** 用户选择的主题（可能是 system） */
    userTheme,
    /** 实际应用的主题（light 或 dark） */
    resolvedTheme,
    /** 系统当前主题 */
    systemTheme,
    /** 是否为深色主题 */
    isDark,
    /** 是否为浅色主题 */
    isLight,
    /** 设置主题 */
    setTheme,
    /** 切换主题 */
    toggleTheme,
    /** 手动应用主题 */
    applyTheme,
  }
}

/**
 * 初始化主题（在应用启动时调用）
 * 
 * 此函数应在 main.ts 中调用，确保：
 * 1. 从 localStorage 恢复用户偏好
 * 2. 初始化系统主题监听器
 * 3. 应用正确的主题到 DOM
 */
export function initializeTheme(): void {
  // 初始化系统主题监听器
  initSystemThemeListener()
  
  // 从 localStorage 读取偏好
  const storedTheme = loadThemePreference()
  
  // 计算实际主题
  let resolvedTheme: ResolvedTheme = 'light'
  if (storedTheme === 'dark') {
    resolvedTheme = 'dark'
  } else if (storedTheme === 'light') {
    resolvedTheme = 'light'
  } else {
    // system 或未设置：跟随系统
    resolvedTheme = systemTheme.value
  }
  
  // 应用主题
  applyThemeToDOM(resolvedTheme)
}

/**
 * CSS 变量定义
 *
 * 在全局样式中定义以下 CSS 变量：
 *
 * :root, [data-theme="light"] {
 *   --color-bg-primary: #ffffff;
 *   --color-bg-secondary: #f5f5f5;
 *   --color-bg-tertiary: #e8e8e8;
 *   --color-text-primary: #1a1a1a;
 *   --color-text-secondary: #666666;
 *   --color-text-tertiary: #999999;
 *   --color-border: #e0e0e0;
 *   --color-accent: #4285f4;
 *   --color-accent-hover: #3367d6;
 *   --color-success: #4caf50;
 *   --color-warning: #ff9800;
 *   --color-error: #f44336;
 *   --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.1);
 *   --shadow-md: 0 2px 8px rgba(0, 0, 0, 0.12);
 *   --shadow-lg: 0 4px 16px rgba(0, 0, 0, 0.15);
 * }
 *
 * [data-theme="dark"] {
 *   --color-bg-primary: #1a1a1a;
 *   --color-bg-secondary: #252525;
 *   --color-bg-tertiary: #333333;
 *   --color-text-primary: #f5f5f5;
 *   --color-text-secondary: #b0b0b0;
 *   --color-text-tertiary: #808080;
 *   --color-border: #404040;
 *   --color-accent: #4285f4;
 *   --color-accent-hover: #5a9cf4;
 *   --color-success: #66bb6a;
 *   --color-warning: #ffb74d;
 *   --color-error: #ef5350;
 *   --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
 *   --shadow-md: 0 2px 8px rgba(0, 0, 0, 0.4);
 *   --shadow-lg: 0 4px 16px rgba(0, 0, 0, 0.5);
 * }
 */
