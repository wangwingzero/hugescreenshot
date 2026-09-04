<script setup lang="ts">
/**
 * 应用根组件 - 主界面
 *
 * 侧边栏布局 + 深色主题 + 自定义标题栏
 * 参考 C++ 版本的设计
 */
import { ref, computed, defineAsyncComponent, onMounted, onUnmounted, watch } from 'vue'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
import { invoke } from '@tauri-apps/api/core'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { useSettingsStore } from '@/stores/settings'
import { useTheme } from '@/composables/useTheme'
import { useAutoUpdate } from '@/composables/useAutoUpdate'
import { UPDATE_CHECK_INTERVAL_MS } from '@/constants/update'
import { DEFAULT_CONFIG, type MouseHighlightConfig } from '@/types'
import appLogoUrl from '@resources/PNG/虎哥截图.png'

// 静态导入关键面板（避免生产构建中 defineAsyncComponent 加载失败导致白屏）
import SettingsPanel from '@/components/settings/SettingsPanel.vue'
import MouseHighlightSettings from '@/components/settings/MouseHighlightSettings.vue'

// 非关键路径组件保持懒加载，但添加错误处理防止静默失败
const ScheduledShutdownPanel = defineAsyncComponent({
  loader: () => import('@/components/shutdown').then(m => m.ScheduledShutdownPanel),
  onError(error, _retry, fail) {
    console.error('[AsyncComponent] ScheduledShutdownPanel 加载失败:', error)
    fail()
  },
})
const SearchDialog = defineAsyncComponent({
  loader: () => import('@/components/FileSearch/SearchDialog.vue'),
  onError(error, _retry, fail) {
    console.error('[AsyncComponent] SearchDialog 加载失败:', error)
    fail()
  },
})

// 菜单项定义
interface MenuItem {
  id: string
  title: string
  icon: string
  group?: string
}

// 菜单项列表
const menuItems: MenuItem[] = [
  { id: 'workbench', title: '工作台', icon: 'workbench' },
  // 辅助工具
  { id: 'mouse_highlight', title: '鼠标高亮', icon: 'cursor', group: '辅助工具' },
  { id: 'power_manager', title: '预约关机', icon: 'clock', group: '辅助工具' },
]


// 自动更新
const {
  status: updateStatus,
  updateInfo,
  progress: updateProgress,
  totalBytes: updateTotalBytes,
  downloadProgressText,
  downloadDetailText,
  checkForUpdate,
  downloadAndInstall,
} = useAutoUpdate()
const showUpdateBanner = ref(false)
const isUpdateInProgress = computed(() =>
  updateStatus.value === 'downloading' || updateStatus.value === 'installing',
)
const updateActionText = computed(() => {
  if (updateStatus.value === 'checking') return '检查中...'
  if (updateStatus.value === 'downloading') return `下载中 ${downloadProgressText.value}`
  if (updateStatus.value === 'installing') return '安装中...'
  if (updateStatus.value === 'error') return '重试更新'
  return '立即更新'
})
const updateProgressWidth = computed(() => `${Math.min(100, Math.max(0, updateProgress.value))}%`)
const shouldRenderUpdateBanner = computed(() =>
  showUpdateBanner.value &&
  !!updateInfo.value &&
  (
    updateStatus.value === 'available' ||
    updateStatus.value === 'downloading' ||
    updateStatus.value === 'installing' ||
    updateStatus.value === 'error'
  ),
)

// 文件搜索对话框显示状态
// **Validates: Requirements 8.1**
const showFileSearchDialog = ref(false)

// 当前选中的菜单项
const activeMenu = ref('')

// 侧边栏展开状态
const sidebarExpanded = ref(true)

// 事件监听器
let unlistenTrayAction: UnlistenFn | null = null
let unlistenHotkey: UnlistenFn | null = null
let unlistenAppReady: UnlistenFn | null = null
let unlistenResize: UnlistenFn | null = null

// 应用就绪状态（后台初始化完成后变为 true）
const isAppReady = ref(false)

// 窗口最大化状态
const isMaximized = ref(false)

// 鼠标高亮面板显示状态
const showMouseHighlightPanel = ref(false)

// 设置面板显示状态
const showSettingsPanel = ref(false)

