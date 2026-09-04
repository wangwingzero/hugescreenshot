/**
 * 翻译功能组合式函数
 *
 * 直接调用 Rust 原生翻译命令（translate_text_direct），不依赖 Python Sidecar。
 *
 * @validates Requirements 9.1, 9.2
 */

import { ref, computed, ComputedRef } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import type { TranslateResult, TranslateProvider } from '@/types'

export interface UseTranslationOptions {
  /** 默认目标语言 */
  defaultTargetLang?: string
  /** 默认翻译提供商 */
  defaultProvider?: TranslateProvider
}

export interface UseTranslationReturn {
  translationResult: ReturnType<typeof ref<TranslateResult | null>>
  isLoading: ReturnType<typeof ref<boolean>>
  error: ReturnType<typeof ref<string | null>>
  hasResult: ComputedRef<boolean>
  currentProvider: ReturnType<typeof ref<TranslateProvider>>
  currentTargetLang: ReturnType<typeof ref<string>>
  availableProviders: TranslateProvider[]
  availableTargetLangs: { code: string; name: string }[]
  translate: (text: string, targetLang?: string, provider?: TranslateProvider) => Promise<TranslateResult | null>
  clearResult: () => void
  setProvider: (provider: TranslateProvider) => void
  setTargetLang: (lang: string) => void
  getTranslatedText: () => string
}

const AVAILABLE_PROVIDERS: TranslateProvider[] = ['google', 'deepl', 'baidu']

const AVAILABLE_TARGET_LANGS = [
  { code: 'zh', name: '中文' },
  { code: 'en', name: 'English' },
  { code: 'ja', name: '日本語' },
  { code: 'ko', name: '한국어' },
  { code: 'fr', name: 'Français' },
  { code: 'de', name: 'Deutsch' },
  { code: 'es', name: 'Español' },
  { code: 'ru', name: 'Русский' },
]

export function useTranslation(options: UseTranslationOptions = {}): UseTranslationReturn {
  const {
    defaultTargetLang = 'zh',
    defaultProvider = 'google'
  } = options

  const translationResult = ref<TranslateResult | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const currentProvider = ref<TranslateProvider>(defaultProvider)
  const currentTargetLang = ref<string>(defaultTargetLang)

  const hasResult = computed(() =>
    translationResult.value !== null && translationResult.value.translatedText.length > 0
  )

  async function translate(
    text: string,
    targetLang?: string,
    provider?: TranslateProvider
  ): Promise<TranslateResult | null> {
    if (!text || !text.trim()) {
      error.value = '翻译文本不能为空'
      return null
    }

    const finalTargetLang = targetLang ?? currentTargetLang.value
    const finalProvider = provider ?? currentProvider.value

    try {
      isLoading.value = true
      error.value = null

      // 调用 Rust 原生翻译命令（多引擎自动回退）
      // provider 参数仅用于 UI 状态显示，实际引擎由 Rust 端按可用性选择
      const raw = await invoke<{
        translatedText: string
        sourceLang: string
        targetLang: string
        provider: string
      }>('translate_text_direct', {
        text,
        targetLang: finalTargetLang,
      })

      const result: TranslateResult = {
        translatedText: raw.translatedText,
        sourceLang: raw.sourceLang,
        targetLang: raw.targetLang,
        provider: finalProvider,
      }

      translationResult.value = result
      return result
    } catch (e) {
      const errorMessage = e instanceof Error ? e.message : String(e)
      error.value = errorMessage
      console.error('Translation failed:', e)
      return null
    } finally {
      isLoading.value = false
    }
  }

  function clearResult(): void {
    translationResult.value = null
    error.value = null
  }

  function setProvider(provider: TranslateProvider): void {
    currentProvider.value = provider
  }

  function setTargetLang(lang: string): void {
    currentTargetLang.value = lang
  }

  function getTranslatedText(): string {
    return translationResult.value?.translatedText ?? ''
  }

  return {
    translationResult,
    isLoading,
    error,
    hasResult,
    currentProvider,
    currentTargetLang,
    availableProviders: AVAILABLE_PROVIDERS,
    availableTargetLangs: AVAILABLE_TARGET_LANGS,
    translate,
    clearResult,
    setProvider,
    setTargetLang,
    getTranslatedText,
  }
}
