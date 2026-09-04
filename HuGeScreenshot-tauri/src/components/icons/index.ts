/**
 * Icon Registry for Settings Panel
 *
 * This module exports Lucide icons used in the settings sidebar navigation.
 * Icons are mapped by name for easy dynamic component rendering.
 *
 * Usage:
 *   import { icons, type IconName } from '@/components/icons'
 *   <component :is="icons[item.icon]" class="menu-icon" />
 *
 * @see https://lucide.dev/icons/
 */

import {
  Settings,
  Keyboard,
  Camera,
  Edit,
  Pin,
  Video,
  ScanText,
  BookOpen,
  MousePointer,
  Globe,
  FileText,
  Bell,
  RefreshCw,
  Sliders,
  Info,
} from 'lucide-vue-next'
import type { Component } from 'vue'

/**
 * Icon name type for type-safe icon references
 */
export type IconName =
  | 'settings'
  | 'keyboard'
  | 'camera'
  | 'edit'
  | 'pin'
  | 'video'
  | 'scan-text'
  | 'book-open'
  | 'mouse-pointer'
  | 'globe'
  | 'file-text'
  | 'bell'
  | 'refresh-cw'
  | 'sliders'
  | 'info'

/**
 * Icon registry mapping icon names to Lucide Vue components
 *
 * Icons are organized by settings category:
 * - 基础设置 (Basic): settings, keyboard, camera, edit
 * - 功能设置 (Features): pin, video, scan-text, book-open, mouse-pointer
 * - 文档处理 (Documents): globe, file-text
 * - 系统设置 (System): bell, refresh-cw, sliders, info
 */
export const icons: Record<IconName, Component> = {
  // 基础设置 (Basic Settings)
  'settings': Settings,      // 通用 (General)
  'keyboard': Keyboard,      // 热键 (Hotkeys)
  'camera': Camera,          // 截图 (Screenshot)
  'edit': Edit,              // 标注 (Annotation)

  // 功能设置 (Feature Settings)
  'pin': Pin,                // 贴图 (Pin Image)
  'video': Video,            // 录屏 (Recording)
  'scan-text': ScanText,     // OCR
  'book-open': BookOpen,
  'mouse-pointer': MousePointer, // 鼠标高亮 (Mouse Highlight)

  // 文档处理 (Document Processing)
  'globe': Globe,            // 网页转MD (Web to Markdown)
  'file-text': FileText,     // 文件转MD (File to Markdown)

  // 系统设置 (System Settings)
  'bell': Bell,              // 通知 (Notification)
  'refresh-cw': RefreshCw,   // 更新 (Update)
  'sliders': Sliders,        // 高级 (Advanced)
  'info': Info,              // 关于 (About)
}

/**
 * Get all available icon names
 */
export const iconNames = Object.keys(icons) as IconName[]

/**
 * Check if a string is a valid icon name
 */
export function isValidIconName(name: string): name is IconName {
  return name in icons
}

// Re-export individual icons for direct import if needed
export {
  Settings,
  Keyboard,
  Camera,
  Edit,
  Pin,
  Video,
  ScanText,
  BookOpen,
  MousePointer,
  Globe,
  FileText,
  Bell,
  RefreshCw,
  Sliders,
  Info,
}