// 设置面板目标页
const settingsCategory = ref('general')

// 预约关机面板显示状态
const showShutdownPanel = ref(false)

// 设置 store
const settingsStore = useSettingsStore()

function shouldCheckForUpdateOnStartup(): boolean {
  const updateConfig = settingsStore.update
  if (!updateConfig.autoCheck) return false

  if (!updateConfig.lastCheckTime) return true

  const lastCheckMs = Date.parse(updateConfig.lastCheckTime)
  if (Number.isNaN(lastCheckMs)) return true

  return Date.now() - lastCheckMs >= UPDATE_CHECK_INTERVAL_MS
}

watch(updateStatus, (nextStatus) => {
  if (
    (nextStatus === 'available' ||
      nextStatus === 'downloading' ||
      nextStatus === 'installing' ||
      nextStatus === 'error') &&
    updateInfo.value
  ) {
    showUpdateBanner.value = true
  }
})

// 初始化主题管理 - 监听 settingsStore 中的主题变化并自动应用到 DOM
useTheme()

// 鼠标高亮配置 - 使用本地状态，避免依赖可能不完整的后端配置
const mouseHighlightConfig = ref<MouseHighlightConfig>({ ...DEFAULT_CONFIG.mouseHighlight })

// 更新鼠标高亮配置
function updateMouseHighlightConfig(config: MouseHighlightConfig) {
  mouseHighlightConfig.value = { ...config }
  // 同步到 store（如果需要持久化）
  settingsStore.updateMouseHighlight(config)
}

// 窗口控制函数
async function minimizeWindow() {
  await getCurrentWindow().minimize()
}

async function toggleMaximize() {
  const win = getCurrentWindow()
  if (isMaximized.value) {
    await win.unmaximize()
  } else {
    await win.maximize()
  }
  isMaximized.value = !isMaximized.value
}

async function closeWindow() {
  await getCurrentWindow().close()
}

// 处理顶部工具栏点击
async function handleToolClick(tool: string) {
  if (tool === 'screenshot') {
    try {
      // 使用 show_overlay_windows 显示预加载的窗口（性能优化）
      // 如果窗口未预加载，会自动创建
      await invoke('show_overlay_windows')
      console.debug('截图模式已启动')
    } catch (error) {
      console.error('启动截图失败:', error)
    }
  }
}

// 处理菜单项点击
async function handleMenuClick(itemId: string) {
  activeMenu.value = itemId

  // 关闭其他面板（包括设置面板）
  showMouseHighlightPanel.value = false
  showSettingsPanel.value = false
  showShutdownPanel.value = false

  if (itemId === 'workbench') {
    await openWorkbench()
  } else if (itemId === 'mouse_highlight') {
    showMouseHighlightPanel.value = true
  } else if (itemId === 'power_manager') {
    showShutdownPanel.value = true
  }
}

// 打开工作台窗口
async function openWorkbench() {
  try {
    await invoke('open_workbench_window')
    console.debug('工作台窗口已打开')
  } catch (error) {
    console.error('打开工作台窗口失败:', error)
  }
}

// 打开设置
function openSettings(category = 'general') {
  // 关闭其他面板
  showMouseHighlightPanel.value = false
  showShutdownPanel.value = false
  
  // 清除菜单选中状态
  activeMenu.value = ''

  settingsCategory.value = category
  showSettingsPanel.value = true
}

function dismissUpdateBanner() {
  if (isUpdateInProgress.value) return
  showUpdateBanner.value = false
}

// 切换侧边栏
function toggleSidebar() {
  sidebarExpanded.value = !sidebarExpanded.value
}

// 处理托盘菜单事件
async function handleTrayAction(action: string) {
  console.debug('收到托盘事件:', action)
  if (action === 'screenshot') {
    await handleToolClick('screenshot')
  } else if (action === 'workbench') {
    await openWorkbench()
  }
}

// 处理热键事件
interface HotkeyEvent {
  action: string
  shortcut: string
  timestamp: number
}

