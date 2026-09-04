/**
 * i18n 国际化配置
 *
 * 配置 vue-i18n 支持中英文切换
 *
 * @validates Requirements 17.6
 */

import { createI18n } from 'vue-i18n'
import type { I18n, Composer, VueI18n } from 'vue-i18n'

// 同步加载主要语言包（中文），英文包按需加载以加速启动
import zhCN from './zh-CN'

// 语言消息（英文包在需要时懒加载）
const messages: Record<string, any> = {
  'zh-CN': zhCN,
}

// 支持的语言列表
export const SUPPORTED_LOCALES = [
  { code: 'zh-CN', name: '中文', nativeName: '简体中文' },
  { code: 'en-US', name: 'English', nativeName: 'English' },
] as const

export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number]['code']

/**
 * 获取浏览器语言
 */
function getBrowserLocale(): SupportedLocale {
  const browserLang = navigator.language

  // 匹配完整语言代码
  if (browserLang in messages) {
    return browserLang as SupportedLocale
  }

  // 匹配语言前缀（如 zh -> zh-CN）
  const langPrefix = browserLang.split('-')[0]
  if (langPrefix === 'zh') {
    return 'zh-CN'
  }
  if (langPrefix === 'en') {
    return 'en-US'
  }

  // 默认中文
  return 'zh-CN'
}

/**
 * 获取存储的语言设置
 */
function getStoredLocale(): SupportedLocale | null {
  const stored = localStorage.getItem('locale')
  if (stored && stored in messages) {
    return stored as SupportedLocale
  }
  return null
}

/**
 * 保存语言设置
 */
export function setStoredLocale(locale: SupportedLocale): void {
  localStorage.setItem('locale', locale)
}

/**
 * 获取初始语言
 */
function getInitialLocale(): SupportedLocale {
  // 优先使用存储的设置
  const stored = getStoredLocale()
  if (stored) {
    return stored
  }

  // 其次使用浏览器语言
  return getBrowserLocale()
}

/**
 * 按需加载语言包
 * 
 * 只有中文包是同步加载的（启动必需），其他语言包按需异步加载。
 * 加载完成后自动注入到 i18n 实例中。
 */
async function loadLocaleMessages(locale: SupportedLocale): Promise<void> {
  if (messages[locale]) return // 已加载

  if (locale === 'en-US') {
    const mod = await import('./en-US')
    messages[locale] = mod.default
    i18n.global.setLocaleMessage(locale, mod.default)
  }
}

// 创建 i18n 实例
const initialLocale = getInitialLocale()
export const i18n: I18n = createI18n({
  legacy: false, // 使用 Composition API 模式
  globalInjection: true, // 全局注入 $t
  locale: initialLocale,
  fallbackLocale: 'zh-CN',
  messages,
  missingWarn: false, // 关闭缺失翻译警告
  fallbackWarn: false, // 关闭回退警告
})

// 如果初始语言不是中文，异步加载对应语言包
if (initialLocale !== 'zh-CN') {
  loadLocaleMessages(initialLocale)
}

/**
 * 切换语言
 */
export async function setLocale(locale: SupportedLocale): Promise<void> {
  // 确保语言包已加载
  await loadLocaleMessages(locale)

  if (i18n.mode === 'legacy') {
    ;(i18n.global as unknown as VueI18n).locale = locale
  } else {
    ;(i18n.global as unknown as Composer).locale.value = locale
  }
  setStoredLocale(locale)

  // 更新 HTML lang 属性
  document.documentElement.setAttribute('lang', locale)
}

/**
 * 获取当前语言
 */
export function getLocale(): SupportedLocale {
  if (i18n.mode === 'legacy') {
    return (i18n.global as unknown as VueI18n).locale as SupportedLocale
  }
  return (i18n.global as unknown as Composer).locale.value as SupportedLocale
}

// 导出默认实例
export default i18n
