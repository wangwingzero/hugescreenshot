/**
 * Property-Based Tests for Settings Store Dirty Flag Behavior
 *
 * Feature: settings-enhancement, Property 14: Dirty Flag on Change
 *
 * **Validates: Requirements 11.1**
 *
 * Property Definition:
 * For any setting value change, the isDirty flag SHALL be set to true.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import * as fc from 'fast-check'
import { useSettingsStore } from '../settings'
import type {
  GeneralConfig,
  HotkeyConfig,
  ScreenshotConfig,
  AnnotationConfig,
  OcrConfig,
  RecordingConfig,
  PinImageConfig,
  MouseHighlightConfig,
  WebToMarkdownConfig,
  FileToMarkdownConfig,
  NotificationConfig,
  UpdateConfig,
  AdvancedConfig,
} from '@/types/config'

// ============================================================================
// Arbitraries for partial config updates
// ============================================================================

/** Arbitrary for partial GeneralConfig updates */
const partialGeneralConfigArb: fc.Arbitrary<Partial<GeneralConfig>> = fc.record(
  {
    language: fc.constantFrom('zh-CN', 'en-US') as fc.Arbitrary<'zh-CN' | 'en-US'>,
    theme: fc.constantFrom('light', 'dark', 'system') as fc.Arbitrary<'light' | 'dark' | 'system'>,
    autoStart: fc.boolean(),
    minimizeToTray: fc.boolean(),
    closeToTray: fc.boolean(),
  },
  { requiredKeys: [] }
).filter((obj) => Object.keys(obj).length > 0) // Ensure at least one property

/** Arbitrary for partial HotkeyConfig updates */
const partialHotkeyConfigArb: fc.Arbitrary<Partial<HotkeyConfig>> = fc.record(
  {
    screenshot: fc.constantFrom('Ctrl+Shift+A', 'Ctrl+Shift+S', 'F1', ''),
    workbench: fc.constantFrom('Alt+W', 'Ctrl+Alt+W', 'F6', ''),
    ocr: fc.constantFrom('Ctrl+Shift+O', 'Ctrl+Alt+O', 'F2', ''),
    recording: fc.constantFrom('Ctrl+Shift+R', 'Ctrl+Alt+R', 'F3', ''),
    pin: fc.constantFrom('Ctrl+Shift+P', 'Ctrl+Alt+P', 'F4', ''),
    mouseHighlight: fc.constantFrom('Alt+M', 'Ctrl+M', 'F5', ''),
  },
  { requiredKeys: [] }
).filter((obj) => Object.keys(obj).length > 0)

/** Arbitrary for partial ScreenshotConfig updates */
const partialScreenshotConfigArb: fc.Arbitrary<Partial<ScreenshotConfig>> = fc.record(
  {
    saveLocation: fc.string({ maxLength: 100 }),
    includeMouseCursor: fc.boolean(),
    autoCopy: fc.boolean(),
    autoSave: fc.boolean(),
  },
  { requiredKeys: [] }
).filter((obj) => Object.keys(obj).length > 0)

/** Arbitrary for partial AnnotationConfig updates */
const partialAnnotationConfigArb: fc.Arbitrary<Partial<AnnotationConfig>> = fc.record(
  {
    defaultStrokeColor: fc.constantFrom('#FF0000', '#00FF00', '#0000FF', '#000000', '#FFFFFF'),
    defaultStrokeWidth: fc.integer({ min: 1, max: 20 }),
    defaultFontSize: fc.integer({ min: 8, max: 72 }),
    defaultFontFamily: fc.constantFrom('Microsoft YaHei', 'Arial', 'SimSun'),
    defaultMosaicSize: fc.integer({ min: 5, max: 50 }),
  },
  { requiredKeys: [] }
).filter((obj) => Object.keys(obj).length > 0)