async function handleHotkeyTriggered(event: HotkeyEvent) {
  console.debug('热键触发:', event.action, event.shortcut)

  switch (event.action) {
    case 'screenshot':
      await handleToolClick('screenshot')
      break
    case 'ocr':
      await handleToolClick('screenshot')
      break
    case 'recording':
      await handleRecordingHotkey()
      break
    case 'pin':
      // TODO: 实现钉图功能
      break
    case 'filesearch':
      // 文件搜索热键触发 - 打开/切换搜索对话框
      // **Validates: Requirements 8.1**
      toggleFileSearchDialog()
      break
    case 'workbench':
      await openWorkbench()
      break
    default:
      console.warn('未知的热键动作:', event.action)
  }
}

/**
 * 切换文件搜索对话框显示状态
 * 如果对话框已打开则关闭，否则打开
 * **Validates: Requirements 8.1**
 */
function toggleFileSearchDialog() {
  showFileSearchDialog.value = !showFileSearchDialog.value
}

/**
 * 关闭文件搜索对话框
 */
function closeFileSearchDialog() {
  showFileSearchDialog.value = false
}

/**
 * 处理录屏热键触发
 * 
 * 如果当前没有录制，启动录制（全屏，使用默认设置）。
 * 如果正在录制，停止录制。
 */
async function handleRecordingHotkey() {
  try {
    const status = await invoke<{ state: string }>('get_recording_status')
    
    if (status.state === 'recording' || status.state === 'paused') {
      // 正在录制，停止
      const result = await invoke<{ outputPath: string; duration: number; fileSize: number }>('stop_recording')
      await invoke('close_recording_control')
      // 恢复 overlay 正常模式（取消鼠标穿透+恢复捕获）
      await invoke('set_overlay_recording_mode', { enabled: false })
      // 关闭录屏区域边框窗口
      await invoke('close_recording_border')
      // 打开预览窗口
      await invoke('open_recording_preview', {
        outputPath: result.outputPath,
        duration: result.duration,
        fileSize: result.fileSize,
      })
    } else {
      // 开始全屏录制
      await invoke('start_recording', {
        params: {
          fps: 30,
          quality: 'medium',
        }
      })
      // 打开录制控制面板
      await invoke('open_recording_control')
    }
  } catch (e) {
    console.error('录屏热键处理失败:', e)
  }
}

// 获取分组的第一个菜单项索引
function getGroupStartIndex(groupName: string): number {
  return menuItems.findIndex(item => item.group === groupName)
}

// 获取图标 SVG
function getIcon(name: string): string {
  const icons: Record<string, string> = {
    workbench: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>`,
    word: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`,
    cursor: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m4 4 7.07 17 2.51-7.39L21 11.07 4 4z"/><path d="m15 15 6 6"/></svg>`,
    clock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
    settings: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
    menu: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>`,
    screenshot: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 7h.01"/><path d="M7 17h.01"/><path d="M17 7h.01"/><path d="M17 17h.01"/></svg>`,
  }
  return icons[name] || ''
}

onMounted(async () => {
  // 监听后台初始化完成事件
  unlistenAppReady = await listen<{ elapsed_ms: number }>('app:ready', (event) => {
    isAppReady.value = true
    console.debug(`后台初始化完成，耗时 ${event.payload.elapsed_ms}ms`)
  })

  // 安全兜底：5 秒后强制就绪（防止事件丢失）
  setTimeout(() => {
    if (!isAppReady.value) {
      isAppReady.value = true
      console.warn('后台初始化超时，强制就绪')
    }
  }, 5000)

  // 等待后台初始化完成后再执行后续初始化
  // 避免后台服务尚未注册时过早执行配置加载等初始化
  const waitForBackendReady = (): Promise<void> => {
    if (isAppReady.value) return Promise.resolve()
    return new Promise((resolve) => {
      const checkInterval = setInterval(() => {
        if (isAppReady.value) {
          clearInterval(checkInterval)
          resolve()
        }
      }, 100)
      // 最多等 6 秒（兜底超时之后也会 resolve）
      setTimeout(() => {
        clearInterval(checkInterval)
        resolve()
      }, 6000)
    })
  }

  await waitForBackendReady()
  // 加载设置配置
  try {
    await settingsStore.loadConfig()
    console.debug('设置配置已加载')
  } catch (error) {
    console.warn('加载设置配置失败，使用默认值:', error)
  }

  // 检查自动更新（静默，不阻塞启动）
  if (shouldCheckForUpdateOnStartup()) {
    checkForUpdate().then((hasUpdate) => {
      if (updateStatus.value !== 'error') {
        settingsStore.updateUpdate({ lastCheckTime: new Date().toISOString() })
      }
      if (hasUpdate && updateInfo.value?.version !== settingsStore.update.skipVersion) {
        showUpdateBanner.value = true
      }
    })
  }

  // 监听托盘事件
  unlistenTrayAction = await listen<string>('tray-action', (event) => {
    handleTrayAction(event.payload)
  })

  // 监听热键事件
  unlistenHotkey = await listen<HotkeyEvent>('hotkey-triggered', (event) => {
    handleHotkeyTriggered(event.payload)
  })
  console.debug('热键事件监听器已注册')

  // 监听窗口大小变化，更新最大化状态
  const win = getCurrentWindow()
  isMaximized.value = await win.isMaximized()

  unlistenResize = await listen('tauri://resize', async () => {
    isMaximized.value = await win.isMaximized()
  })
})

