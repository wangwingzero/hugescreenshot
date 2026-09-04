/**
 * 图像导出服务
 *
 * 提供图像导出到文件和剪贴板的功能：
 * - 导出为 PNG 文件
 * - 复制到剪贴板
 * - 处理高 DPI 坐标转换
 *
 * @validates Requirements 6.6, 18.4
 * @validates Property 12: Image Export Integrity
 * @validates Property 28: Annotation Coordinate System
 */

import { writeFile, BaseDirectory } from '@tauri-apps/plugin-fs'
import { invoke } from '@tauri-apps/api/core'
import { save } from '@tauri-apps/plugin-dialog'
import type { SelectionRegion } from '@/types'

/** 导出格式（仅 PNG） */
export type ExportFormat = 'png'

/** 导出质量 (0-1) */
export type ExportQuality = number

/** 导出选项 */
export interface ExportOptions {
  /** 导出格式 */
  format: ExportFormat
  /** 质量 (0-1) */
  quality?: ExportQuality
  /** 文件名（不含扩展名） */
  filename?: string
  /** 保存目录 */
  directory?: BaseDirectory
}

/** 导出结果 */
export interface ExportResult {
  /** 是否成功 */
  success: boolean
  /** 文件路径（保存到文件时） */
  path?: string
  /** 错误信息 */
  error?: string
}

/** 默认导出选项 */
const DEFAULT_OPTIONS: ExportOptions = {
  format: 'png',
  quality: 1,
  filename: 'screenshot',
}

/**
 * 生成带时间戳的文件名
 * @param prefix 文件名前缀
 * @returns 带时间戳的文件名
 */
function generateTimestampFilename(prefix: string = 'screenshot'): string {
  const now = new Date()
  const timestamp = now
    .toISOString()
    .replace(/[:.]/g, '-')
    .replace('T', '_')
    .slice(0, 19)
  return `${prefix}_${timestamp}`
}

/**
 * 获取文件扩展名
 */
function getExtension(_format: ExportFormat): string {
  return 'png'
}

/**
 * 获取 MIME 类型
 */
function getMimeType(_format: ExportFormat): string {
  return 'image/png'
}

/**
 * 将 Data URL 转换为 Uint8Array
 * @param dataUrl Data URL 字符串
 * @returns Uint8Array 二进制数据
 */
function dataUrlToUint8Array(dataUrl: string): Uint8Array {
  // 移除 data:image/xxx;base64, 前缀
  const base64 = dataUrl.split(',')[1]
  if (!base64) {
    throw new Error('Invalid data URL format')
  }

  // Base64 解码
  const binaryString = atob(base64)
  const bytes = new Uint8Array(binaryString.length)
  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i)
  }
  return bytes
}

/**
 * 将 Blob 转换为 Uint8Array
 * @param blob Blob 对象
 * @returns Uint8Array 二进制数据
 */
async function blobToUint8Array(blob: Blob): Promise<Uint8Array> {
  const arrayBuffer = await blob.arrayBuffer()
  return new Uint8Array(arrayBuffer)
}

/**
 * 从 Canvas 导出图像数据
 *
 * 处理高 DPI 场景：
 * - Canvas 内部使用物理像素渲染
 * - 导出时保持物理像素分辨率
 *
 * @param canvas Canvas 元素
 * @param format 导出格式
 * @param quality JPEG 质量
 * @returns Blob 对象
 */
export async function exportCanvasToBlob(
  canvas: HTMLCanvasElement,
  format: ExportFormat = 'png',
  quality: ExportQuality = 0.92
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) {
          resolve(blob)
        } else {
          reject(new Error('Failed to export canvas to blob'))
        }
      },
      getMimeType(format),
      quality
    )
  })
}

/**
 * 从 Canvas 导出图像为 Data URL
 *
 * @param canvas Canvas 元素
 * @param format 导出格式
 * @param quality JPEG 质量
 * @returns Data URL 字符串
 */
export function exportCanvasToDataUrl(
  canvas: HTMLCanvasElement,
  format: ExportFormat = 'png',
  quality: ExportQuality = 0.92
): string {
  return canvas.toDataURL(getMimeType(format), quality)
}

/**
 * 保存图像到文件
 *
 * 使用 Tauri 的文件系统 API 保存图像。
 * 支持用户选择保存位置或自动保存到指定目录。
 *
 * @param imageData 图像数据（Blob 或 Uint8Array）
 * @param options 导出选项
 * @returns 导出结果
 *
 * @validates Property 12: Image Export Integrity
 */
