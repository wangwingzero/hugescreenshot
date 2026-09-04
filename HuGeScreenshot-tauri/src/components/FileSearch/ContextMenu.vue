<template>
  <Teleport to="body">
    <Transition name="context-menu-fade">
      <div
        v-if="visible"
        ref="menuRef"
        class="context-menu"
        :style="menuStyle"
        role="menu"
        @click.stop
        @contextmenu.prevent
      >
        <button
          v-for="item in items"
          :key="item.id"
          class="context-menu-item"
          :class="{ 'is-danger': item.danger }"
          role="menuitem"
          @click="handleItemClick(item)"
        >
          <span class="item-icon">{{ item.icon }}</span>
          <span class="item-label">{{ item.label }}</span>
          <span v-if="item.shortcut" class="item-shortcut">{{ item.shortcut }}</span>
        </button>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
/**
 * 右键菜单组件
 *
 * 通用的右键菜单组件，支持：
 * - 动态定位（根据鼠标位置）
 * - 自动边界检测（防止超出屏幕）
 * - 点击外部自动关闭
 * - 键盘导航（Esc 关闭）
 *
 * @validates Requirements 6.3
 */

import { ref, computed, watch, onUnmounted, nextTick } from 'vue'

// ============================================
// Types
// ============================================

/** 菜单项 */
export interface ContextMenuItem {
  /** 唯一标识 */
  id: string
  /** 显示标签 */
  label: string
  /** 图标（emoji 或字符） */
  icon: string
  /** 快捷键提示 */
  shortcut?: string
  /** 是否为危险操作（红色显示） */
  danger?: boolean
}

// ============================================
// Props & Emits
// ============================================

interface Props {
  /** 是否显示 */
  visible: boolean
  /** 菜单项列表 */
  items: ContextMenuItem[]
  /** 鼠标 X 坐标 */
  x: number
  /** 鼠标 Y 坐标 */
  y: number
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  items: () => [],
  x: 0,
  y: 0,
})

const emit = defineEmits<{
  /** 关闭菜单 */
  (e: 'close'): void
  /** 选择菜单项 */
  (e: 'select', item: ContextMenuItem): void
}>()

// ============================================
// Refs
// ============================================

/** 菜单容器引用 */
const menuRef = ref<HTMLDivElement | null>(null)

/** 调整后的位置 */
const adjustedPosition = ref({ x: 0, y: 0 })

// ============================================
// Computed
// ============================================

/** 菜单样式 */
const menuStyle = computed(() => ({
  left: `${adjustedPosition.value.x}px`,
  top: `${adjustedPosition.value.y}px`,
}))

// ============================================
// Methods
// ============================================

/**
 * 调整菜单位置，防止超出屏幕边界
 */
async function adjustPosition(): Promise<void> {
  await nextTick()

  const menu = menuRef.value
  if (!menu) {
    adjustedPosition.value = { x: props.x, y: props.y }
    return
  }

  const menuRect = menu.getBoundingClientRect()
  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight

  let x = props.x
  let y = props.y

  // 检查右边界
  if (x + menuRect.width > viewportWidth - 8) {
    x = viewportWidth - menuRect.width - 8
  }

  // 检查下边界
  if (y + menuRect.height > viewportHeight - 8) {
    y = viewportHeight - menuRect.height - 8
  }

  // 确保不超出左边界和上边界
  x = Math.max(8, x)
  y = Math.max(8, y)

  adjustedPosition.value = { x, y }
}

/**
 * 处理菜单项点击
 */
function handleItemClick(item: ContextMenuItem): void {
  emit('select', item)
  emit('close')
}

/**
 * 处理点击外部关闭
 */
function handleClickOutside(event: MouseEvent): void {
  if (menuRef.value && !menuRef.value.contains(event.target as Node)) {
    emit('close')
  }
}

/**
 * 处理键盘事件
 */
function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    emit('close')
  }
}

// ============================================
// Watchers
// ============================================

watch(
  () => props.visible,
  (newVisible) => {
    if (newVisible) {
      // 显示时调整位置
      adjustPosition()
      // 添加事件监听
      document.addEventListener('click', handleClickOutside)
      document.addEventListener('keydown', handleKeydown)
    } else {
      // 隐藏时移除事件监听
      document.removeEventListener('click', handleClickOutside)
      document.removeEventListener('keydown', handleKeydown)
    }
  }
)

watch(
  () => [props.x, props.y],
  () => {
    if (props.visible) {
      adjustPosition()
    }
  }
)

// ============================================
// Lifecycle
// ============================================

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.context-menu {
  position: fixed;
  min-width: 160px;
  padding: 4px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  box-shadow: var(--shadow-lg);
  z-index: 10000;
  backdrop-filter: blur(8px);
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: var(--color-text-primary);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.1s ease;
}

.context-menu-item:hover {
  background: var(--color-surface-muted);
}

.context-menu-item:active {
  background: var(--color-surface-strong);
}

.context-menu-item:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: -2px;
}

.context-menu-item.is-danger {
  color: var(--color-error);
}

.context-menu-item.is-danger:hover {
  background: var(--color-error-light);
}

.item-icon {
  flex-shrink: 0;
  width: 18px;
  font-size: 14px;
  text-align: center;
}

.item-label {
  flex: 1;
}

.item-shortcut {
  flex-shrink: 0;
  color: var(--color-text-tertiary);
  font-size: 11px;
}

/* 动画 */
.context-menu-fade-enter-active,
.context-menu-fade-leave-active {
  transition: all 0.1s ease;
}

.context-menu-fade-enter-from,
.context-menu-fade-leave-to {
  opacity: 0;
  transform: scale(0.95);
}
</style>