onUnmounted(() => {
  if (unlistenAppReady) {
    unlistenAppReady()
  }
  if (unlistenTrayAction) {
    unlistenTrayAction()
  }
  if (unlistenHotkey) {
    unlistenHotkey()
  }
  if (unlistenResize) {
    unlistenResize()
  }
})
</script>

<template>
  <div class="app-container">
    <!-- 启动加载屏 -->
    <Transition name="splash-fade">
      <div v-if="!isAppReady" class="splash-screen">
        <div class="splash-content">
          <img class="splash-icon" :src="appLogoUrl" alt="虎哥截图" />
          <span class="splash-title">虎哥截图</span>
          <div class="splash-loading">
            <div class="splash-loading-bar"></div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 自定义标题栏 -->
    <header class="titlebar" data-tauri-drag-region>
      <div class="titlebar-left" data-tauri-drag-region>
        <img class="titlebar-icon" :src="appLogoUrl" alt="虎哥截图" />
        <span class="titlebar-title" data-tauri-drag-region>虎哥截图</span>
      </div>
      <div class="titlebar-controls">
        <button class="titlebar-btn" @click="minimizeWindow" title="最小化">
          <svg viewBox="0 0 12 12" width="12" height="12">
            <line x1="2" y1="6" x2="10" y2="6" stroke="currentColor" stroke-width="1"/>
          </svg>
        </button>
        <button class="titlebar-btn" @click="toggleMaximize" :title="isMaximized ? '还原' : '最大化'">
          <svg v-if="!isMaximized" viewBox="0 0 12 12" width="12" height="12">
            <rect x="2" y="2" width="8" height="8" fill="none" stroke="currentColor" stroke-width="1"/>
          </svg>
          <svg v-else viewBox="0 0 12 12" width="12" height="12">
            <rect x="3" y="1" width="6" height="6" fill="none" stroke="currentColor" stroke-width="1"/>
            <path d="M1 4 L1 10 L7 10 L7 8" fill="none" stroke="currentColor" stroke-width="1"/>
          </svg>
        </button>
        <button class="titlebar-btn titlebar-btn-close" @click="closeWindow" title="关闭">
          <svg viewBox="0 0 12 12" width="12" height="12">
            <line x1="2" y1="2" x2="10" y2="10" stroke="currentColor" stroke-width="1"/>
            <line x1="10" y1="2" x2="2" y2="10" stroke="currentColor" stroke-width="1"/>
          </svg>
        </button>
      </div>
    </header>

    <!-- 顶部工具栏 (已整合进侧边栏或隐藏，保持 DOM 结构如果不使用则移除，这里我们将其移除，改用 Sidebar 中的按钮) -->
    <!-- 移除旧工具栏 div class="top-toolbar" -->

    <div class="main-layout">
      <!-- 左侧侧边栏 -->
      <aside class="sidebar" :class="{ collapsed: !sidebarExpanded }">
        <!-- 汉堡菜单 -->
        <button class="menu-toggle" @click="toggleSidebar">
          <span v-html="getIcon('menu')"></span>
        </button>

        <!-- 菜单列表 -->
        <nav class="menu-list">
          <!-- 截图大按钮 - 放在侧边栏顶部更显眼 -->
          <button class="menu-item" style="margin-bottom: 8px;" @click="handleToolClick('screenshot')">
            <span class="menu-icon" v-html="getIcon('screenshot')"></span>
            <span class="menu-text">截图</span>
          </button>

          <!-- 无分组的菜单项 -->
          <template v-for="(item, index) in menuItems" :key="item.id">
            <!-- 分组标题 -->
            <div
              v-if="item.group && getGroupStartIndex(item.group) === index"
              class="menu-group-title"
            >
              {{ item.group }}
            </div>
            <!-- 菜单项 -->
            <button
              class="menu-item"
              :class="{ active: activeMenu === item.id }"
              @click="handleMenuClick(item.id)"
            >
              <span class="menu-icon" v-html="getIcon(item.icon)"></span>
              <span class="menu-text">{{ item.title }}</span>
            </button>
          </template>
        </nav>

        <!-- 底部设置 -->
        <button class="menu-item settings-btn" @click="openSettings()">
          <span class="menu-icon" v-html="getIcon('settings')"></span>
          <span class="menu-text">设置</span>
        </button>
      </aside>

      <!-- 右侧主内容区 -->
      <main class="main-content">

        <!-- 鼠标高亮面板 -->
        <div v-if="showMouseHighlightPanel" class="panel-container mouse-highlight-panel">
          <div class="panel-header">
            <h2 class="panel-title">鼠标高亮</h2>
            <button class="panel-close-btn" @click="showMouseHighlightPanel = false">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
          <div class="panel-content">
            <MouseHighlightSettings
              :config="mouseHighlightConfig"
              @update:config="updateMouseHighlightConfig"
            />
          </div>
        </div>

        <!-- 设置面板 -->
        <div v-if="showSettingsPanel" class="panel-container settings-panel-container">
          <SettingsPanel :initial-category="settingsCategory" />
        </div>

        <!-- 预约关机面板 -->
        <div v-if="showShutdownPanel" class="panel-container shutdown-panel">
          <div class="panel-header">
            <h2 class="panel-title">预约关机</h2>
            <button class="panel-close-btn" @click="showShutdownPanel = false">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
          <div class="panel-content">
            <ScheduledShutdownPanel />
          </div>
        </div>

        <div
          v-if="!showMouseHighlightPanel && !showSettingsPanel && !showShutdownPanel"
          class="welcome-content"
        >
          <img class="app-logo" :src="appLogoUrl" alt="虎哥截图" />
          <h1 class="app-title">虎哥截图</h1>
          <p class="app-hint">按 Alt+X 开始截图</p>
        </div>
      </main>
    </div>

    <!-- 文件搜索对话框 (Alt+Space 触发) -->
    <!-- **Validates: Requirements 8.1** -->
    <SearchDialog
      v-if="showFileSearchDialog"
      :visible="showFileSearchDialog"
      @close="closeFileSearchDialog"
    />

    <!-- 自动更新通知 -->
    <Transition name="slide-down">
      <div
        v-if="shouldRenderUpdateBanner"
        class="update-banner"
        :class="{ 'update-banner-active': isUpdateInProgress }"
      >
        <div class="update-banner-content">
          <span class="update-icon">🔄</span>
          <div class="update-message">
            <span class="update-text">
              发现新版本 <strong>{{ updateInfo?.version }}</strong>
            </span>
            <span v-if="isUpdateInProgress" class="update-detail">
              {{ downloadDetailText }}
            </span>
          </div>
          <button
            class="update-btn update-btn-primary"
            :disabled="isUpdateInProgress"
            @click="downloadAndInstall"
          >
            {{ updateActionText }}
          </button>
          <button
            class="update-btn update-btn-dismiss"
            :disabled="isUpdateInProgress"
            @click="dismissUpdateBanner"
          >
            稍后
          </button>
        </div>
        <div
          v-if="isUpdateInProgress"
          class="update-progress-track"
          :class="{ indeterminate: updateTotalBytes <= 0 }"
        >
          <div
            class="update-progress-bar"
            :style="{ width: updateTotalBytes > 0 ? updateProgressWidth : '35%' }"
          ></div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.app-container {
  /* 使用新定义的全局变量 */
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg-primary); /* 全局背景 */
  color: var(--color-text-primary);
  font-family: var(--font-family);
  overflow: hidden; /* 防止圆角溢出 */
}

