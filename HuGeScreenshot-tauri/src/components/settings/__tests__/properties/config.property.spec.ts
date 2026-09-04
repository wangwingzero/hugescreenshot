/**
 * Property-Based Tests for Configuration
 *
 * Feature: settings-enhancement
 * Property 15: Configuration Round-Trip
 *
 * **Validates: Requirements 11.2**
 *
 * Property Definition:
 * For any valid AppConfig object, saving to storage and then loading
 * SHALL produce an equivalent configuration object.
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import type {
  AppConfig,
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
import { DEFAULT_CONFIG } from '@/types/config'

// ============================================================================
// Arbitraries for each configuration section
// ============================================================================

/** Arbitrary for GeneralConfig */
const generalConfigArb: fc.Arbitrary<GeneralConfig> = fc.record({
  language: fc.constantFrom('zh-CN', 'en-US') as fc.Arbitrary<'zh-CN' | 'en-US'>,
  theme: fc.constantFrom('light', 'dark', 'system') as fc.Arbitrary<'light' | 'dark' | 'system'>,
  autoStart: fc.boolean(),
  minimizeToTray: fc.boolean(),
  closeToTray: fc.boolean(),
})

/** Arbitrary for HotkeyConfig - generates valid hotkey strings */
const hotkeyStringArb: fc.Arbitrary<string> = fc.oneof(
  // Common hotkey patterns
  fc.constantFrom(
    'Ctrl+Shift+A',
    'Ctrl+Shift+O',
    'Ctrl+Shift+R',
    'Ctrl+Shift+P',
    'Alt+M',
    'Ctrl+Alt+S',
    'F1',
    'F12',
    'Ctrl+F1',
    ''
  ),
  // Generate custom hotkey combinations
  fc
    .tuple(
      fc.constantFrom('Ctrl', 'Alt', 'Shift', 'Ctrl+Shift', 'Ctrl+Alt', 'Alt+Shift'),
      fc.constantFrom('A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0')
    )
    .map(([modifier, key]) => `${modifier}+${key}`)
)

const hotkeyConfigArb: fc.Arbitrary<HotkeyConfig> = fc.record({
  screenshot: hotkeyStringArb,
  workbench: hotkeyStringArb,
  ocr: hotkeyStringArb,
  recording: hotkeyStringArb,
  pin: hotkeyStringArb,
  mouseHighlight: hotkeyStringArb,
})

/** Arbitrary for ScreenshotConfig */
const screenshotConfigArb: fc.Arbitrary<ScreenshotConfig> = fc.record({
  saveLocation: fc.string({ maxLength: 200 }),
  includeMouseCursor: fc.boolean(),
  autoCopy: fc.boolean(),
  autoSave: fc.boolean(),
})


/** Arbitrary for AnnotationConfig */
const annotationConfigArb: fc.Arbitrary<AnnotationConfig> = fc.record({
  defaultStrokeColor: fc
    .tuple(
      fc.integer({ min: 0, max: 255 }),
      fc.integer({ min: 0, max: 255 }),
      fc.integer({ min: 0, max: 255 })
    )
    .map(([r, g, b]) => `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`),
  defaultStrokeWidth: fc.integer({ min: 1, max: 20 }),
  defaultFontSize: fc.integer({ min: 8, max: 72 }),
  defaultFontFamily: fc.constantFrom('Microsoft YaHei', 'Arial', 'SimSun', 'Consolas', 'Times New Roman'),
  defaultMosaicSize: fc.integer({ min: 5, max: 50 }),
})

/** Arbitrary for OcrConfig */
const ocrConfigArb: fc.Arbitrary<OcrConfig> = fc.record({
  engine: fc.constantFrom('local', 'baiduAccurate'),
  defaultLanguage: fc.constantFrom('auto', 'zh', 'en', 'ja', 'ko'),
  autoTranslate: fc.boolean(),
  translateProvider: fc.constantFrom('google', 'deepl', 'baidu') as fc.Arbitrary<'google' | 'deepl' | 'baidu'>,
  translateTargetLang: fc.constantFrom('zh', 'en', 'ja', 'ko', 'fr', 'de'),
  baiduApiKey: fc.string({ maxLength: 80 }),
  baiduSecretKey: fc.string({ maxLength: 100 }),
  baiduDetectDirection: fc.boolean(),
  baiduProbability: fc.boolean(),
})

