/**
 * 录制控制面板入口
 *
 * 独立窗口，录制中显示在屏幕上方。
 * 包含录制状态指示器、时间显示、暂停/停止按钮。
 */
import { createApp } from 'vue'
import RecordingControlApp from './RecordingControlApp.vue'
import './styles/theme.css'

const app = createApp(RecordingControlApp)
app.mount('#app')
