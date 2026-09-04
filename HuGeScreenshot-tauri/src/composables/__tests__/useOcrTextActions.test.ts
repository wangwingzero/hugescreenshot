/**
 * applyFormat() 纯函数单元测试
 *
 * 覆盖所有 8 种格式化类型，重点测试边界情况：
 * - URL/邮箱/代码块在标点转换时的保护
 * - Markdown # 在符号清理时的保留
 * - 多行连续合并（smart-paragraphs）
 * - 句末标点检测、标题/短行检测、Markdown标题保护
 * - 多余空行压缩
 * - CJK 空格清理的循环处理
 */

import { describe, it, expect } from 'vitest'
import { applyFormat } from '../useOcrTextActions'

// ============================================
// merge-lines
// ============================================
describe('merge-lines', () => {
  it('合并多行为单行', () => {
    expect(applyFormat('aaa\nbbb\nccc', 'merge-lines')).toBe('aaabbbccc')
  })

  it('处理 CRLF 换行', () => {
    expect(applyFormat('aaa\r\nbbb\r\nccc', 'merge-lines')).toBe('aaabbbccc')
  })

  it('空文本不变', () => {
    expect(applyFormat('', 'merge-lines')).toBe('')
  })
})

// ============================================
// smart-paragraphs
// ============================================
describe('smart-paragraphs', () => {
  it('保留空行分段，合并单换行', () => {
    const input = '第一段第一行\n第一段第二行\n\n第二段'
    const result = applyFormat(input, 'smart-paragraphs')
    expect(result).toContain('第一段第一行第一段第二行')
    expect(result).toContain('\n\n')
    expect(result).toContain('第二段')
  })

  it('中文之间合并不加空格', () => {
    const input = '你好\n世界'
    expect(applyFormat(input, 'smart-paragraphs')).toBe('你好世界')
  })

  it('英文之间合并加空格', () => {
    const input = 'hello\nworld'
    expect(applyFormat(input, 'smart-paragraphs')).toBe('hello world')
  })

  it('连续多行都被合并（非仅首次）', () => {
    const input = 'line1\nline2\nline3\nline4'
    const result = applyFormat(input, 'smart-paragraphs')
    // 所有行应被合并为一行
    expect(result).not.toContain('\n')
  })

  it('CRLF 被正确处理', () => {
    const input = 'aaa\r\nbbb\r\nccc'
    const result = applyFormat(input, 'smart-paragraphs')
    expect(result).not.toContain('\r')
  })

  // ---- 结构化行保护测试 ----

  it('保护列表项不被合并', () => {
    const input = '段落文本\n- 列表项1\n- 列表项2\n后续段落'
    const result = applyFormat(input, 'smart-paragraphs')
    expect(result).toContain('- 列表项1\n- 列表项2')
  })

  it('保护数字列表项不被合并', () => {
    const input = '说明：\n1. 第一步\n2. 第二步\n3. 第三步'
    const result = applyFormat(input, 'smart-paragraphs')
    expect(result).toContain('1. 第一步\n2. 第二步\n3. 第三步')
  })

  it('保护表格行不被合并', () => {
    const input = '| 列A | 列B |\n| --- | --- |\n| 值1 | 值2 |'
    const result = applyFormat(input, 'smart-paragraphs')
    expect(result).toContain('| 列A | 列B |')
    expect(result).toContain('| 值1 | 值2 |')
  })

  it('保护缩进代码块不被合并', () => {
    const input = '代码如下：\n    const x = 1\n    const y = 2\n结束'
    const result = applyFormat(input, 'smart-paragraphs')
    expect(result).toContain('    const x = 1\n    const y = 2')
  })

  it('保护含代码特征的行不被合并', () => {
    const input = 'function hello() {\n  return true\n}'
    const result = applyFormat(input, 'smart-paragraphs')
    // 含 { 和 return 的行不应被合并
    expect(result).toContain('function hello() {')
    expect(result).toContain('return true')
  })

  // ---- 句末标点检测测试 ----

  it('以中文句号结尾的行视为段落结束', () => {
    const input = '第一段内容。\n第二段内容'
    const result = applyFormat(input, 'smart-paragraphs')
    expect(result).toBe('第一段内容。\n第二段内容')
  })

  it('以英文句号结尾的行视为段落结束', () => {
    const input = 'First paragraph.\nSecond paragraph'
    const result = applyFormat(input, 'smart-paragraphs')
    expect(result).toBe('First paragraph.\nSecond paragraph')
  })

  it('以问号结尾的行视为段落结束', () => {
    const input = '这是提问？\n这是回答'
    const result = applyFormat(input, 'smart-paragraphs')
    expect(result).toBe('这是提问？\n这是回答')
  })

  it('以感叹号结尾的行视为段落结束', () => {
    const input = '注意！\n请查看以下内容'
    const result = applyFormat(input, 'smart-paragraphs')
    expect(result).toBe('注意！\n请查看以下内容')
  })

  it('以省略号结尾的行视为段落结束', () => {
    const input = '未完…\n下一段'
    const result = applyFormat(input, 'smart-paragraphs')
    expect(result).toBe('未完…\n下一段')
  })

  it('以逗号结尾的行不视为段落结束（继续合并）', () => {
    const input = '第一部分，\n第二部分'
    const result = applyFormat(input, 'smart-paragraphs')
    expect(result).toBe('第一部分，第二部分')
  })

  // ---- 标题/短行检测测试 ----

  it('中文编号标题独立保留', () => {
    const input = '前面的内容\n一、基本概述\n具体描述文字'
    const result = applyFormat(input, 'smart-paragraphs')
    expect(result).toContain('一、基本概述')
    // 标题应在独立行上
    const lines = result.split('\n')
    expect(lines.some(l => l.trim() === '一、基本概述')).toBe(true)
  })

  it('第X章标题独立保留', () => {
    const input = '上文内容\n第三章 系统设计\n本章介绍系统设计'
    const result = applyFormat(input, 'smart-paragraphs')
    const lines = result.split('\n')
    expect(lines.some(l => l.includes('第三章'))).toBe(true)
  })

  it('全大写英文标题独立保留', () => {
    const input = 'Some content here\nINTRODUCTION AND OVERVIEW\nThe following is'
    const result = applyFormat(input, 'smart-paragraphs')
    const lines = result.split('\n')
    expect(lines.some(l => l.includes('INTRODUCTION AND OVERVIEW'))).toBe(true)
  })

  // ---- Markdown 标题保护测试 ----

  it('Markdown 标题不被合并', () => {
    const input = '前面文本\n# 标题一\n后面文本'
    const result = applyFormat(input, 'smart-paragraphs')
    expect(result).toContain('# 标题一')
    const lines = result.split('\n')
    expect(lines.some(l => l === '# 标题一')).toBe(true)
  })

  it('多级 Markdown 标题不被合并', () => {
    const input = '文本\n## 二级标题\n### 三级标题\n正文'
    const result = applyFormat(input, 'smart-paragraphs')
    expect(result).toContain('## 二级标题')
    expect(result).toContain('### 三级标题')
  })

  // ---- 多余空行压缩测试 ----

  it('连续空行压缩为一个段落分隔', () => {
    const input = '第一段\n\n\n\n第二段'
    const result = applyFormat(input, 'smart-paragraphs')
    // 应只有一个空行分隔
    expect(result).toBe('第一段\n\n第二段')
  })

  it('三个以上连续空行压缩为一个', () => {
    const input = 'A\n\n\n\n\nB\n\n\n\nC'
    const result = applyFormat(input, 'smart-paragraphs')
    expect(result).toBe('A\n\nB\n\nC')
  })
})