/** Arbitrary for partial OcrConfig updates */
const partialOcrConfigArb: fc.Arbitrary<Partial<OcrConfig>> = fc.record(
  {
    engine: fc.constantFrom('local', 'baiduAccurate'),
    defaultLanguage: fc.constantFrom('auto', 'zh', 'en', 'ja', 'ko'),
    autoTranslate: fc.boolean(),
    translateProvider: fc.constantFrom('google', 'deepl', 'baidu') as fc.Arbitrary<'google' | 'deepl' | 'baidu'>,
    translateTargetLang: fc.constantFrom('zh', 'en', 'ja', 'ko'),
    baiduApiKey: fc.string({ maxLength: 80 }),
    baiduSecretKey: fc.string({ maxLength: 100 }),
    baiduDetectDirection: fc.boolean(),
    baiduProbability: fc.boolean(),
  },
  { requiredKeys: [] }
).filter((obj) => Object.keys(obj).length > 0)

/** Arbitrary for partial RecordingConfig updates */
const partialRecordingConfigArb: fc.Arbitrary<Partial<RecordingConfig>> = fc.record(
  {
    defaultFps: fc.constantFrom(15, 24, 30, 60),
    systemAudio: fc.boolean(),
    micAudio: fc.boolean(),
    outputDir: fc.string({ maxLength: 100 }),
  },
  { requiredKeys: [] }
).filter((obj) => Object.keys(obj).length > 0)

/** Arbitrary for partial PinImageConfig updates */
const partialPinImageConfigArb: fc.Arbitrary<Partial<PinImageConfig>> = fc.record(
  {
    defaultOpacity: fc.double({ min: 0.1, max: 1.0, noNaN: true }),
    mouseThrough: fc.boolean(),
    rememberPosition: fc.boolean(),
  },
  { requiredKeys: [] }
).filter((obj) => Object.keys(obj).length > 0)

/** Arbitrary for partial MouseHighlightConfig updates */
const partialMouseHighlightConfigArb: fc.Arbitrary<Partial<MouseHighlightConfig>> = fc.record(
  {
    enabled: fc.boolean(),
    restoreOnStartup: fc.boolean(),
    circleEnabled: fc.boolean(),
    spotlightEnabled: fc.boolean(),
    cursorMagnifyEnabled: fc.boolean(),
    clickEffectEnabled: fc.boolean(),
    theme: fc.constantFrom('classic_yellow', 'business_blue', 'vibrant_red', 'fresh_green') as fc.Arbitrary<MouseHighlightConfig['theme']>,
    circleRadius: fc.integer({ min: 10, max: 100 }),
    circleThickness: fc.integer({ min: 1, max: 10 }),
    spotlightRadius: fc.integer({ min: 50, max: 500 }),
    spotlightDarkness: fc.integer({ min: 0, max: 100 }),
    cursorScale: fc.double({ min: 1.0, max: 5.0, noNaN: true }),
    rippleDuration: fc.integer({ min: 100, max: 2000 }),
  },
  { requiredKeys: [] }
).filter((obj) => Object.keys(obj).length > 0)

/** Arbitrary for partial WebToMarkdownConfig updates */
const partialWebToMarkdownConfigArb: fc.Arbitrary<Partial<WebToMarkdownConfig>> = fc.record(
  {
    includeImages: fc.boolean(),
    includeLinks: fc.boolean(),
    timeout: fc.integer({ min: 5, max: 120 }),
    saveDir: fc.string({ maxLength: 100 }),
  },
  { requiredKeys: [] }
).filter((obj) => Object.keys(obj).length > 0)

/** Arbitrary for partial FileToMarkdownConfig updates */
const partialFileToMarkdownConfigArb: fc.Arbitrary<Partial<FileToMarkdownConfig>> = fc.record(
  {
    apiToken: fc.string({ maxLength: 100 }),
    modelVersion: fc.constantFrom('pipeline', 'vlm') as fc.Arbitrary<'pipeline' | 'vlm'>,
    saveDir: fc.string({ maxLength: 100 }),
  },
  { requiredKeys: [] }
).filter((obj) => Object.keys(obj).length > 0)

/** Arbitrary for partial NotificationConfig updates */
const partialNotificationConfigArb: fc.Arbitrary<Partial<NotificationConfig>> = fc.record(
  {
    startup: fc.boolean(),
    screenshotSave: fc.boolean(),
    pinImage: fc.boolean(),
    recordingComplete: fc.boolean(),
    softwareUpdate: fc.boolean(),
  },
  { requiredKeys: [] }
).filter((obj) => Object.keys(obj).length > 0)