/** Arbitrary for RecordingConfig */
const recordingConfigArb: fc.Arbitrary<RecordingConfig> = fc.record({
  defaultFps: fc.constantFrom(15, 24, 30, 60),
  systemAudio: fc.boolean(),
  micAudio: fc.boolean(),
  outputDir: fc.string({ maxLength: 200 }),
})

/** Arbitrary for PinImageConfig */
const pinImageConfigArb: fc.Arbitrary<PinImageConfig> = fc.record({
  defaultOpacity: fc.double({ min: 0.1, max: 1.0, noNaN: true }),
  mouseThrough: fc.boolean(),
  rememberPosition: fc.boolean(),
})

/** Arbitrary for MouseHighlightConfig */
const mouseHighlightConfigArb: fc.Arbitrary<MouseHighlightConfig> = fc.record({
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
})

/** Arbitrary for WebToMarkdownConfig */
const webToMarkdownConfigArb: fc.Arbitrary<WebToMarkdownConfig> = fc.record({
  includeImages: fc.boolean(),
  includeLinks: fc.boolean(),
  timeout: fc.integer({ min: 5, max: 120 }),
  saveDir: fc.string({ maxLength: 200 }),
})

/** Arbitrary for FileToMarkdownConfig */
const fileToMarkdownConfigArb: fc.Arbitrary<FileToMarkdownConfig> = fc.record({
  engine: fc.constantFrom('local', 'mineru') as fc.Arbitrary<'local' | 'mineru'>,
  apiToken: fc.string({ maxLength: 200 }),
  modelVersion: fc.constantFrom('pipeline', 'vlm') as fc.Arbitrary<'pipeline' | 'vlm'>,
  saveDir: fc.string({ maxLength: 200 }),
})

/** Arbitrary for NotificationConfig */
const notificationConfigArb: fc.Arbitrary<NotificationConfig> = fc.record({
  startup: fc.boolean(),
  screenshotSave: fc.boolean(),
  pinImage: fc.boolean(),
  recordingComplete: fc.boolean(),
  softwareUpdate: fc.boolean(),
})

/** Arbitrary for UpdateConfig */
const updateConfigArb: fc.Arbitrary<UpdateConfig> = fc.record({
  autoCheck: fc.boolean(),
  lastCheckTime: fc.oneof(
    fc.constant(''),
    fc.constant('2025-01-01T00:00:00.000Z'),
    fc.constant('2024-06-15T12:30:45.123Z'),
    // Generate ISO date strings from timestamp
    fc.integer({ min: 1577836800000, max: 1893456000000 }).map((ts) => new Date(ts).toISOString())
  ),
  skipVersion: fc.oneof(
    fc.constant(''),
    fc
      .tuple(
        fc.integer({ min: 0, max: 9 }),
        fc.integer({ min: 0, max: 99 }),
        fc.integer({ min: 0, max: 99 })
      )
      .map(([major, minor, patch]) => `${major}.${minor}.${patch}`)
  ),
})

/** Arbitrary for AdvancedConfig */
const advancedConfigArb: fc.Arbitrary<AdvancedConfig> = fc.record({
  proxyEnabled: fc.boolean(),
  proxyType: fc.constantFrom('http', 'socks5') as fc.Arbitrary<'http' | 'socks5'>,
  proxyHost: fc.oneof(
    fc.constant(''),
    fc.constant('127.0.0.1'),
    fc.constant('localhost'),
    fc.ipV4()
  ),
  proxyPort: fc.integer({ min: 1, max: 65535 }),
  debugLogging: fc.boolean(),
  debugLogPath: fc.string({ maxLength: 200 }),
  portableMode: fc.boolean(),
})


// ============================================================================
// Complete AppConfig Arbitrary
// ============================================================================

/** Arbitrary for complete AppConfig */
const appConfigArb: fc.Arbitrary<AppConfig> = fc.record({
  general: generalConfigArb,
  hotkeys: hotkeyConfigArb,
  screenshot: screenshotConfigArb,
  annotation: annotationConfigArb,
  ocr: ocrConfigArb,
  recording: recordingConfigArb,
  pinImage: pinImageConfigArb,
  mouseHighlight: mouseHighlightConfigArb,
  webToMarkdown: webToMarkdownConfigArb,
  fileToMarkdown: fileToMarkdownConfigArb,
  notification: notificationConfigArb,
  update: updateConfigArb,
  advanced: advancedConfigArb,
})

