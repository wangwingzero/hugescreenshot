/**
 * 鼠标高亮 Overlay 入口
 *
 * 功能：
 * - 全屏透明覆盖层
 * - 监听 Rust 发来的鼠标事件
 * - 绘制高亮效果（光圈、聚光灯、点击涟漪等）
 */

import { listen } from '@tauri-apps/api/event'
import { invoke } from '@tauri-apps/api/core'
import { getCurrentWindow } from '@tauri-apps/api/window'

// ============================================
// 常量定义
// ============================================

const HIGHLIGHT_DEFAULT_OPACITY = 0.3
const HIGHLIGHT_FADE_DURATION_MS = 500
const HIGHLIGHT_MIN_SCALE = 0.5
const HIGHLIGHT_MAX_SCALE = 2.0

// ============================================
// 类型定义
// ============================================

interface MousePosition {
  x: number
  y: number
}

interface MouseEvent {
  eventType: 'move' | 'leftDown' | 'leftUp' | 'rightDown' | 'rightUp' | 'middleDown' | 'middleUp'
  position: MousePosition
  timestamp: number
}

interface HighlightConfig {
  enabled: boolean
  effect: 'none' | 'circle' | 'spotlight' | 'magnifier'
  clickEffect: 'none' | 'ripple' | 'flash' | 'ring'
  color: string
  radius: number
  opacity: number
  spotlightDarkness: number
  magnifierZoom: number
  showLeftClick: boolean
  showRightClick: boolean
  leftClickColor: string
  rightClickColor: string
  clickDuration: number
  updateRate: number
}

interface RippleEffect {
  x: number
  y: number
  startTime: number
  duration: number
  color: string
  maxRadius: number
}

// ============================================
// 全局状态
// ============================================

let canvas: HTMLCanvasElement | null = null
let ctx: CanvasRenderingContext2D | null = null

// Tauri 事件取消监听函数
const unlistenFns: (() => void)[] = []

let currentConfig: HighlightConfig = {
  enabled: true,
  effect: 'circle',
  clickEffect: 'ripple',
  color: '#FFD700',
  radius: 40,
  opacity: 0.6,
  spotlightDarkness: HIGHLIGHT_MIN_SCALE,
  magnifierZoom: HIGHLIGHT_MAX_SCALE,
  showLeftClick: true,
  showRightClick: true,
  leftClickColor: '#FFD700',
  rightClickColor: '#FF6B6B',
  clickDuration: HIGHLIGHT_FADE_DURATION_MS,
  updateRate: 60,
}

let mouseX = 0
let mouseY = 0
let activeRipples: RippleEffect[] = []
let animationFrameId: number | null = null
// 窗口偏移（用于多显示器）
let windowOffsetX = 0
let windowOffsetY = 0
// DPI 缩放因子
let scaleFactor = 1

// ============================================
// 初始化
// ============================================

