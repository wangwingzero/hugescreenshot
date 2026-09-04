/**
 * 录制预览窗口入口
 */
import { createApp } from 'vue'
import RecordingPreviewApp from './RecordingPreviewApp.vue'
import './styles/theme.css'

const app = createApp(RecordingPreviewApp)
app.mount('#app')