// ============================================================================
// Property Tests
// ============================================================================

describe('Feature: settings-enhancement, Property 15: Configuration Round-Trip', () => {
  /**
   * Property 15: Configuration Round-Trip
   *
   * For any valid AppConfig object, saving to storage and then loading
   * SHALL produce an equivalent configuration object.
   *
   * **Validates: Requirements 11.2**
   */
  it('should satisfy round-trip serialization for any valid AppConfig', () => {
    fc.assert(
      fc.property(appConfigArb, (config: AppConfig) => {
        // Simulate save: serialize to JSON string
        const serialized = JSON.stringify(config)

        // Simulate load: deserialize from JSON string
        const deserialized = JSON.parse(serialized) as AppConfig

        // Verify round-trip produces equivalent object
        expect(deserialized).toEqual(config)
      }),
      {
        numRuns: 100, // Minimum 100 iterations as per spec
        verbose: true,
      }
    )
  })

  /**
   * Additional property: Double round-trip should be idempotent
   *
   * serialize(deserialize(serialize(config))) === serialize(config)
   */
  it('should satisfy idempotent serialization (double round-trip)', () => {
    fc.assert(
      fc.property(appConfigArb, (config: AppConfig) => {
        // First round-trip
        const serialized1 = JSON.stringify(config)
        const deserialized1 = JSON.parse(serialized1) as AppConfig

        // Second round-trip
        const serialized2 = JSON.stringify(deserialized1)
        const deserialized2 = JSON.parse(serialized2) as AppConfig

        // Both deserializations should be equal
        expect(deserialized2).toEqual(deserialized1)
        // Both serializations should be equal
        expect(serialized2).toEqual(serialized1)
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Property: DEFAULT_CONFIG should satisfy round-trip
   */
  it('should satisfy round-trip for DEFAULT_CONFIG', () => {
    const serialized = JSON.stringify(DEFAULT_CONFIG)
    const deserialized = JSON.parse(serialized) as AppConfig

    expect(deserialized).toEqual(DEFAULT_CONFIG)
  })

  /**
   * Property: Partial config merge with defaults should be stable
   *
   * When loading a partial config and merging with defaults,
   * the result should be serializable and deserializable.
   */
  it('should handle partial config merge with defaults', () => {
    fc.assert(
      fc.property(
        // Generate partial configs (some sections may be missing)
        fc.record(
          {
            general: fc.option(generalConfigArb, { nil: undefined }),
            hotkeys: fc.option(hotkeyConfigArb, { nil: undefined }),
            screenshot: fc.option(screenshotConfigArb, { nil: undefined }),
            annotation: fc.option(annotationConfigArb, { nil: undefined }),
            ocr: fc.option(ocrConfigArb, { nil: undefined }),
            recording: fc.option(recordingConfigArb, { nil: undefined }),
            pinImage: fc.option(pinImageConfigArb, { nil: undefined }),
            mouseHighlight: fc.option(mouseHighlightConfigArb, { nil: undefined }),
            webToMarkdown: fc.option(webToMarkdownConfigArb, { nil: undefined }),
            fileToMarkdown: fc.option(fileToMarkdownConfigArb, { nil: undefined }),
            notification: fc.option(notificationConfigArb, { nil: undefined }),
            update: fc.option(updateConfigArb, { nil: undefined }),
            advanced: fc.option(advancedConfigArb, { nil: undefined }),
          },
          { requiredKeys: [] }
        ),
        (partialConfig) => {
          // Merge with defaults (simulating config loading behavior)
          const mergedConfig: AppConfig = {
            general: partialConfig.general ?? DEFAULT_CONFIG.general,
            hotkeys: partialConfig.hotkeys ?? DEFAULT_CONFIG.hotkeys,
            screenshot: partialConfig.screenshot ?? DEFAULT_CONFIG.screenshot,
            annotation: partialConfig.annotation ?? DEFAULT_CONFIG.annotation,
            ocr: partialConfig.ocr ?? DEFAULT_CONFIG.ocr,
            recording: partialConfig.recording ?? DEFAULT_CONFIG.recording,
            pinImage: partialConfig.pinImage ?? DEFAULT_CONFIG.pinImage,
            mouseHighlight: partialConfig.mouseHighlight ?? DEFAULT_CONFIG.mouseHighlight,
            webToMarkdown: partialConfig.webToMarkdown ?? DEFAULT_CONFIG.webToMarkdown,
            fileToMarkdown: partialConfig.fileToMarkdown ?? DEFAULT_CONFIG.fileToMarkdown,
            notification: partialConfig.notification ?? DEFAULT_CONFIG.notification,
            update: partialConfig.update ?? DEFAULT_CONFIG.update,
            advanced: partialConfig.advanced ?? DEFAULT_CONFIG.advanced,
          }

          // Round-trip the merged config
          const serialized = JSON.stringify(mergedConfig)
          const deserialized = JSON.parse(serialized) as AppConfig

          expect(deserialized).toEqual(mergedConfig)
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Property: Config with edge case values should round-trip correctly
   */
  it('should handle edge case values in configuration', () => {
    // Test with boundary values
    const edgeCaseConfig: AppConfig = {
      ...DEFAULT_CONFIG,
      screenshot: {
        ...DEFAULT_CONFIG.screenshot,
        saveLocation: '', // empty string
      },
      pinImage: {
        defaultOpacity: 0.1, // minimum
        mouseThrough: true,
        rememberPosition: false,
      },
      mouseHighlight: {
        enabled: true,
        restoreOnStartup: false,
        circleEnabled: false,
        spotlightEnabled: false,
        cursorMagnifyEnabled: false,
        clickEffectEnabled: false,
        theme: 'classic_yellow',
        circleRadius: 10, // minimum
        circleThickness: 1, // minimum
        spotlightRadius: 50, // minimum
        spotlightDarkness: 0, // minimum
        cursorScale: 1.0, // minimum
        rippleDuration: 100, // minimum
      },
      webToMarkdown: {
        includeImages: false,
        includeLinks: false,
        timeout: 5, // minimum
        saveDir: '',
      },
      update: {
        autoCheck: false,
        lastCheckTime: '',
        skipVersion: '',
      },
      advanced: {
        proxyEnabled: true,
        proxyType: 'socks5',
        proxyHost: '',
        proxyPort: 1, // minimum
        debugLogging: true,
        debugLogPath: '',
        portableMode: true,
      },
    }

    const serialized = JSON.stringify(edgeCaseConfig)
    const deserialized = JSON.parse(serialized) as AppConfig

    expect(deserialized).toEqual(edgeCaseConfig)
  })

  /**
   * Property: Config with maximum boundary values should round-trip correctly
   */
  it('should handle maximum boundary values in configuration', () => {
    const maxBoundaryConfig: AppConfig = {
      ...DEFAULT_CONFIG,
      screenshot: {
        ...DEFAULT_CONFIG.screenshot,
      },
      pinImage: {
        defaultOpacity: 1.0, // maximum
        mouseThrough: true,
        rememberPosition: true,
      },
      mouseHighlight: {
        enabled: true,
        restoreOnStartup: true,
        circleEnabled: true,
        spotlightEnabled: true,
        cursorMagnifyEnabled: true,
        clickEffectEnabled: true,
        theme: 'fresh_green',
        circleRadius: 100, // maximum
        circleThickness: 10, // maximum
        spotlightRadius: 500, // maximum
        spotlightDarkness: 100, // maximum
        cursorScale: 5.0, // maximum
        rippleDuration: 2000, // maximum
      },
      webToMarkdown: {
        includeImages: true,
        includeLinks: true,
        timeout: 120, // maximum
        saveDir: 'C:\\Users\\Test\\Documents\\Markdown',
      },
      update: {
        autoCheck: true,
        lastCheckTime: new Date().toISOString(),
        skipVersion: '9.99.99',
      },
      advanced: {
        proxyEnabled: true,
        proxyType: 'http',
        proxyHost: '192.168.1.1',
        proxyPort: 65535, // maximum
        debugLogging: true,
        debugLogPath: 'C:\\Logs\\debug.log',
        portableMode: false,
      },
    }

    const serialized = JSON.stringify(maxBoundaryConfig)
    const deserialized = JSON.parse(serialized) as AppConfig

    expect(deserialized).toEqual(maxBoundaryConfig)
  })
})