async function initOverlay() {
  console.log('[MouseHighlight] 初始化鼠标高亮 Overlay...')

  const app = document.getElementById('overlay-app')
  if (!app) {
    console.error('[MouseHighlight] 找不到 overlay-app 元素')
    return
  }

  // 获取窗口信息
  try {
    const win = getCurrentWindow()
    scaleFactor = await win.scaleFactor()
    const position = await win.outerPosition()
    windowOffsetX = position.x
    windowOffsetY = position.y
    console.log(`[MouseHighlight] 窗口位置: (${windowOffsetX}, ${windowOffsetY}), 缩放因子: ${scaleFactor}`)
  } catch (e) {
    console.warn('[MouseHighlight] 无法获取窗口信息:', e)
    scaleFactor = window.devicePixelRatio || 1
  }

  // 创建 Canvas
  canvas = document.createElement('canvas')
  canvas.id = 'highlight-canvas'
  canvas.style.position = 'fixed'
  canvas.style.top = '0'
  canvas.style.left = '0'
  canvas.style.width = '100%'
  canvas.style.height = '100%'
  canvas.style.pointerEvents = 'none'
  app.appendChild(canvas)

  ctx = canvas.getContext('2d')
  if (!ctx) {
    console.error('[MouseHighlight] 无法获取 Canvas 上下文')
    return
  }

  // 设置 Canvas 大小
  resizeCanvas()
  window.addEventListener('resize', resizeCanvas)

  // 监听配置更新事件
  const unlistenConfig = await listen<HighlightConfig>('mouse-highlight-config', (event) => {
    console.log('[MouseHighlight] 收到配置更新:', event.payload)
    currentConfig = { ...currentConfig, ...event.payload }
  })
  unlistenFns.push(unlistenConfig)

  // 监听鼠标移动事件
  const unlistenMove = await listen<MouseEvent>('mouse-move', (event) => {
    const { position } = event.payload
    // rdev 返回的是物理像素坐标，需要：
    // 1. 减去窗口偏移（窗口可能不在 (0,0)）
    // 2. 除以缩放因子转换为逻辑坐标
    mouseX = (position.x - windowOffsetX) / scaleFactor
    mouseY = (position.y - windowOffsetY) / scaleFactor
  })
  unlistenFns.push(unlistenMove)

  // 监听鼠标点击事件
  const unlistenClick = await listen<MouseEvent>('mouse-click', (event) => {
    const { eventType, position } = event.payload

    if (currentConfig.clickEffect === 'none') return

    let color = currentConfig.leftClickColor
    if (eventType === 'leftDown' && currentConfig.showLeftClick) {
      color = currentConfig.leftClickColor
    } else if (eventType === 'rightDown' && currentConfig.showRightClick) {
      color = currentConfig.rightClickColor
    } else {
      return
    }

    // 添加涟漪效果
    // 同样需要转换物理坐标到逻辑坐标
    activeRipples.push({
      x: (position.x - windowOffsetX) / scaleFactor,
      y: (position.y - windowOffsetY) / scaleFactor,
      startTime: Date.now(),
      duration: currentConfig.clickDuration,
      color: color,
      maxRadius: currentConfig.radius * 2,
    })
  })
  unlistenFns.push(unlistenClick)

  // 监听窗口显示事件
  const unlistenShow = await listen('show-highlight-overlay', () => {
    console.log('[MouseHighlight] 收到显示事件')
    startAnimation()
  })
  unlistenFns.push(unlistenShow)

  // 监听窗口隐藏事件
  const unlistenHide = await listen('hide-highlight-overlay', () => {
    console.log('[MouseHighlight] 收到隐藏事件')
    stopAnimation()
  })
  unlistenFns.push(unlistenHide)

  // 主动从后端拉取当前配置（解决竞态条件：overlay 创建后 Rust 立即发送配置事件，
  // 但此时 JS 还未加载完毕，事件监听器未注册，导致配置事件丢失，回退到硬编码默认值）
  try {
    const initialConfig = await invoke<HighlightConfig>('get_mouse_highlight_config')
    console.log('[MouseHighlight] 获取初始配置:', initialConfig)
    currentConfig = { ...currentConfig, ...initialConfig }
  } catch (e) {
    console.warn('[MouseHighlight] 获取初始配置失败，使用默认值:', e)
  }

  // 开始动画循环
  startAnimation()

  console.log('[MouseHighlight] 初始化完成')
}

// ============================================
// Canvas 管理
// ============================================

function resizeCanvas() {
  if (!canvas || !ctx) return

  const dpr = window.devicePixelRatio || 1
  const width = window.innerWidth
  const height = window.innerHeight

  // 设置 canvas 的实际像素大小
  canvas.width = width * dpr
  canvas.height = height * dpr

  // 设置 canvas 的 CSS 显示大小
  canvas.style.width = width + 'px'
  canvas.style.height = height + 'px'

  // 重置变换矩阵，然后应用 DPR 缩放
  // 这样我们可以用逻辑坐标绑定，canvas 自动处理 DPR
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

// ============================================
// 动画循环
// ============================================

function startAnimation() {
  if (animationFrameId !== null) return

  function animate() {
    render()
    animationFrameId = requestAnimationFrame(animate)
  }

  animationFrameId = requestAnimationFrame(animate)
}

function stopAnimation() {
  if (animationFrameId !== null) {
    cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }
}

// ============================================
// 渲染
// ============================================

function render() {
  if (!ctx || !canvas) return

  // 清空画布（使用逻辑尺寸，因为 ctx 已经缩放过）
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)

  if (!currentConfig.enabled) return

  // 绘制主效果
  switch (currentConfig.effect) {
    case 'circle':
      drawCircle()
      break
    case 'spotlight':
      drawSpotlight()
      break
    case 'magnifier':
      // 放大镜效果需要截图，暂不实现
      drawCircle() // fallback
      break
  }

  // 绘制点击涟漪
  drawRipples()
}

