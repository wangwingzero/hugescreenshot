/**
 * Property-Based Tests for Sidebar Navigation
 *
 * Feature: settings-enhancement
 *
 * This file tests the sidebar navigation behavior:
 * - Property 2: Category Completeness
 * - Property 3: Active Category Highlighting
 *
 * **Validates: Requirements 1.3, 1.4**
 */

import { describe, it, expect } from 'vitest'
import { mount, VueWrapper } from '@vue/test-utils'
import * as fc from 'fast-check'
import { createI18n } from 'vue-i18n'
import SettingsSidebar from '../../SettingsSidebar.vue'
import { icons, type IconName } from '@/components/icons'

// ============================================================================
// Test Setup
// ============================================================================

/**
 * Settings menu item definition (matching SettingsSidebar.vue)
 */
interface SettingsMenuItem {
  id: string
  icon: IconName
  labelKey: string
}

/**
 * Settings group with header and items (matching SettingsSidebar.vue)
 */
interface SettingsGroup {
  id: string
  headerKey: string
  items: SettingsMenuItem[]
}

/**
 * All settings groups as defined in SettingsSidebar.vue
 * Updated to match the current component structure
 */
const settingsGroups: SettingsGroup[] = [
  {
    id: 'basic',
    headerKey: 'settings.group.basic',
    items: [
      { id: 'general', icon: 'settings', labelKey: 'settings.general' },
      { id: 'hotkeys', icon: 'keyboard', labelKey: 'settings.hotkeys' },
      { id: 'screenshot', icon: 'camera', labelKey: 'settings.screenshot' },
      { id: 'ocr', icon: 'scan-text', labelKey: 'settings.ocr' },
    ]
  },
  {
    id: 'features',
    headerKey: 'settings.group.features',
    items: [
      { id: 'pinImage', icon: 'pin', labelKey: 'settings.pinImage.title' },
      { id: 'recording', icon: 'video', labelKey: 'settings.recording' },
    ]
  },
  {
    id: 'system',
    headerKey: 'settings.group.system',
    items: [
      { id: 'notification', icon: 'bell', labelKey: 'settings.notification.title' },
      { id: 'about', icon: 'info', labelKey: 'settings.about.title' },
    ]
  },
]

/** All category IDs */
const allCategoryIds: string[] = settingsGroups.flatMap(group => group.items.map(item => item.id))

/** All menu items */
const allMenuItems: SettingsMenuItem[] = settingsGroups.flatMap(group => group.items)

/**
 * Create i18n instance for testing
 */
function createTestI18n() {
  return createI18n({
    legacy: false,
    locale: 'en',
    messages: {
      en: {
        settings: {
          group: {
            basic: 'Basic Settings',
            features: 'Feature Settings',
            documents: 'Document Processing',
            system: 'System Settings',
          },
          general: 'General',
          hotkeys: 'Hotkeys',
          screenshot: 'Screenshot',
          annotation: 'Annotation',
          pinImage: {
            title: 'Pin Image',
          },
          recording: 'Recording',
          ocr: 'OCR',
          mouseHighlight: 'Mouse Highlight',
          webToMarkdown: 'Web to Markdown',
          fileToMarkdown: 'File to Markdown',
          notification: {
            title: 'Notification',
          },
          update: 'Update',
          advanced: 'Advanced',
          about: {
            title: 'About',
          },
        }
      }
    }
  })
}

/**
 * Mount SettingsSidebar with test configuration
 */
function mountSidebar(activeCategory: string = 'general'): VueWrapper {
  const i18n = createTestI18n()
  
  return mount(SettingsSidebar, {
    props: {
      modelValue: activeCategory,
    },
    global: {
      plugins: [i18n],
    },
  })
}

// ============================================================================
// Property 2: Category Completeness
// ============================================================================