export async function saveImageToFile(
  imageData: Blob | Uint8Array,
  options: Partial<ExportOptions> = {}
): Promise<ExportResult> {
  const opts = { ...DEFAULT_OPTIONS, ...options }
  const extension = getExtension(opts.format)
  const filename = opts.filename || generateTimestampFilename()

  try {
    // 显示保存对话框让用户选择位置
    const filePath = await save({
      defaultPath: `${filename}.${extension}`,
      filters: [
        {
          name: 'PNG Image',
          extensions: [extension],
        },
        {
          name: 'All Files',
          extensions: ['*'],
        },
      ],
    })

    if (!filePath) {
      // 用户取消了保存
      return {
        success: false,
        error: 'User cancelled save operation',
      }
    }

    // 转换为 Uint8Array
    const bytes =
      imageData instanceof Blob
        ? await blobToUint8Array(imageData)
        : imageData

    // 写入文件
    await writeFile(filePath, bytes)

    return {
      success: true,
      path: filePath,
    }
  } catch (error) {
    const errorMessage =
      error instanceof Error ? error.message : String(error)
    console.error('Failed to save image:', errorMessage)
    return {
      success: false,
      error: errorMessage,
    }
  }
}

/**
 * 快速保存图像到指定目录（不显示对话框）
 *
 * @param imageData 图像数据
 * @param directory 保存目录
 * @param options 导出选项
 * @returns 导出结果
 */
export async function quickSaveImage(
  imageData: Blob | Uint8Array,
  directory: BaseDirectory,
  options: Partial<ExportOptions> = {}
): Promise<ExportResult> {
  const opts = { ...DEFAULT_OPTIONS, ...options }
  const extension = getExtension(opts.format)
  const filename = opts.filename || generateTimestampFilename()
  const fullFilename = `${filename}.${extension}`

  try {
    // 转换为 Uint8Array
    const bytes =
      imageData instanceof Blob
        ? await blobToUint8Array(imageData)
        : imageData

    // 写入文件
    await writeFile(fullFilename, bytes, { baseDir: directory })

    return {
      success: true,
      path: fullFilename,
    }
  } catch (error) {
    const errorMessage =
      error instanceof Error ? error.message : String(error)
    console.error('Failed to quick save image:', errorMessage)
    return {
      success: false,
      error: errorMessage,
    }
  }
}

/**
 * 复制图像到剪贴板
 *
 * 使用自定义 Rust 命令（arboard 库）复制图像，
 * 绕过 Tauri clipboard-manager 插件在 Windows 上的 PATH_TOO_LONG (os error 206) 问题。
 *
 * @param imageData 图像数据（Blob 或 Uint8Array，必须是 PNG 格式）
 * @returns 导出结果
 *
 * @validates Property 12: Image Export Integrity
 */
export async function copyImageToClipboard(
  imageData: Blob | Uint8Array
): Promise<ExportResult> {
  try {
    // 转换为 Uint8Array
    const bytes =
      imageData instanceof Blob
        ? await blobToUint8Array(imageData)
        : imageData

    // 使用自定义 Rust 命令（arboard）写入剪贴板
    // 传递 PNG 数据，Rust 端会解码并写入剪贴板
    // 直接传递 Uint8Array，Tauri v2 原生支持反序列化为 Vec<u8>，避免 Array.from() 内存翻倍
    await invoke('copy_png_to_clipboard', {
      pngData: bytes,
    })

    return {
      success: true,
    }
  } catch (error) {
    const errorMessage =
      error instanceof Error ? error.message : String(error)
    console.error('Failed to copy image to clipboard:', errorMessage)
    return {
      success: false,
      error: errorMessage,
    }
  }
}

/**
 * 【性能优化】直接从 Canvas 获取 RGBA 数据并复制到剪贴板
 * 
 * 避免 PNG 编解码，直接传递 RGBA 数据给 Rust 端
 * 性能提升：从 ~800ms 降低到 ~100ms
 *
 * @param canvas Canvas 元素
 * @returns 导出结果
 */
export async function copyCanvasRgbaToClipboard(
  canvas: HTMLCanvasElement
): Promise<ExportResult> {
  try {
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      return {
        success: false,
        error: 'Failed to get canvas context',
      }
    }

    const width = canvas.width
    const height = canvas.height
    const imageData = ctx.getImageData(0, 0, width, height)
    // 直接传递 RGBA 数据，避免 PNG 编解码
    // 直接传递 Uint8ClampedArray，Tauri v2 原生支持反序列化为 Vec<u8>，避免 Array.from() 内存翻倍
    await invoke('copy_image_to_clipboard', {
      width,
      height,
      rgbaData: new Uint8Array(imageData.data.buffer),
    })

    return {
      success: true,
    }
  } catch (error) {
    const errorMessage =
      error instanceof Error ? error.message : String(error)
    console.error('Failed to copy canvas RGBA to clipboard:', errorMessage)
    return {
      success: false,
      error: errorMessage,
    }
  }
}

/**
 * 从 Data URL 复制图像到剪贴板
 *
 * @param dataUrl Data URL 字符串
 * @returns 导出结果
 */