/**
 * 绘制光圈效果
 */
function drawCircle() {
  if (!ctx) return

  const { color, radius, opacity } = currentConfig

  ctx.save()
  ctx.globalAlpha = opacity

  // 外圈
  ctx.beginPath()
  ctx.arc(mouseX, mouseY, radius, 0, Math.PI * 2)
  ctx.strokeStyle = color
  ctx.lineWidth = 3
  ctx.stroke()

  // 内圈（半透明填充）
  ctx.beginPath()
  ctx.arc(mouseX, mouseY, radius * HIGHLIGHT_DEFAULT_OPACITY, 0, Math.PI * 2)
  ctx.fillStyle = color
  ctx.globalAlpha = opacity * HIGHLIGHT_DEFAULT_OPACITY
  ctx.fill()

  ctx.restore()
}

/**
 * 绘制聚光灯效果
 */
function drawSpotlight() {
  if (!ctx || !canvas) return

  const { radius, spotlightDarkness } = currentConfig
  const width = window.innerWidth
  const height = window.innerHeight

  ctx.save()

  // 创建径向渐变（中心透明，外围暗）
  const gradient = ctx.createRadialGradient(
    mouseX, mouseY, radius * HIGHLIGHT_MIN_SCALE,
    mouseX, mouseY, radius * HIGHLIGHT_MAX_SCALE
  )
  gradient.addColorStop(0, 'rgba(0, 0, 0, 0)')
  gradient.addColorStop(0.5, 'rgba(0, 0, 0, 0)')
  gradient.addColorStop(1, `rgba(0, 0, 0, ${spotlightDarkness})`)

  // 绘制暗色覆盖（使用逻辑尺寸）
  ctx.fillStyle = `rgba(0, 0, 0, ${spotlightDarkness})`
  ctx.fillRect(0, 0, width, height)

  // 用径向渐变"擦除"中心区域
  ctx.globalCompositeOperation = 'destination-out'
  ctx.beginPath()
  ctx.arc(mouseX, mouseY, radius, 0, Math.PI * 2)
  ctx.fill()

  ctx.restore()
}

/**
 * 绘制点击涟漪效果
 */
function drawRipples() {
  if (!ctx) return

  const now = Date.now()
  const stillActive: RippleEffect[] = []

  for (const ripple of activeRipples) {
    const elapsed = now - ripple.startTime
    const progress = elapsed / ripple.duration

    if (progress >= 1) {
      continue // 涟漪已结束
    }

    stillActive.push(ripple)

    const currentRadius = ripple.maxRadius * progress
    const alpha = 1 - progress

    ctx.save()
    ctx.globalAlpha = alpha * 0.6

    // 涟漪圆环
    ctx.beginPath()
    ctx.arc(ripple.x, ripple.y, currentRadius, 0, Math.PI * 2)
    ctx.strokeStyle = ripple.color
    ctx.lineWidth = 3 * (1 - progress * 0.5)
    ctx.stroke()

    // 内部填充（更淡）
    ctx.globalAlpha = alpha * 0.2
    ctx.fillStyle = ripple.color
    ctx.fill()

    ctx.restore()
  }

  activeRipples = stillActive
}

// ============================================
// 清理
// ============================================

/**
 * 清理所有事件监听器和动画
 */
function cleanup() {
  window.removeEventListener('resize', resizeCanvas)
  stopAnimation()

  // 清理 Tauri 事件监听
  unlistenFns.forEach((fn) => fn())
  unlistenFns.length = 0
}

// 页面卸载时清理事件监听
window.addEventListener('beforeunload', cleanup)

// ============================================
// 启动
// ============================================

initOverlay().catch((e) => {
  console.error('[MouseHighlight] 初始化失败:', e)
})