describe('Feature: settings-enhancement, Property 2: Category Completeness', () => {
  it('should have non-empty icon for all categories', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: allMenuItems.length - 1 }),
        (index: number) => {
          const item = allMenuItems[index]
          expect(item.icon).toBeDefined()
          expect(typeof item.icon).toBe('string')
          expect(item.icon.length).toBeGreaterThan(0)
        }
      ),
      { numRuns: 100, verbose: true }
    )
  })

  it('should have non-empty labelKey for all categories', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: allMenuItems.length - 1 }),
        (index: number) => {
          const item = allMenuItems[index]
          expect(item.labelKey).toBeDefined()
          expect(typeof item.labelKey).toBe('string')
          expect(item.labelKey.length).toBeGreaterThan(0)
        }
      ),
      { numRuns: 100, verbose: true }
    )
  })

  it('should have valid icon name in icon registry for all categories', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: allMenuItems.length - 1 }),
        (index: number) => {
          const item = allMenuItems[index]
          expect(icons).toHaveProperty(item.icon)
          expect(icons[item.icon]).toBeDefined()
        }
      ),
      { numRuns: 100, verbose: true }
    )
  })

  it('should have unique category IDs', () => {
    const uniqueIds = new Set(allCategoryIds)
    expect(uniqueIds.size).toBe(allCategoryIds.length)
  })

  it('should have exactly 8 menu items across 3 groups', () => {
    expect(settingsGroups.length).toBe(3)
    expect(allMenuItems.length).toBe(8)
  })
})

// ============================================================================
// Property 3: Active Category Highlighting
// ============================================================================

describe('Feature: settings-enhancement, Property 3: Active Category Highlighting', () => {
  it('should have exactly one active item at any time', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...allCategoryIds),
        (activeCategoryId: string) => {
          const wrapper = mountSidebar(activeCategoryId)
          const activeButtons = wrapper.findAll('.menu-item.active')
          expect(activeButtons.length).toBe(1)
          wrapper.unmount()
        }
      ),
      // Reduced numRuns for component mounting tests to avoid timeout
      { numRuns: 20, verbose: true }
    )
  }, 30000) // 30s timeout for component tests

  it('should update active class when modelValue changes', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom(...allCategoryIds),
        fc.constantFrom(...allCategoryIds),
        async (firstCategory: string, secondCategory: string) => {
          const wrapper = mountSidebar(firstCategory)
          
          let activeButtons = wrapper.findAll('.menu-item.active')
          expect(activeButtons.length).toBe(1)
          
          await wrapper.setProps({ modelValue: secondCategory })
          await wrapper.vm.$nextTick()
          
          activeButtons = wrapper.findAll('.menu-item.active')
          expect(activeButtons.length).toBe(1)
          
          wrapper.unmount()
          return true
        }
      ),
      // Reduced numRuns for component mounting tests to avoid timeout
      { numRuns: 20, verbose: true }
    )
  }, 30000) // 30s timeout for component tests

  it('should emit update:modelValue when menu item is clicked', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom(...allCategoryIds),
        fc.integer({ min: 0, max: allCategoryIds.length - 1 }),
        async (initialCategory: string, targetIndex: number) => {
          const wrapper = mountSidebar(initialCategory)
          const buttons = wrapper.findAll('.menu-item')
          
          await buttons[targetIndex].trigger('click')
          await wrapper.vm.$nextTick()
          
          const emitted = wrapper.emitted('update:modelValue')
          expect(emitted).toBeDefined()
          expect(emitted!.length).toBeGreaterThan(0)
          
          const lastEmitted = emitted![emitted!.length - 1]
          expect(lastEmitted[0]).toBe(allCategoryIds[targetIndex])
          
          wrapper.unmount()
          return true
        }
      ),
      { numRuns: 100, verbose: true }
    )
  })

  it('should render all 8 menu items', () => {
    const wrapper = mountSidebar('general')
    const buttons = wrapper.findAll('.menu-item')
    expect(buttons.length).toBe(8)
    wrapper.unmount()
  })

  it('should render all 3 group headers', () => {
    const wrapper = mountSidebar('general')
    const headers = wrapper.findAll('.group-header')
    expect(headers.length).toBe(3)
    wrapper.unmount()
  })
})
