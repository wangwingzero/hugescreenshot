/**
 * OCR 文本操作共享 composable
 *
 * 提供 OCR 文本处理的统一逻辑，被 OCR 结果弹窗和工作台面板共享使用。
 * 包括：
 * - 文本格式化（合并为单行、智能分段、移除空格、标点转换）
 * - 恢复原文
 * - 复制到剪贴板
 * - 翻译
 * - 本地 OCR 重新识别
 * - Markdown 转换
 *
 * 设计原则：
 * - 纯格式化函数可独立使用（applyFormat）
 * - composable 接受外部 Ref，适配不同状态管理模式
 * - 一处修改，两处（OCR 弹窗 + 工作台）同步生效
 */

import { type Ref, computed } from 'vue'
import { writeText } from '@tauri-apps/plugin-clipboard-manager'
import { invoke } from '@tauri-apps/api/core'
import type { OcrEngine } from '@/types'

// ============================================
// Types
// ============================================

/** 文本格式化类型（与 OcrToolbar 保持一致） */
export type FormatType =
  | 'merge-lines'
  | 'smart-paragraphs'
  | 'remove-spaces'
  | 'punct-to-en'
  | 'punct-to-cn'
  | 'clean-symbols'
  | 'strip-line-numbers'
  | 'add-line-numbers'
  | 'remove-cjk-spaces'

/** composable 配置选项 */
export interface OcrTextActionsOptions {
  /** 获取当前图片路径（用于本地 OCR 重新识别） */
  getImagePath?: () => string | null
  /** 外部加载状态 Ref（可选，composable 会在操作期间设置） */
  isLoading?: Ref<boolean>
}

interface OcrCommandResult {
  text: string
  boxes: Array<{ text: string; confidence: number; box_coords?: number[][] }>
  elapse: number
  engine?: string
}

// ============================================
// 纯函数：文本格式化
// ============================================

// ---- 符号噪声过滤常量 ----
// 将 clean-symbols 使用的正则按类别拆分为命名常量，方便维护和扩展。
//
// 注意：Rust 端 OCR 引擎（ocr/engine.rs 的 is_symbol_noise）已在识别阶段过滤
// 1-2 字符的纯符号 region（如 `>`、`{}`）。前端此处是**文本级别的补充清理**，
// 针对多字符行首符号残留和纯符号行，两层过滤互补、不冲突。

/** 箭头类符号（文件夹展开箭头、导航箭头等） */
const ARROWS = '>›»«‹<►▶▸▼▾▲△▻▹'
/** 勾选/叉号类符号（复选框图标） */
const CHECK_MARKS = '☐☑☒✓✗✘×'
/** 几何图形符号（文件/文件夹图标） */
const GEOMETRIC = '⊕⊗⊙■□▪▫◆◇◈'
/** 装饰/特殊符号（星号、项目符号、警告图标等） */
const DECORATIVE = '⬤⬢⬡※☆★⚠⚡♦♣♠♥'
/** 系统/键盘符号（macOS 按键图标等） */
const SYSTEM = '⌂⌘⌥⌃⌤⎋⏎'

/** 所有 UI 噪声符号集合 */
const ALL_NOISE_SYMBOLS = ARROWS + CHECK_MARKS + GEOMETRIC + DECORATIVE + SYSTEM

/**
 * 行首 UI 噪声符号正则：匹配单个噪声符号或成对括号符号（`{}`、`[]`、`()`、`<>`）
 * 捕获组 $1 保留行首缩进
 */
const RE_LINE_START_NOISE = new RegExp(
  `^([ \\t]*)(?:[${ALL_NOISE_SYMBOLS.replace(/[-\\^$*+?.()|[\]{}]/g, '\\$&')}]|\\{\\}|\\[\\]|\\(\\)|<>)[ \\t]*`,
)

/** 行首连续 > 符号（如 `>>` 或 `>>>` + 空格） */
const RE_LINE_START_ARROWS = /^([ \t]*)>{1,3}[ \t]+/

/** 行首孤立的单个标点符号（后面跟空格 + 实际文本内容）
 *  注意：排除 # 以保护 Markdown 标题（如 "# Title"） */