// ============================================
// remove-spaces
// ============================================
describe('remove-spaces', () => {
  it('多空格合并为单空格', () => {
    expect(applyFormat('a   b    c', 'remove-spaces')).toBe('a b c')
  })

  it('Tab 合并为空格', () => {
    expect(applyFormat('a\t\tb', 'remove-spaces')).toBe('a b')
  })

  it('首尾空格被 trim', () => {
    expect(applyFormat('  hello  ', 'remove-spaces')).toBe('hello')
  })
})

// ============================================
// punct-to-en
// ============================================
describe('punct-to-en', () => {
  it('基本中文标点转英文', () => {
    expect(applyFormat('你好，世界！', 'punct-to-en')).toBe('你好,世界!')
  })

  it('括号转换', () => {
    expect(applyFormat('（内容）', 'punct-to-en')).toBe('(内容)')
  })

  it('引号转换', () => {
    expect(applyFormat('\u201c你好\u201d', 'punct-to-en')).toBe('"你好"')
  })
})

// ============================================
// punct-to-cn
// ============================================
describe('punct-to-cn', () => {
  it('基本英文标点转中文', () => {
    expect(applyFormat('hello,world!', 'punct-to-cn')).toBe('hello，world！')
  })

  it('保护 URL 不被误转换', () => {
    const input = '访问 https://example.com/path?q=1&v=2 获取信息'
    const result = applyFormat(input, 'punct-to-cn')
    // URL 内的标点应保持不变
    expect(result).toContain('https://example.com/path?q=1&v=2')
  })

  it('保护邮箱不被误转换', () => {
    const input = '联系 test@example.com 获取帮助'
    const result = applyFormat(input, 'punct-to-cn')
    expect(result).toContain('test@example.com')
  })

  it('保护反引号代码不被误转换', () => {
    const input = '使用 `console.log("hello")` 输出'
    const result = applyFormat(input, 'punct-to-cn')
    expect(result).toContain('`console.log("hello")`')
  })

  it('保护 Windows 文件路径不被误转换', () => {
    const input = '文件在 C:\\Users\\test\\file.txt 目录下'
    const result = applyFormat(input, 'punct-to-cn')
    expect(result).toContain('C:\\Users\\test\\file.txt')
  })

  it('非保护区域正常转换', () => {
    const input = 'hello,world. https://example.com ok!'
    const result = applyFormat(input, 'punct-to-cn')
    // 非 URL 部分应转换
    expect(result).toContain('hello，world')
    expect(result).toContain('ok！')
    // URL 保持不变
    expect(result).toContain('https://example.com')
  })
})

