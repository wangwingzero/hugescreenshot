/**
 * 语言管理 Composable
 *
 * 提供语言切换功能，与设置 store 集成：
 * - 获取/设置当前语言
 * - 支持的语言列表
 * - 语言切换持久化
 *
 * @validates Requirements 17.6
 */

import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from '@/stores/settings'
import { SUPPORTED_LOCALES, setLocale } from '@/locales'
import type { SupportedLocale } from '@/locales'

/**
 * 语言管理 Composable
 */
export function useLocale() {
  const { locale, t, n, d } = useI18n()
  const settingsStore = useSettingsStore()

  /** 当前语言 */
  const currentLocale = computed<SupportedLocale>({
    get: () => locale.value as SupportedLocale,
    set: (value: SupportedLocale) => {
      setLocale(value)
    },
  })

  /** 支持的语言列表 */
  const supportedLocales = SUPPORTED_LOCALES

  /** 当前语言信息 */
  const currentLocaleInfo = computed(() => {
    return supportedLocales.find((l) => l.code === currentLocale.value)
  })

  /**
   * 切换语言
   */
  function changeLocale(newLocale: SupportedLocale): void {
    setLocale(newLocale)
    // 同步到设置 store
    settingsStore.updateGeneral({ language: newLocale })
  }

  // 监听设置 store 中的语言变化
  watch(
    () => settingsStore.general.language,
    (newLang) => {
      if (newLang && newLang !== currentLocale.value) {
        setLocale(newLang as SupportedLocale)
      }
    },
    { immediate: true }
  )

  return {
    /** 当前语言 */
    currentLocale,
    /** 支持的语言列表 */
    supportedLocales,
    /** 当前语言信息 */
    currentLocaleInfo,
    /** 切换语言 */
    changeLocale,
    /** 翻译函数 */
    t,
    /** 数字格式化 */
    n,
    /** 日期格式化 */
    d,
  }
}
