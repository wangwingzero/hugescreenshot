/**
 * Property-Based Tests for AboutSection Component
 *
 * Feature: about-section (merged About + Update)
 *
 * Properties tested:
 * 1. Auto-check toggle state is always reflected in the store
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import * as fc from 'fast-check'
import AboutSection from '../../sections/AboutSection.vue'
import { useSettingsStore } from '@/stores/settings'

// ============================================================================
// Mock Tauri APIs
// ============================================================================

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@tauri-apps/api/app', () => ({
  getVersion: vi.fn().mockResolvedValue('1.0.0'),
}))

vi.mock('@tauri-apps/plugin-shell', () => ({
  open: vi.fn().mockResolvedValue(undefined),
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
            statusError: '检查更新失败',
          },
        },
      },
    },
  })
}

function mountAboutSection() {
  const i18n = createTestI18n()
  const pinia = createPinia()
  setActivePinia(pinia)

  const wrapper = mount(AboutSection, {
    global: {
      plugins: [pinia, i18n],
    },
  })

  const store = useSettingsStore()
  return { wrapper, store }
}

// ============================================================================
// Property-Based Tests
// ============================================================================

describe('Feature: about-section, Property Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  /**
   * Property 1: Auto-check toggle state is always persisted to store
   *
   * For any boolean value, toggling auto-check via the component SHALL update the store accordingly.
   */
  it('Property 1: Auto-check toggle state is always persisted to store', async () => {
    await fc.assert(
      fc.asyncProperty(fc.boolean(), async (initialAutoCheck) => {
        const { wrapper, store } = mountAboutSection()

        try {
          // Set initial state
          store.updateUpdate({ autoCheck: initialAutoCheck })
          await flushPromises()

          // Find ToggleSwitch and trigger toggle via component event
          const toggleSwitch = wrapper.findComponent({ name: 'ToggleSwitch' })
          if (toggleSwitch.exists()) {
            toggleSwitch.vm.$emit('update:modelValue', !initialAutoCheck)
            await flushPromises()
            expect(store.update.autoCheck).toBe(!initialAutoCheck)
          }

          return true
        } finally {
          wrapper.unmount()
        }
      }),
      { numRuns: 20 }
    )
  })
})
