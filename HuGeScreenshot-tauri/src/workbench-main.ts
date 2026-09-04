/**
 * 工作台窗口入口
 */
import { createApp, nextTick } from 'vue'
import { createPinia } from 'pinia'
import { getCurrentWebviewWindow } from '@tauri-apps/api/webviewWindow'
import WorkbenchApp from './WorkbenchApp.vue'
import './styles/theme.css'
import { initializeTheme } from './composables/useTheme'

// 在 Vue 挂载前初始化主题，防止白屏闪烁
initializeTheme()

const app = createApp(WorkbenchApp)
app.use(createPinia())
app.mount('#workbench-app')

// 等待 Vue 渲染完成后显示窗口，避免白屏闪烁
// nextTick 确保 DOM 更新完成，requestAnimationFrame 确保浏览器完成绑定
nextTick(() => {
  requestAnimationFrame(async () => {
    const appWindow = getCurrentWebviewWindow()
    await appWindow.show()
    await appWindow.setFocus()
  })
})