// ============================================
// clean-symbols
// ============================================
describe('clean-symbols', () => {
  it('保留 Markdown # 标题', () => {
    const input = '# 标题\n正文'
    const result = applyFormat(input, 'clean-symbols')
    expect(result).toContain('# 标题')
  })

  it('移除行首噪声符号', () => {
    const input = '► 文件名.txt'
    const result = applyFormat(input, 'clean-symbols')
    expect(result).toContain('文件名.txt')
    expect(result).not.toContain('►')
  })

  it('移除纯符号行', () => {
    const input = '正文\n>>>>\n正文2'
    const result = applyFormat(input, 'clean-symbols')
    expect(result).not.toContain('>>>>')
  })

  it('保留有实际内容的行', () => {
    const input = '有内容的行\n另一行文字'
    const result = applyFormat(input, 'clean-symbols')
    expect(result).toContain('有内容的行')
    expect(result).toContain('另一行文字')
  })
})

// ============================================
// strip-line-numbers
// ============================================
describe('strip-line-numbers', () => {
  it('移除行号（数字+点）', () => {
    const input = '1. 第一行\n2. 第二行\n3. 第三行'
    const result = applyFormat(input, 'strip-line-numbers')
    expect(result).toBe('第一行\n第二行\n第三行')
  })

  it('移除行号（数字+冒号）', () => {
    const input = '10: function hello() {\n11: return true\n12: }'
    const result = applyFormat(input, 'strip-line-numbers')
    expect(result).toContain('function hello()')
    expect(result).not.toMatch(/^\d+:/)
  })

  it('移除行号（数字+空格）', () => {
    const input = '1 第一行\n2 第二行'
    const result = applyFormat(input, 'strip-line-numbers')
    expect(result).toBe('第一行\n第二行')
  })

  it('保留无行号的行不变', () => {
    const input = '无行号的文本'
    expect(applyFormat(input, 'strip-line-numbers')).toBe('无行号的文本')
  })
})

// ============================================
// add-line-numbers
// ============================================
describe('add-line-numbers', () => {
  it('为每行添加编号', () => {
    const input = '第一行\n第二行\n第三行'
    const result = applyFormat(input, 'add-line-numbers')
    expect(result).toBe('1. 第一行\n2. 第二行\n3. 第三行')
  })

  it('空行不编号', () => {
    const input = '第一行\n\n第二行'
    const result = applyFormat(input, 'add-line-numbers')
    expect(result).toBe('1. 第一行\n\n2. 第二行')
  })

  it('替换已有编号为新编号', () => {
    const input = '3. 第一行\n5. 第二行\n9. 第三行'
    const result = applyFormat(input, 'add-line-numbers')
    expect(result).toBe('1. 第一行\n2. 第二行\n3. 第三行')
  })

  it('替换中文顿号编号', () => {
    const input = '1、第一行\n2、第二行'
    const result = applyFormat(input, 'add-line-numbers')
    expect(result).toBe('1. 第一行\n2. 第二行')
  })

  it('替换右括号编号', () => {
    const input = '1) 第一行\n2) 第二行'
    const result = applyFormat(input, 'add-line-numbers')
    expect(result).toBe('1. 第一行\n2. 第二行')
  })

  it('单行文本也添加编号', () => {
    const input = '仅一行内容'
    const result = applyFormat(input, 'add-line-numbers')
    expect(result).toBe('1. 仅一行内容')
  })
})

// ============================================
// remove-cjk-spaces
// ============================================
describe('remove-cjk-spaces', () => {
  it('移除中文字符间的空格', () => {
    const input = '你 好 世 界'
    expect(applyFormat(input, 'remove-cjk-spaces')).toBe('你好世界')
  })

  it('保留中英文之间的空格', () => {
    const input = '你好 hello 世界'
    const result = applyFormat(input, 'remove-cjk-spaces')
    expect(result).toBe('你好 hello 世界')
  })

  it('连续多个中文字符间空格都被清理', () => {
    const input = '一 二 三 四 五'
    expect(applyFormat(input, 'remove-cjk-spaces')).toBe('一二三四五')
  })

  it('空文本不变', () => {
    expect(applyFormat('', 'remove-cjk-spaces')).toBe('')
  })

  it('无 CJK 空格时不变', () => {
    const input = 'hello world 123'
    expect(applyFormat(input, 'remove-cjk-spaces')).toBe('hello world 123')
  })
})
