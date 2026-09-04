<template>
  <div class="title-bar" data-tauri-drag-region>
    <!-- 标题 -->
    <div class="title-text" data-tauri-drag-region>
      <span>工作台</span>
    </div>

    <!-- 窗口控制按钮 -->
    <div class="window-controls">
      <button
        class="control-btn minimize-btn"
        title="最小化"
        @click="handleMinimize"
      >
        <svg viewBox="0 0 12 12" fill="currentColor">
          <rect x="2" y="5.5" width="8" height="1" />
        </svg>
      </button>
      <button
        class="control-btn maximize-btn"
        title="最大化"
        @click="handleMaximize"
      >
        <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1">
          <rect x="2" y="2" width="8" height="8" />
        </svg>
      </button>
      <button
        class="control-btn close-btn"
        title="关闭"
        @click="handleClose"
      >
        <svg viewBox="0 0 12 12" fill="currentColor">
          <path d="M2.5 2.5L9.5 9.5M9.5 2.5L2.5 9.5" stroke="currentColor" stroke-width="1.2" />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 自定义标题栏组件
 * 
 * 用于替代原生窗口标题栏，实现与内容区域一致的颜色风格
 */

import { getCurrentWindow } from '@tauri-apps/api/window'

const appWindow = getCurrentWindow()

async function handleMinimize(): Promise<void> {
  try {
    await appWindow.minimize()
  } catch (error) {
    console.error('[TitleBar] 最小化窗口失败:', error)
  }
}

async function handleMaximize(): Promise<void> {
  try {
    const isMaximized = await appWindow.isMaximized()
    if (isMaximized) {
      await appWindow.unmaximize()
    } else {
      await appWindow.maximize()
    }
  } catch (error) {
    console.error('[TitleBar] 最大化/还原窗口失败:', error)
  }
}

async function handleClose(): Promise<void> {
  try {
    await appWindow.close()
  } catch (error) {
    console.error('[TitleBar] 关闭窗口失败:', error)
  }
}
</script>

<style scoped>
.title-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 32px;
  padding: 0 8px 0 12px;
  background: var(--color-bg-secondary);
  border-bottom: 1px solid var(--color-border-light);
  user-select: none;
  -webkit-app-region: drag;
}

.title-text {
  display: flex;
  align-items: center;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.window-controls {
  display: flex;
  align-items: center;
  -webkit-app-region: no-drag;
}

.control-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: background-color 0.1s;
}

.control-btn svg {
  width: 12px;
  height: 12px;
}

.control-btn:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.close-btn:hover {
  background: var(--color-error);
  color: var(--color-text-primary);
}
</style>
