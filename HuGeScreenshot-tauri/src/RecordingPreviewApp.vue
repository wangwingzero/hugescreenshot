<template>
  <div class="preview-container">
    <!-- 标题栏 -->
    <div class="titlebar" @mousedown="startDrag">
      <span class="title">录制完成</span>
      <button class="close-btn" @click="handleClose">✕</button>
    </div>

    <!-- 视频预览 -->
    <div class="video-section">
      <video
        ref="videoRef"
        class="video-player"
        :src="videoSrc"
        controls
        preload="metadata"
        @loadedmetadata="onVideoLoaded"
      />
    </div>

    <!-- 文件信息 -->
    <div class="info-section">
      <div class="info-row">
        <span class="info-label">时长</span>
        <span class="info-value">{{ formattedDuration }}</span>
      </div>
      <div class="info-row">
        <span class="info-label">大小</span>
        <span class="info-value">{{ formattedSize }}</span>
      </div>
      <div class="info-row path-row">
        <span class="info-label">路径</span>
        <span class="info-value path" :title="filePath">{{ truncatedPath }}</span>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="actions">
      <button class="action-btn" @click="openFolder">
        <span>📂</span>
        <span>打开文件夹</span>
      </button>
      <button class="action-btn" @click="copyFile">
        <span>📋</span>
        <span>复制视频</span>
      </button>
      <button class="action-btn danger" @click="deleteFile">
        <span>🗑️</span>
        <span>删除</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { invoke, convertFileSrc } from '@tauri-apps/api/core'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { listen } from '@tauri-apps/api/event'
import { openPath } from '@tauri-apps/plugin-opener'

// State
const filePath = ref('')
const duration = ref(0)
const fileSize = ref(0)
const videoRef = ref<HTMLVideoElement | null>(null)

// Computed
const videoSrc = computed(() => {
  if (!filePath.value) return ''
  return convertFileSrc(filePath.value)
})

const formattedDuration = computed(() => {
  const secs = Math.floor(duration.value)
  const mins = Math.floor(secs / 60)
  const remainingSecs = secs % 60
  return `${mins}:${remainingSecs.toString().padStart(2, '0')}`
})

const formattedSize = computed(() => {
  const bytes = fileSize.value
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
})

const truncatedPath = computed(() => {
  if (!filePath.value) return ''
  if (filePath.value.length <= 50) return filePath.value
  return '...' + filePath.value.slice(-47)
})

// Methods
function startDrag(e: MouseEvent) {
  // 如果点击的是关闭按钮或其子元素，不启动拖拽
  if ((e.target as HTMLElement).closest('.close-btn')) return
  getCurrentWindow().startDragging()
}

async function handleClose() {
  try {
    // 使用专用命令关闭预览窗口（最可靠）
    await invoke('close_recording_preview')
  } catch (e) {
    // 备用：直接关闭当前窗口
    try {
      await getCurrentWindow().close()
    } catch {}
  }
}

async function openFolder() {
  if (!filePath.value) return
  try {
    // 打开文件所在目录
    const dir = filePath.value.replace(/[/\\][^/\\]+$/, '')
    await openPath(dir)
  } catch (e) {
    console.error('打开文件夹失败:', e)
    alert('打开文件夹失败: ' + (e instanceof Error ? e.message : String(e)))
  }
}

async function copyFile() {
  if (!filePath.value) return
  try {
    // 复制文件路径到剪贴板
    await navigator.clipboard.writeText(filePath.value)
    alert('文件路径已复制到剪贴板')
  } catch (e) {
    console.error('复制失败:', e)
    alert('复制失败，请重试')
  }
}

async function deleteFile() {
  if (!filePath.value) return
  if (!confirm('确定要删除这个录制文件吗？')) return

  try {
    await invoke('delete_file', { path: filePath.value })
    handleClose()
  } catch (e) {
    console.error('删除失败:', e)
    alert('删除失败: ' + e)
  }
}

function onVideoLoaded() {
  if (videoRef.value) {
    duration.value = videoRef.value.duration
  }
}

// Lifecycle
onMounted(async () => {
  // 方法 1：监听录制结果事件（从 Rust 后端发送）
  await listen<{
    outputPath: string
    duration: number
    fileSize: number
  }>('recording-completed', (event) => {
    console.log('[Preview] 收到 recording-completed 事件:', event.payload)
    filePath.value = event.payload.outputPath
    duration.value = event.payload.duration
    fileSize.value = event.payload.fileSize
  })

  // 方法 2：从 URL hash 读取文件路径（更可靠的备用方案）
  // Rust 端创建窗口时会在 URL 中附带参数
  const hash = window.location.hash
  if (hash) {
    try {
      const data = JSON.parse(decodeURIComponent(hash.slice(1)))
      if (data.outputPath) {
        console.log('[Preview] 从 URL hash 读取数据:', data)
        filePath.value = data.outputPath
        duration.value = data.duration || 0
        fileSize.value = data.fileSize || 0
      }
    } catch (e) {
      console.warn('[Preview] 解析 URL hash 失败:', e)
    }
  }

  // 方法 3：查询录屏引擎获取最后一次录制结果
  if (!filePath.value) {
    try {
      const status = await invoke<{
        state: string
        elapsedTime: number
        outputPath: string | null
        frameCount: number
        fileSize: number
      }>('get_recording_status')
      
      if (status.outputPath) {
        console.log('[Preview] 从录屏状态获取数据:', status)
        filePath.value = status.outputPath
        duration.value = status.elapsedTime
        fileSize.value = status.fileSize
      }
    } catch (e) {
      console.warn('[Preview] 查询录屏状态失败:', e)
    }
  }
})
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
  overflow: hidden;
}

.preview-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

/* 标题栏 */
.titlebar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--color-bg-secondary);
  cursor: grab;
}

.titlebar:active {
  cursor: grabbing;
}

.title {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.close-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: var(--color-text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}

.close-btn:hover {
  background: rgba(244, 67, 54, 0.8);
  color: #fff;
}

/* 视频预览 */
.video-section {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-primary);
  min-height: 200px;
}

.video-player {
  max-width: 100%;
  max-height: 100%;
  outline: none;
}

/* 文件信息 */
.info-section {
  padding: 12px 16px;
  background: var(--color-bg-secondary);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.path-row {
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

.info-label {
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.info-value {
  color: var(--color-text-primary);
  font-size: 13px;
}

.info-value.path {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 11px;
  color: var(--color-text-secondary);
  word-break: break-all;
}

/* 操作按钮 */
.actions {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  background: var(--color-bg-secondary);
}

.action-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 12px;
  background: var(--color-surface-muted);
  border: 1px solid var(--color-border-subtle);
  border-radius: 6px;
  color: var(--color-text-primary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.action-btn:hover {
  background: var(--color-surface-strong);
  border-color: var(--color-border-subtle);
}

.action-btn.danger:hover {
  background: rgba(244, 67, 54, 0.2);
  border-color: rgba(244, 67, 54, 0.4);
  color: var(--color-error);
}
</style>
