/**
 * 自动更新组合式函数
 *
 * 在应用启动时检查更新，如果有新版本则提示用户下载安装。
 * 使用 Tauri updater 插件，更新源由 src-tauri/tauri.conf.json 指向自有发布服务器。
 */
import { computed, ref } from 'vue'
import { check } from '@tauri-apps/plugin-updater'
import { relaunch } from '@tauri-apps/plugin-process'

/** 更新状态 */
export type UpdateStatus =
  | 'idle'
  | 'checking'
  | 'available'
  | 'downloading'
  | 'installing'
  | 'upToDate'
  | 'error'

const status = ref<UpdateStatus>('idle')
const updateInfo = ref<{ version: string; notes: string } | null>(null)
const error = ref<string | null>(null)
const progress = ref(0)
const totalBytes = ref(0)
const downloadedBytes = ref(0)
const downloadSpeedBytesPerSecond = ref(0)
let lastSpeedSampleAt = 0
let lastSpeedSampleBytes = 0

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'

  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let unitIndex = 0

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex++
  }

  const fractionDigits = value >= 100 || unitIndex === 0 ? 0 : value >= 10 ? 1 : 2
  return `${value.toFixed(fractionDigits)} ${units[unitIndex]}`
}

function resetDownloadStats(): void {
  progress.value = 0
  totalBytes.value = 0
  downloadedBytes.value = 0
  downloadSpeedBytesPerSecond.value = 0
  lastSpeedSampleAt = Date.now()
  lastSpeedSampleBytes = 0
}

const downloadProgressText = computed(() => {
  if (status.value === 'downloading' && totalBytes.value <= 0 && progress.value <= 0) return '准备中'
  return `${Math.min(100, Math.max(0, progress.value))}%`
})

const downloadSizeText = computed(() => {
  if (totalBytes.value <= 0) return `已下载 ${formatBytes(downloadedBytes.value)}`
  return `${formatBytes(downloadedBytes.value)} / ${formatBytes(totalBytes.value)}`
})

const downloadSpeedText = computed(() => {
  if (downloadSpeedBytesPerSecond.value <= 0) return '计算速度中'
  return `${formatBytes(downloadSpeedBytesPerSecond.value)}/s`
})

const downloadDetailText = computed(() => {
  if (status.value === 'installing') return '下载完成，正在安装并准备重启'
  if (status.value !== 'downloading') return ''
  return `${downloadProgressText.value} · ${downloadSizeText.value} · ${downloadSpeedText.value}`
})

export function useAutoUpdate() {
  /** 检查更新 */
  async function checkForUpdate(): Promise<boolean> {
    status.value = 'checking'
    error.value = null

    try {
      const update = await check()

      if (update) {
        status.value = 'available'
        updateInfo.value = {
          version: update.version,
          notes: update.body ?? '',
        }
        console.info(`发现新版本: ${update.version}`)
        return true
      }

      status.value = 'upToDate'
      updateInfo.value = null
      console.debug('当前已是最新版本')
      return false
    } catch (e) {
      status.value = 'error'
      error.value = e instanceof Error ? e.message : String(e)
      console.warn('检查更新失败:', error.value)
      return false
    }
  }

  /** 下载并安装更新，完成后重启 */
  async function downloadAndInstall() {
    if (status.value === 'downloading' || status.value === 'installing') return

    status.value = 'downloading'
    error.value = null
    resetDownloadStats()

    try {
      const update = await check()
      if (!update) {
        status.value = 'upToDate'
        updateInfo.value = null
        return
      }

      updateInfo.value = {
        version: update.version,
        notes: update.body ?? '',
      }

      await update.downloadAndInstall((event) => {
        if (event.event === 'Started' && event.data.contentLength) {
          totalBytes.value = event.data.contentLength
          downloadedBytes.value = 0
          lastSpeedSampleAt = Date.now()
          lastSpeedSampleBytes = 0
          console.debug(`开始下载更新，大小: ${totalBytes.value} bytes`)
        } else if (event.event === 'Progress') {
          const chunkLength = event.data.chunkLength
          downloadedBytes.value += chunkLength

          const now = Date.now()
          const elapsedSeconds = (now - lastSpeedSampleAt) / 1000
          if (elapsedSeconds >= 0.5) {
            downloadSpeedBytesPerSecond.value = Math.max(
              0,
              (downloadedBytes.value - lastSpeedSampleBytes) / elapsedSeconds,
            )
            lastSpeedSampleAt = now
            lastSpeedSampleBytes = downloadedBytes.value
          }

          progress.value = totalBytes.value > 0
            ? Math.min(100, Math.round((downloadedBytes.value / totalBytes.value) * 100))
            : 0
        } else if (event.event === 'Finished') {
          if (totalBytes.value > 0) {
            downloadedBytes.value = totalBytes.value
          }
          progress.value = 100
          console.debug('更新下载完成')
        }
      })

      status.value = 'installing'
      await relaunch()
    } catch (e) {
      status.value = 'error'
      error.value = e instanceof Error ? e.message : String(e)
      console.error('更新安装失败:', error.value)
    }
  }

  return {
    status,
    updateInfo,
    error,
    progress,
    totalBytes,
    downloadedBytes,
    downloadSpeedBytesPerSecond,
    downloadProgressText,
    downloadSizeText,
    downloadSpeedText,
    downloadDetailText,
    checkForUpdate,
    downloadAndInstall,
  }
}
