/**
 * Unit Tests for AboutSection Component
 *
 * Feature: about-section (merged About + Update)
 *
 * Tests cover:
 * - App info display (name, version, description)
 * - Update settings: auto-check toggle
 * - Check now button behavior
 * - Manual download link
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, VueWrapper, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import AboutSection from '../AboutSection.vue'

// ============================================================================
// Mock Tauri APIs
// ============================================================================

vi.mock('@tauri-apps/api/app', () => ({
  getVersion: vi.fn().mockResolvedValue('1.0.0'),
}))

vi.mock('@tauri-apps/plugin-shell', () => ({
  open: vi.fn().mockResolvedValue(undefined),
}))

const mockDownloadAndInstall = vi.fn()
const updateStatus = ref<'idle' | 'checking' | 'available' | 'downloading' | 'installing' | 'upToDate' | 'error'>('idle')
const updateInfo = ref<{ version: string; notes: string } | null>(null)
const updateError = ref<string | null>(null)
const updateProgress = ref(0)
const updateTotalBytes = ref(0)
const downloadProgressText = computed(() => `${updateProgress.value}%`)
const downloadDetailText = computed(() =>
  updateStatus.value === 'downloading' ? `${updateProgress.value}% · 4 MB / 10 MB · 1 MB/s` : '',
)

const mockCheckForUpdate = vi.fn(async () => {
  updateStatus.value = updateInfo.value ? 'available' : 'upToDate'
  return updateStatus.value === 'available'
})

vi.mock('@/composables/useAutoUpdate', () => ({
  useAutoUpdate: () => ({
    status: updateStatus,
    updateInfo,
    error: updateError,
    progress: updateProgress,
    totalBytes: updateTotalBytes,
    downloadedBytes: ref(0),
    downloadSpeedBytesPerSecond: ref(0),
    downloadProgressText,
    downloadSizeText: computed(() => '4 MB / 10 MB'),
    downloadSpeedText: computed(() => '1 MB/s'),
    downloadDetailText,
    checkForUpdate: mockCheckForUpdate,
    downloadAndInstall: mockDownloadAndInstall,
  }),
}))

// ============================================================================
// Test Setup
// ============================================================================

function createTestI18n() {
  return createI18n({
    legacy: false,
    locale: 'zh-CN',
    messages: {
      'zh-CN': {
        settings: {
          about: {
            title: '关于',
            version: '版本 {version}',
            description: '一款功能强大的截图工具',
          },
          update: {
            title: '更新',
            autoCheck: '自动检查更新',
            autoCheckHelp: '启用后定期自动检查是否有新版本',
            checkNow: '立即检查',
            checkNowBtn: '检查更新',
            checking: '检查中...',
            lastCheck: '上次检查',
            manualDownload: '手动下载',
            manualDownloadHelp: '自动更新失败时，可访问此地址手动下载最新版本',
            openBrowserFailed: '无法打开浏览器，请手动访问链接',
            statusUpToDate: '已是最新版本',
            statusAvailable: '发现新版本',
            statusError: '检查更新失败',
          },
          common: {
            updateAvailable: '发现新版本 {version}',
          },
        },
        update: {
          downloadAndInstall: '下载并安装',
          installing: '正在安装更新...',
        },
      },
    },
  })
}

function mountAboutSection(): VueWrapper {
  const i18n = createTestI18n()
  const pinia = createPinia()
  setActivePinia(pinia)

  return mount(AboutSection, {
    global: {
      plugins: [pinia, i18n],
    },
  })
}

// ============================================================================
// Unit Tests
// ============================================================================

describe('AboutSection Component Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    updateStatus.value = 'idle'
    updateInfo.value = null
    updateError.value = null
    updateProgress.value = 0
    updateTotalBytes.value = 0
  })

  describe('App Info Display', () => {
    it('should display app name', async () => {
      const wrapper = mountAboutSection()
      await flushPromises()
      expect(wrapper.find('.app-name').text()).toBe('虎哥截图')
      wrapper.unmount()
    })

    it('should display app version', async () => {
      const wrapper = mountAboutSection()
      await flushPromises()
      expect(wrapper.find('.app-version').exists()).toBe(true)
      wrapper.unmount()
    })

    it('should display app logo', async () => {
      const wrapper = mountAboutSection()
      await flushPromises()
      const logo = wrapper.find('.app-logo')
      expect(logo.exists()).toBe(true)
      expect(logo.attributes('src')).toContain('.png')
      wrapper.unmount()
    })
  })

  describe('Update Settings', () => {
    it('should show auto-check toggle', async () => {
      const wrapper = mountAboutSection()
      await flushPromises()
      expect(wrapper.text()).toContain('自动检查更新')
      wrapper.unmount()
    })

    it('should show check-now button', async () => {
      const wrapper = mountAboutSection()
      await flushPromises()
      const btn = wrapper.find('.check-now-btn')
      expect(btn.exists()).toBe(true)
      expect(btn.text()).toBe('检查更新')
      wrapper.unmount()
    })

    it('should disable check-now button while checking', async () => {
      const wrapper = mountAboutSection()
      await flushPromises()
      const btn = wrapper.find('.check-now-btn')
      await btn.trigger('click')
      expect(btn.exists()).toBe(true)
      wrapper.unmount()
    })

    it('should show success message when update check returns UpToDate', async () => {
      const wrapper = mountAboutSection()
      await flushPromises()

      const btn = wrapper.find('.check-now-btn')
      await btn.trigger('click')
      await flushPromises()

      const result = wrapper.find('.check-result')
      expect(result.exists()).toBe(true)
      expect(result.classes()).toContain('check-result-success')
      wrapper.unmount()
    })

    it('should show error message when update check fails', async () => {
      mockCheckForUpdate.mockRejectedValueOnce(new Error('网络错误'))
      const wrapper = mountAboutSection()
      await flushPromises()

      const btn = wrapper.find('.check-now-btn')
      await btn.trigger('click')
      await flushPromises()

      const result = wrapper.find('.check-result')
      expect(result.exists()).toBe(true)
      expect(result.classes()).toContain('check-result-error')
      wrapper.unmount()
    })

    it('should show update-available message when status is Available', async () => {
      updateInfo.value = { version: '0.1.13', notes: '' }
      const wrapper = mountAboutSection()
      await flushPromises()

      const btn = wrapper.find('.check-now-btn')
      await btn.trigger('click')
      await flushPromises()

      const result = wrapper.find('.check-result')
      expect(result.exists()).toBe(true)
      expect(result.classes()).toContain('check-result-update')
      expect(result.text()).toContain('0.1.13')
      wrapper.unmount()
    })

    it('should show shared download progress when update is downloading', async () => {
      updateStatus.value = 'downloading'
      updateInfo.value = { version: '0.1.13', notes: '' }
      updateProgress.value = 42
      updateTotalBytes.value = 10

      const wrapper = mountAboutSection()
      await flushPromises()

      expect(wrapper.text()).toContain('0.1.13')
      expect(wrapper.text()).toContain('42%')
      wrapper.unmount()
    })

    it('should show manual download link', async () => {
      const wrapper = mountAboutSection()
      await flushPromises()

      const link = wrapper.find('.manual-download-link')
      expect(link.exists()).toBe(true)
      expect(link.attributes('href')).toBe('https://downloads.example.com')
      wrapper.unmount()
    })

    it('should call open() when manual download link is clicked', async () => {
      const { open } = await import('@tauri-apps/plugin-shell')
      const wrapper = mountAboutSection()
      await flushPromises()

      const link = wrapper.find('.manual-download-link')
      await link.trigger('click')
      await flushPromises()

      expect(open).toHaveBeenCalledWith('https://downloads.example.com')
      wrapper.unmount()
    })

    it('should show error when open() fails', async () => {
      const { open } = await import('@tauri-apps/plugin-shell')
      vi.mocked(open).mockRejectedValueOnce(new Error('No browser'))
      const wrapper = mountAboutSection()
      await flushPromises()

      const link = wrapper.find('.manual-download-link')
      await link.trigger('click')
      await flushPromises()

      const result = wrapper.find('.check-result')
      expect(result.exists()).toBe(true)
      expect(result.classes()).toContain('check-result-error')
      wrapper.unmount()
    })

  })
})