export async function copyDataUrlToClipboard(
  dataUrl: string
): Promise<ExportResult> {
  try {
    const bytes = dataUrlToUint8Array(dataUrl)
    return copyImageToClipboard(bytes)
  } catch (error) {
    const errorMessage =
      error instanceof Error ? error.message : String(error)
    console.error('Failed to copy data URL to clipboard:', errorMessage)
    return {
      success: false,
      error: errorMessage,
    }
  }
}

/**
 * 创建合并画布（背景 + 标注）
 *
 * 处理高 DPI 场景：
 * - 输入的 Canvas 已经是物理像素尺寸
 * - 输出保持物理像素尺寸以确保图像质量
 *
 * @param backgroundCanvas 背景画布
 * @param annotationCanvas 标注画布
 * @param region 选区信息（用于裁剪）
 * @param _dpr 设备像素比（保留参数，用于未来扩展）
 * @returns 合并后的 Canvas
 *
 * @validates Property 28: Annotation Coordinate System
 */
export function createMergedCanvas(
  backgroundCanvas: HTMLCanvasElement | null,
  annotationCanvas: HTMLCanvasElement,
  region?: SelectionRegion,
  _dpr: number = 1
): HTMLCanvasElement {
  // 创建输出画布
  const outputCanvas = document.createElement('canvas')

  // 如果有选区，使用物理像素尺寸
  if (region) {
    outputCanvas.width = region.physicalRect.width
    outputCanvas.height = region.physicalRect.height
  } else {
    // 否则使用标注画布的尺寸
    outputCanvas.width = annotationCanvas.width
    outputCanvas.height = annotationCanvas.height
  }

  const ctx = outputCanvas.getContext('2d')
  if (!ctx) {
    throw new Error('Failed to get canvas context')
  }

  // 绘制背景
  if (backgroundCanvas) {
    if (region) {
      // 从背景画布裁剪指定区域
      ctx.drawImage(
        backgroundCanvas,
        region.physicalRect.x,
        region.physicalRect.y,
        region.physicalRect.width,
        region.physicalRect.height,
        0,
        0,
        outputCanvas.width,
        outputCanvas.height
      )
    } else {
      ctx.drawImage(backgroundCanvas, 0, 0)
    }
  }

  // 绘制标注层
  // 标注画布已经包含了 DPR 缩放，直接绘制
  ctx.drawImage(annotationCanvas, 0, 0)

  return outputCanvas
}

/**
 * 导出服务类
 *
 * 提供完整的图像导出功能，包括：
 * - 保存到文件
 * - 复制到剪贴板
 * - 高 DPI 处理
 */
export class ExportService {
  private defaultFormat: ExportFormat = 'png'
  private defaultQuality: ExportQuality = 1

  /**
   * 设置默认导出格式
   */
  setDefaultFormat(format: ExportFormat): void {
    this.defaultFormat = format
  }

  /**
   * 设置默认 JPEG 质量
   */
  setDefaultQuality(quality: ExportQuality): void {
    this.defaultQuality = Math.max(0, Math.min(1, quality))
  }

  /**
   * 从 Canvas 导出并保存到文件
   */
  async saveCanvasToFile(
    canvas: HTMLCanvasElement,
    options?: Partial<ExportOptions>
  ): Promise<ExportResult> {
    const opts = {
      format: this.defaultFormat,
      quality: this.defaultQuality,
      ...options,
    }

    const blob = await exportCanvasToBlob(canvas, opts.format, opts.quality)
    return saveImageToFile(blob, opts)
  }

  /**
   * 从 Canvas 导出并复制到剪贴板
   * 
   * 【性能优化】直接获取 Canvas 的 RGBA 数据，避免 PNG 编解码
   */
  async copyCanvasToClipboard(
    canvas: HTMLCanvasElement
  ): Promise<ExportResult> {
    return copyCanvasRgbaToClipboard(canvas)
  }

  /**
   * 从合并画布导出
   */
  async exportMergedCanvas(
    backgroundCanvas: HTMLCanvasElement | null,
    annotationCanvas: HTMLCanvasElement,
    region?: SelectionRegion,
    dpr: number = 1,
    options?: Partial<ExportOptions>
  ): Promise<{ canvas: HTMLCanvasElement; blob: Blob }> {
    const mergedCanvas = createMergedCanvas(
      backgroundCanvas,
      annotationCanvas,
      region,
      dpr
    )

    const opts = {
      format: this.defaultFormat,
      quality: this.defaultQuality,
      ...options,
    }

    const blob = await exportCanvasToBlob(
      mergedCanvas,
      opts.format,
      opts.quality
    )

    return { canvas: mergedCanvas, blob }
  }
}

// 导出单例实例
export const exportService = new ExportService()
