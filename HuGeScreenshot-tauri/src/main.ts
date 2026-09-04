/**
 * 应用主入口
 *
 * 初始化 Vue 应用、Pinia 状态管理和 i18n 国际化
 */

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'

// 导入全局样式
import './styles/theme.css'

// 导入 i18n
import i18n from './locales'

// 导入主题初始化函数
import { initializeTheme } from './composables/useTheme'

// 在 Vue 应用挂载前初始化主题，防止 FOUC
initializeTheme()

// 创建 Pinia 实例
const pinia = createPinia()

// 创建 Vue 应用
const app = createApp(App)

// 使用 Pinia
app.use(pinia)

// 使用 i18n
app.use(i18n)

// 挂载应用
app.mount('#app')