/** Arbitrary for partial UpdateConfig updates */
const partialUpdateConfigArb: fc.Arbitrary<Partial<UpdateConfig>> = fc.record(
  {
    autoCheck: fc.boolean(),
    lastCheckTime: fc.constantFrom('', '2025-01-01T00:00:00.000Z'),
    skipVersion: fc.constantFrom('', '1.0.0', '2.0.0'),
  },
  { requiredKeys: [] }
).filter((obj) => Object.keys(obj).length > 0)

/** Arbitrary for partial AdvancedConfig updates */
const partialAdvancedConfigArb: fc.Arbitrary<Partial<AdvancedConfig>> = fc.record(
  {
    proxyEnabled: fc.boolean(),
    proxyType: fc.constantFrom('http', 'socks5') as fc.Arbitrary<'http' | 'socks5'>,
    proxyHost: fc.constantFrom('', '127.0.0.1', 'localhost'),
    proxyPort: fc.integer({ min: 1, max: 65535 }),
    debugLogging: fc.boolean(),
    debugLogPath: fc.string({ maxLength: 100 }),
    portableMode: fc.boolean(),
  },
  { requiredKeys: [] }
).filter((obj) => Object.keys(obj).length > 0)

// ============================================================================
// Property Tests
// ============================================================================

describe('Feature: settings-enhancement, Property 14: Dirty Flag on Change', () => {
  beforeEach(() => {
    // Create a fresh Pinia instance before each test
    setActivePinia(createPinia())
  })

  /**
   * Property 14: Dirty Flag on Change
   *
   * For any setting value change, the isDirty flag SHALL be set to true.
   *
   * **Validates: Requirements 11.1**
   */

  it('should set isDirty to true when updateGeneral is called with any partial update', () => {
    fc.assert(
      fc.property(partialGeneralConfigArb, (updates) => {
        const store = useSettingsStore()
        store.isDirty = false // Reset dirty flag

        store.updateGeneral(updates)

        expect(store.isDirty).toBe(true)
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should set isDirty to true when updateScreenshot is called with any partial update', () => {
    fc.assert(
      fc.property(partialScreenshotConfigArb, (updates) => {
        const store = useSettingsStore()
        store.isDirty = false

        store.updateScreenshot(updates)

        expect(store.isDirty).toBe(true)
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should set isDirty to true when updateAnnotation is called with any partial update', () => {
    fc.assert(
      fc.property(partialAnnotationConfigArb, (updates) => {
        const store = useSettingsStore()
        store.isDirty = false

        store.updateAnnotation(updates)

        expect(store.isDirty).toBe(true)
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should set isDirty to true when updateOcr is called with any partial update', () => {
    fc.assert(
      fc.property(partialOcrConfigArb, (updates) => {
        const store = useSettingsStore()
        store.isDirty = false

        store.updateOcr(updates)

        expect(store.isDirty).toBe(true)
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should set isDirty to true when updateRecording is called with any partial update', () => {
    fc.assert(
      fc.property(partialRecordingConfigArb, (updates) => {
        const store = useSettingsStore()
        store.isDirty = false

        store.updateRecording(updates)

        expect(store.isDirty).toBe(true)
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should set isDirty to true when updatePinImage is called with any partial update', () => {
    fc.assert(
      fc.property(partialPinImageConfigArb, (updates) => {
        const store = useSettingsStore()
        store.isDirty = false

        store.updatePinImage(updates)

        expect(store.isDirty).toBe(true)
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should set isDirty to true when updateMouseHighlight is called with any partial update', () => {
    fc.assert(
      fc.property(partialMouseHighlightConfigArb, (updates) => {
        const store = useSettingsStore()
        store.isDirty = false

        store.updateMouseHighlight(updates)

        expect(store.isDirty).toBe(true)
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should set isDirty to true when updateWebToMarkdown is called with any partial update', () => {
    fc.assert(
      fc.property(partialWebToMarkdownConfigArb, (updates) => {
        const store = useSettingsStore()
        store.isDirty = false

        store.updateWebToMarkdown(updates)

        expect(store.isDirty).toBe(true)
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should set isDirty to true when updateFileToMarkdown is called with any partial update', () => {
    fc.assert(
      fc.property(partialFileToMarkdownConfigArb, (updates) => {
        const store = useSettingsStore()
        store.isDirty = false

        store.updateFileToMarkdown(updates)

        expect(store.isDirty).toBe(true)
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should set isDirty to true when updateNotification is called with any partial update', () => {
    fc.assert(
      fc.property(partialNotificationConfigArb, (updates) => {
        const store = useSettingsStore()
        store.isDirty = false

        store.updateNotification(updates)

        expect(store.isDirty).toBe(true)
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should set isDirty to true when updateUpdate is called with any partial update', () => {
    fc.assert(
      fc.property(partialUpdateConfigArb, (updates) => {
        const store = useSettingsStore()
        store.isDirty = false

        store.updateUpdate(updates)

        expect(store.isDirty).toBe(true)
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should set isDirty to true when updateAdvanced is called with any partial update', () => {
    fc.assert(
      fc.property(partialAdvancedConfigArb, (updates) => {
        const store = useSettingsStore()
        store.isDirty = false

        store.updateAdvanced(updates)

        expect(store.isDirty).toBe(true)
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Test updateHotkeys separately since it's async and involves Tauri invoke
   * We test the synchronous part of the dirty flag behavior
   *
   * Note: updateHotkeys is async and calls Tauri invoke. In test environment
   * without Tauri backend, the invoke will fail. The implementation sets isDirty
   * to true before the invoke call, but does NOT roll it back on failure.
   * This is the expected behavior - the dirty flag indicates "user made changes"
   * even if the backend sync failed.
   */
  it('should set isDirty to true when updateHotkeys is called (async behavior)', async () => {
    // Use asyncProperty for async tests with fast-check
    await fc.assert(
      fc.asyncProperty(partialHotkeyConfigArb, async (updates) => {
        // Create fresh pinia for each iteration
        setActivePinia(createPinia())
        const store = useSettingsStore()
        store.isDirty = false

        // updateHotkeys is async and calls Tauri invoke
        // In test environment without Tauri, it will throw
        try {
          await store.updateHotkeys(updates)
        } catch {
          // Expected to fail in test environment without Tauri backend
        }

        // The store sets isDirty to true before the async invoke call
        // Even if invoke fails, isDirty remains true (not rolled back)
        // This is correct behavior - user made changes, even if sync failed
        return Boolean(store.isDirty)
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Additional property: isDirty should remain true after multiple updates
   */
  it('should keep isDirty true after multiple consecutive updates', () => {
    fc.assert(
      fc.property(
        partialGeneralConfigArb,
        partialScreenshotConfigArb,
        partialPinImageConfigArb,
        (generalUpdates, screenshotUpdates, pinImageUpdates) => {
          const store = useSettingsStore()
          store.isDirty = false

          store.updateGeneral(generalUpdates)
          expect(store.isDirty).toBe(true)

          store.updateScreenshot(screenshotUpdates)
          expect(store.isDirty).toBe(true)

          store.updatePinImage(pinImageUpdates)
          expect(store.isDirty).toBe(true)
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Property: resetToDefault should also set isDirty to true
   */
  it('should set isDirty to true when resetToDefault is called', () => {
    const store = useSettingsStore()
    store.isDirty = false

    store.resetToDefault()

    expect(store.isDirty).toBe(true)
  })

  /**
   * Property: resetSection should also set isDirty to true
   */
  it('should set isDirty to true when resetSection is called for any section', () => {
    const sections: (keyof typeof store.config)[] = [
      'general',
      'hotkeys',
      'screenshot',
      'annotation',
      'ocr',
      'recording',
      'pinImage',
      'mouseHighlight',
      'webToMarkdown',
      'fileToMarkdown',
      'notification',
      'update',
      'advanced',
    ]

    const store = useSettingsStore()

    for (const section of sections) {
      store.isDirty = false
      store.resetSection(section)
      expect(store.isDirty).toBe(true)
    }
  })
})