/* 自定义标题栏 - 统一风格 */
.titlebar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 38px; /* 增加高度 */
  padding: 0 12px;
  background-color: var(--color-bg-secondary); /* 侧边栏/标题栏统一背景 */
  user-select: none;
  -webkit-user-select: none;
  border-bottom: 0.5px solid var(--color-border-light); /* 微妙分割线 */
}

.titlebar-left {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-left: 68px; /* 为红绿灯留出空间 (模拟 Mac) 或保持原样 */
}

.titlebar-icon {
  width: 18px;
  height: 18px;
  object-fit: contain;
  border-radius: 4px;
}

.titlebar-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.titlebar-controls {
  display: flex;
  align-items: center;
  height: 100%;
  gap: 8px;
}

.titlebar-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.titlebar-btn:hover {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.titlebar-btn-close:hover {
  background-color: var(--color-error);
  color: white;
}

/* 顶部工具栏 - 融合进内容区或侧边栏 */
.top-toolbar {
  display: none; /* 隐藏旧的工具栏，整合进侧边栏或作为悬浮按钮 */
}

/* 主布局 */
.main-layout {
  flex: 1;
  display: flex;
  overflow: hidden;
  background-color: var(--color-bg-primary);
}

/* 侧边栏 - Mac 风格 */
.sidebar {
  width: 240px; /* 加宽 */
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg-secondary);
  border-right: 0.5px solid var(--color-border-light);
  transition: width var(--transition-normal);
  padding-bottom: var(--spacing-md);
}