const RE_LINE_START_LONE_PUNCT =
  /^([ \t]*)[·•|^~`$%&@!?][ \t]+(?=[\w\u4e00-\u9fff\u3400-\u4dbf.])/

/** 包含有效文本内容（字母、数字或汉字）的行 */
const RE_HAS_REAL_CONTENT = /[\da-zA-Z\u4e00-\u9fff\u3400-\u4dbf\uF900-\uFAFF]/

// ---- 保护区域正则（用于标点转换）----

/** URL 模式（http/https/ftp） */
const RE_URL = /https?:\/\/[^\s]+|ftp:\/\/[^\s]+/g
/** 邮箱模式 */
const RE_EMAIL = /[\w.+-]+@[\w-]+\.[\w.-]+/g
/** 文件路径模式（Windows 或 Unix） */
const RE_FILE_PATH = /(?:[A-Z]:\\|\.\/|\.\.\/|\/)[^\s]+/gi
/** 代码块模式（反引号包裹） */
const RE_CODE_INLINE = /`[^`]+`/g

/**
 * 保护特殊区域不被标点转换破坏
 *
 * 在标点转换前，将 URL、邮箱、文件路径、代码块等替换为占位符，
 * 转换后再还原，避免误伤。
 */
function protectAndConvert(
  text: string,
  converter: (s: string) => string,
): string {
  const protectedRegions: { placeholder: string; original: string }[] = []
  let idx = 0

  // 收集所有需要保护的区域
  const patterns = [RE_URL, RE_EMAIL, RE_FILE_PATH, RE_CODE_INLINE]
  let result = text
  for (const pattern of patterns) {
    // 重置 lastIndex，确保全局正则从头匹配
    pattern.lastIndex = 0
    result = result.replace(pattern, (match) => {
      const placeholder = `\0PROTECTED_${idx++}\0`
      protectedRegions.push({ placeholder, original: match })
      return placeholder
    })
  }

  // 对非保护区域执行标点转换
  result = converter(result)

  // 还原保护区域
  for (const { placeholder, original } of protectedRegions) {
    result = result.replace(placeholder, original)
  }

  return result
}

/** 行号模式：行首可选空白 + 数字 + 分隔符（.、:、|、空格/tab）
 *  要求至少2行连续递增才视为行号 */
const RE_LINE_NUMBER = /^([ \t]*)(\d+)([.:|]|[ \t])[ \t]*/

/** 中文汉字间的空格（OCR 常见误识别） */
const RE_CJK_SPACE = /([\u4e00-\u9fff\u3400-\u4dbf\uF900-\uFAFF])\s+([\u4e00-\u9fff\u3400-\u4dbf\uF900-\uFAFF])/g

// ---- 智能分段保护规则 ----

/** 列表项模式：-, *, +, 或 1. 2. 开头 */
const RE_LIST_ITEM = /^[ \t]*(?:[-*+]|\d+[.)]) /

/** 表格行模式：包含至少一个 | 分隔符 */
const RE_TABLE_ROW = /\|.*\|/

/** 代码特征模式：常见代码语法元素 */
const RE_CODE_PATTERN = /[{};]$|^[ \t]*[{}]|=>|->|\bif\s*\(|\bfor\s*\(|\bwhile\s*\(|\bfunction\b|\bconst\b|\blet\b|\bvar\b|\breturn\b|\bimport\b|\bexport\b|\bclass\b|\bdef\b|\/\/|\/\*|\*\/|#include|#define/

/** 缩进行（至少2空格或1个Tab开头，且非列表项） */
const RE_INDENTED = /^(?:[ ]{2,}|\t)/

/** Markdown 标题模式：# 开头 */
const RE_MARKDOWN_HEADING = /^#{1,6}\s/

/** 句末终止标点（中英文句号、问号、感叹号、省略号） */
const RE_SENTENCE_END = /[。.！!？?…]$/

/** 判断文本是否以 CJK 字符或 CJK 标点结尾 */
const RE_CJK_TAIL = /[\u4e00-\u9fff\u3400-\u4dbf\uF900-\uFAFF，。！？；：、''""）】》]$/

/** 判断文本是否以 CJK 字符或 CJK 标点开头 */
const RE_CJK_HEAD = /^[\u4e00-\u9fff\u3400-\u4dbf\uF900-\uFAFF（【《]/

/**
 * 判断一行是否是"结构化行"——不应被智能合并
 *
 * 包括：列表项、表格行、含代码特征的行、缩进代码块、Markdown 标题
 */
function isStructuredLine(line: string): boolean {
  return (
    RE_LIST_ITEM.test(line) ||
    RE_TABLE_ROW.test(line) ||
    RE_CODE_PATTERN.test(line) ||
    RE_INDENTED.test(line) ||
    RE_MARKDOWN_HEADING.test(line)
  )
}

/**
 * 判断一行是否像标题/短标题行——不应被合并到前一段
 *
 * 仅在有**强信号**时才判定为标题，避免误判 OCR 断行：
 * - 中文编号标题：一、二、(一)、第X章/节/部分
 * - 数字章节标题：1.1、2.3.1 等独立编号（不含后续内容或只跟标题文字）
 * - 全大写英文行：如 "INTRODUCTION"、"CONCLUSION"
 */
function isTitleLikeLine(line: string): boolean {
  const trimmed = line.trim()
  if (trimmed.length === 0) return false

  // 中文编号标题：一、二、...；（一）、（二）、...；第X章/节/部分
  if (/^[一二三四五六七八九十]+[、.]/.test(trimmed)) return true
  if (/^（[一二三四五六七八九十\d]+）/.test(trimmed)) return true
  if (/^第[一二三四五六七八九十百千\d]+[章节篇条款]/.test(trimmed)) return true
  if (/^第[一二三四五六七八九十百千\d]+部分/.test(trimmed)) return true

  // 独立数字编号行：1.1、2.3.1 等，后面只跟短标题文字（不超过20字）
  if (/^\d+(\.\d+)+\s?.{0,20}$/.test(trimmed)) return true

  // 全大写英文行（至少2个单词，总长度不超过60），常见于标题
  if (/^[A-Z][A-Z\s]{2,60}$/.test(trimmed) && /\s/.test(trimmed)) return true

  return false
}

/**
 * 对文本应用格式化（纯函数，无副作用）
 *
 * 被 composable 和 workbenchStore 共享调用。
 *
 * @param text 原始文本
 * @param type 格式化类型
 * @returns 格式化后的文本
 */
export function applyFormat(text: string, type: FormatType): string {
  let formatted = text

  switch (type) {
    case 'merge-lines':
      // 合并为单行：移除所有换行符
      formatted = formatted.replace(/\r?\n/g, '')
      break

    case 'smart-paragraphs': {
      // 智能分段：连续换行保留，单个换行合并
      // 保护：代码块、列表项、表格行、Markdown 标题不合并
      // 优化：
      //   1) 句末标点检测——以句号/问号/感叹号结尾的行视为段落结束
      //   2) 标题/短行检测——短行不合并到前段，独立保留
      //   3) 中英混合边界——CJK 间不加空格，中英文间加空格
      //   4) Markdown 标题保护——# 开头行不合并
      //   5) 多余空行压缩——连续空行合并为单个段落分隔
      formatted = formatted.replace(/\r\n/g, '\n')

      const lines = formatted.split('\n')
      const result: string[] = []
      let buffer = ''
      let consecutiveEmptyLines = 0

      for (let i = 0; i < lines.length; i++) {
        const line = lines[i]

        // 空行 → 段落分隔符（连续空行压缩为一个）
        if (line.trim() === '') {
          if (buffer) {
            result.push(buffer)
            buffer = ''
          }
          consecutiveEmptyLines++
          if (consecutiveEmptyLines <= 1) {
            result.push('')
          }
          continue
        }
        consecutiveEmptyLines = 0

        // 结构化行（代码/列表/表格/Markdown标题）→ 不合并，独立保留
        if (isStructuredLine(line)) {
          if (buffer) {
            result.push(buffer)
            buffer = ''
          }
          result.push(line)
          continue
        }

        // 标题/短行检测：如果当前行像标题且 buffer 不以连接标点结尾，
        // 先输出 buffer，再独立输出标题行（不作为缓冲区，避免后续行合并进来）
        const bufferEndsContinuation = /[,，;；:：]$/.test(buffer.trim())
        if (buffer && !bufferEndsContinuation && isTitleLikeLine(line)) {
          result.push(buffer)
          buffer = ''
          result.push(line)
          continue
        }

        // 普通文本行 → 合并到 buffer
        if (!buffer) {
          buffer = line
        } else {
          // CJK 智能拼接
          const isCjkBefore = RE_CJK_TAIL.test(buffer)
          const isCjkAfter = RE_CJK_HEAD.test(line)
          if (isCjkBefore && isCjkAfter) {
            buffer += line
          } else {
            buffer += ' ' + line
          }
        }

        // 句末标点检测：如果 buffer 以句末终止标点结尾，视为段落结束
        if (RE_SENTENCE_END.test(buffer.trim())) {
          result.push(buffer)
          buffer = ''
        }
      }
      if (buffer) {
        result.push(buffer)
      }

      formatted = result.join('\n')
      break
    }

    case 'remove-spaces':
      // 移除多余空格
      formatted = formatted.replace(/[ \t]+/g, ' ').trim()
      break

    case 'punct-to-en':
      // 中文标点转英文（保护 URL/邮箱/代码块不被误转换）
      formatted = protectAndConvert(formatted, (s) =>
        s
          .replace(/，/g, ',')
          .replace(/。/g, '.')
          .replace(/！/g, '!')
          .replace(/？/g, '?')
          .replace(/：/g, ':')
          .replace(/；/g, ';')
          .replace(/（/g, '(')
          .replace(/）/g, ')')
          .replace(/【/g, '[')
          .replace(/】/g, ']')
          .replace(/\u201c/g, '"')
          .replace(/\u201d/g, '"')
          .replace(/\u2018/g, "'")
          .replace(/\u2019/g, "'")
      )
      break

    case 'punct-to-cn':
      // 英文标点转中文（保护 URL/邮箱/代码块不被误转换）
      formatted = protectAndConvert(formatted, (s) =>
        s
          .replace(/,/g, '，')
          .replace(/\./g, '。')
          .replace(/!/g, '！')
          .replace(/\?/g, '？')
          .replace(/:/g, '：')
          .replace(/;/g, '；')
          .replace(/\(/g, '（')
          .replace(/\)/g, '）')
          .replace(/\[/g, '【')
          .replace(/\]/g, '】')
      )
      break

    case 'clean-symbols':
      // 清理 OCR 符号噪声（文本级别补充清理，与 Rust 端引擎级过滤互补）
      // 常见于截图中 UI 图标（文件夹箭头、文件类型图标、状态图标等）被误识别为文字字符
      formatted = formatted
        .split('\n')
        .map((line) => {
          let cleaned = line

          // 1. 移除行首的明确噪声符号（不可能是正常文本内容的）
          cleaned = cleaned.replace(RE_LINE_START_NOISE, '$1')

          // 2. 移除行首的连续 > 符号（如 >> 或 >>> ）
          cleaned = cleaned.replace(RE_LINE_START_ARROWS, '$1')

          // 3. 移除行首孤立的单个符号字符（后面跟空格+实际文本内容）
          //    例如 "! releaseyml" 中的 "!"、"· 文本" 中的 "·"
          cleaned = cleaned.replace(RE_LINE_START_LONE_PUNCT, '$1')

          return cleaned
        })
        .filter((line) => {
          // 4. 过滤掉纯符号行（不含任何字母、数字或汉字）
          const stripped = line.trim()
          if (stripped.length === 0) return true // 保留空行
          return RE_HAS_REAL_CONTENT.test(stripped)
        })
        .join('\n')

      // 5. 清理因移除符号产生的多余空行
      formatted = formatted.replace(/\n{3,}/g, '\n\n').trim()
      break

    case 'strip-line-numbers':
      // 去除行号：移除每行开头的行号（如 "1. ", "12: ", "123 "）
      // 仅当检测到连续递增数字时才处理，避免误删有意义的数字开头
      formatted = formatted
        .split('\n')
        .map((line) => line.replace(RE_LINE_NUMBER, ''))
        .join('\n')
      break

    case 'add-line-numbers':
      // 添加编号：为每个非空行添加 "1. "、"2. "、"3. " 等编号（类似 Word 编号列表）
      // 空行保留不编号，已有编号的行先去除再重新编号
      {
        let counter = 1
        formatted = formatted
          .split('\n')
          .map((line) => {
            const trimmed = line.trim()
            if (trimmed.length === 0) return '' // 空行保留
            // 移除已有的编号前缀（数字+点+空格 或 数字+)空格）
            const stripped = trimmed.replace(/^\d+[.)、]\s*/, '')
            return `${counter++}. ${stripped}`
          })
          .join('\n')
      }
      break

    case 'remove-cjk-spaces':
      // 中文间去空格：移除中文字符之间的空格（OCR 常见问题）
      // 循环处理，确保连续的 CJK 空格 CJK 都被清理
      {
        let prev: string
        do {
          prev = formatted
          formatted = formatted.replace(RE_CJK_SPACE, '$1$2')
        } while (formatted !== prev)
      }
      break
  }

  return formatted
}

// ============================================
// Composable
// ============================================

/**
 * OCR 文本操作 composable
 *
 * 使用方式：
 * ```ts
 * const textRef = ref('')
 * const originalRef = ref('')
 * const { formatText, copyText, translateText, ... } = useOcrTextActions(textRef, originalRef)
 * ```
 *
 * @param textRef 当前文本的 Ref
 * @param originalTextRef 原始文本的 Ref（用于恢复原文）
 * @param options 配置选项
 */
export function useOcrTextActions(
  textRef: Ref<string>,
  originalTextRef: Ref<string>,
  options?: OcrTextActionsOptions
) {
  const externalLoading = options?.isLoading

  // ============================================
  // Computed
  // ============================================

  /** 是否有内容 */
  const hasContent = computed(() => textRef.value.length > 0)

  /** 文本是否已修改（与原文不同） */
  const hasChanges = computed(() => textRef.value !== originalTextRef.value)

  /** 字符数 */
  const charCount = computed(() => textRef.value.length)

  // ============================================
  // 文本格式化
  // ============================================

  /**
   * 格式化文本
   * @param type 格式化类型
   */
  function formatText(type: FormatType): void {
    if (!textRef.value) return

    textRef.value = applyFormat(textRef.value, type)
  }

  /**
   * 恢复原始文本
   */
  function restoreOriginal(): void {
    textRef.value = originalTextRef.value
  }

  // ============================================
  // 剪贴板
  // ============================================

  /**
   * 复制文本到剪贴板
   * @returns 是否成功
   */
  async function copyText(): Promise<boolean> {
    if (!textRef.value) return false

    try {
      await writeText(textRef.value)
      return true
    } catch (error) {
      console.error('[useOcrTextActions] 复制失败:', error)
      return false
    }
  }

  // ============================================
  // 翻译
  // ============================================

  /** 直接翻译结果类型（与 Rust DirectTranslationResult 对应） */
  interface DirectTranslateResult {
    translatedText: string
    sourceLang: string
    targetLang: string
    provider: string
  }

  /**
   * 翻译文本（智能语言检测，不依赖 Sidecar）
   *
   * 参考 Python 版本的 _do_smart_translate：
   * - 检测文本是否包含中文
   * - 中文→翻译为英语，非中文→翻译为中文
   *
   * 优先使用 Rust 原生直接翻译（免费 MyMemory API），
   * 无需 Python Sidecar 即可工作。
   *
   * @param targetLang 目标语言（可选，不提供时自动检测）
   * @throws Error 翻译服务返回空结果时抛出
   */
  async function translateText(targetLang?: string): Promise<void> {
    if (!textRef.value) return

    try {
      if (externalLoading) externalLoading.value = true

      // 直接调用 Rust 原生翻译命令（不依赖 Sidecar）
      const result = await invoke<DirectTranslateResult>('translate_text_direct', {
        text: textRef.value,
        targetLang: targetLang || null,
      })

      if (result.translatedText) {
        textRef.value = result.translatedText
      } else {
        throw new Error('翻译服务返回空结果')
      }
    } finally {
      if (externalLoading) externalLoading.value = false
    }
  }

  // ============================================
  // 本地 OCR
  // ============================================

  /**
   * 使用本地 OCR 重新识别
   * @returns OCR 识别结果文本
   */
  async function performLocalOcr(
    engine: OcrEngine = 'local'
  ): Promise<{ text: string; confidence: number; elapsedTime: number; engine: string }> {
    const imagePath = options?.getImagePath?.()
    if (!imagePath) {
      throw new Error('没有可识别的图片')
    }

    try {
      if (externalLoading) externalLoading.value = true

      const startTime = Date.now()
      const result = await invoke<OcrCommandResult>('call_ocr', { imagePath, engine })
      const elapsedTime = Date.now() - startTime

      // 提取文本
      const text = result.boxes && result.boxes.length > 0
        ? result.boxes.map((box) => box.text).join('\n')
        : result.text ?? ''

      // 计算平均置信度
      const avgConfidence =
        result.boxes && result.boxes.length > 0
          ? result.boxes.reduce((sum, box) => sum + (box.confidence ?? 0), 0) /
            result.boxes.length
          : 0

      // 更新文本
      textRef.value = text
      originalTextRef.value = text

      return {
        text,
        confidence: Math.round(avgConfidence * 100),
        elapsedTime,
        engine: result.engine ?? engine,
      }
    } finally {
      if (externalLoading) externalLoading.value = false
    }
  }

  return {
    // Computed
    hasContent,
    hasChanges,
    charCount,

    // 文本操作
    formatText,
    restoreOriginal,
    copyText,
    translateText,
    performLocalOcr,
  }
}