.sidebar.collapsed {
  width: 68px;
}

.sidebar.collapsed .menu-text,
.sidebar.collapsed .menu-group-title {
  opacity: 0;
  pointer-events: none;
  display: none;
}

/* 汉堡菜单 */
.menu-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 48px;
  padding: 0;
  background: none;
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: color var(--transition-fast);
}

.menu-toggle:hover {
  color: var(--color-text-primary);
}

/* 菜单列表 */
.menu-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 12px; /* 增加左右内边距 */
  display: flex;
  flex-direction: column;
  gap: 4px; /* 菜单项间距 */
}

/* 分组标题 */
.menu-group-title {
  padding: 16px 12px 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.8px;
}

/* 菜单项 - Pill Style */
.menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 8px 12px;
  background: transparent;
  border: none;
  border-radius: var(--radius-md); /* 圆角药丸 */
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  text-align: left;
  font-weight: 500;
}

.menu-item:hover {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.menu-item.active {
  background-color: var(--color-accent); /* 激活色 */
  color: var(--color-text-inverse);
  box-shadow: var(--shadow-sm);
}

.menu-item.active .menu-icon {
  color: var(--color-text-inverse);
}

.menu-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  opacity: 0.8;
  transition: opacity var(--transition-fast);
}

.menu-item.active .menu-icon {
  opacity: 1;
}

.menu-icon :deep(svg) {
  width: 100%;
  height: 100%;
}

.menu-text {
  font-size: 13px;
  white-space: nowrap;
}

/* 设置按钮 */
.settings-btn {
  margin: 0 12px;
  width: auto;
  border-top: none;
}

/* 主内容区 */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background-color: var(--color-bg-primary);
  position: relative;
  border-top-left-radius: var(--radius-lg); /* 内容区圆角 */
  margin-top: 1px; /* 微调 */
  box-shadow: -1px -1px 0 var(--color-border-light); /* 模拟内嵌边框 */
  overflow: hidden;
}

.welcome-content {
  text-align: center;
  animation: fadeIn 0.5s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.app-logo {
  width: 96px;
  height: 96px;
  margin: 0 auto 32px;
  object-fit: contain;
  filter: drop-shadow(0 4px 12px rgba(0,0,0,0.2));
}

.app-logo :deep(svg) {
  width: 100%;
  height: 100%;
}

.app-title {
  font-size: 32px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--color-text-primary);
  letter-spacing: -0.5px;
}

.app-hint {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background-color: var(--color-bg-secondary);
  border-radius: var(--radius-full);
  font-size: 13px;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border-light);
}

/* 滚动条隐藏但可滚动 */
.menu-list::-webkit-scrollbar {
  width: 0;
  background: transparent;
}


/* 对话框遮罩层 */
.dialog-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-overlay);
  z-index: 100;
}

/* 面板容器 */
.panel-container {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--color-bg-primary);
  z-index: 50;
}

/* 鼠标高亮面板 */
.mouse-highlight-panel {
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  border-bottom: 1px solid var(--color-border);
}

.panel-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: var(--color-text-primary);
}

.panel-close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: none;
  border: none;
  border-radius: 4px;
  color: var(--color-text-tertiary);
  cursor: pointer;
  transition: all 0.15s;
}

.panel-close-btn:hover {
  background: var(--color-surface-hover);
  color: var(--color-text-primary);
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

/* 设置面板容器 */
.settings-panel-container {
  /* 移除居中对齐，让面板充满整个内容区域 */
  width: 100%;
  height: 100%;
}

/* 预约关机面板 */
.shutdown-panel {
  display: flex;
  flex-direction: column;
}

/* ============================================================
   启动加载屏（Splash Screen）
   ============================================================ */
.splash-screen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-primary);
}

.splash-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.splash-icon {
  width: 64px;
  height: 64px;
  object-fit: contain;
  animation: splash-bounce 1.5s ease-in-out infinite;
}

.splash-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text-primary);
  letter-spacing: 2px;
}

.splash-loading {
  width: 120px;
  height: 3px;
  background: var(--color-surface-muted);
  border-radius: 2px;
  overflow: hidden;
  margin-top: 8px;
}

.splash-loading-bar {
  width: 40%;
  height: 100%;
  background: linear-gradient(90deg, var(--color-accent), var(--color-accent));
  border-radius: 2px;
  animation: splash-loading 1.2s ease-in-out infinite;
}

@keyframes splash-bounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

@keyframes splash-loading {
  0% { transform: translateX(-100%); }
  50% { transform: translateX(200%); }
  100% { transform: translateX(-100%); }
}

/* Splash screen 淡出动画 */
.splash-fade-leave-active {
  transition: opacity 0.4s ease;
}

.splash-fade-leave-to {
  opacity: 0;
}

/* 更新通知横幅 */
.update-banner {
  position: fixed;
  top: 32px; /* 标题栏下方 */
  left: 0;
  right: 0;
  z-index: 9999;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  padding: 9px 16px 10px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.update-banner-content {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  font-size: 13px;
  color: #fff;
}

.update-banner-active {
  padding-bottom: 13px;
}

.update-icon {
  font-size: 16px;
}

.update-message {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.update-text strong {
  color: #fbbf24;
}

.update-detail {
  min-width: 240px;
  color: rgba(255, 255, 255, 0.88);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.update-btn {
  padding: 4px 14px;
  border-radius: 4px;
  border: none;
  font-size: 12px;
  cursor: pointer;
  transition: opacity 0.2s;
}

.update-btn:hover {
  opacity: 0.85;
}

.update-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.update-btn-primary {
  min-width: 96px;
  background: #fff;
  color: #2563eb;
  font-weight: 600;
}

.update-btn-dismiss {
  background: transparent;
  color: rgba(255, 255, 255, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.3);
}

.update-progress-track {
  position: absolute;
  left: 16px;
  right: 16px;
  bottom: 5px;
  height: 3px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.22);
}

.update-progress-bar {
  height: 100%;
  min-width: 3px;
  border-radius: inherit;
  background: #fbbf24;
  transition: width 0.2s ease;
}

.update-progress-track.indeterminate .update-progress-bar {
  animation: update-progress-indeterminate 1.2s ease-in-out infinite;
}

@keyframes update-progress-indeterminate {
  0% { transform: translateX(-120%); }
  100% { transform: translateX(320%); }
}

/* 更新横幅滑入动画 */
.slide-down-enter-active {
  transition: transform 0.3s ease, opacity 0.3s ease;
}

.slide-down-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.slide-down-enter-from {
  transform: translateY(-100%);
  opacity: 0;
}

.slide-down-leave-to {
  transform: translateY(-100%);
  opacity: 0;
}
</style>
