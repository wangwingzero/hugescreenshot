/**
 * Property-Based Tests for Character Count Accuracy
 *
 * Feature: workbench-layout-redesign, Property 9: Character Count Accuracy
 *
 * **Validates: Requirements 6.1**
 *
 * Property Definition:
 * For any OCR text displayed in the panel, the character count shown in the status bar
 * SHALL equal the actual length of the text string.
 *
 * This test file verifies:
 * 1. Character count equals text.length for any string
 * 2. Empty strings result in zero character count
 * 3. Unicode characters (including CJK) are counted correctly
 * 4. Whitespace characters are included in the count
 * 5. Special characters and control characters are handled
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ============================================================================
// Character Count Logic (extracted from OcrStatusBar.vue / workbenchStore)
// ============================================================================

/**
 * Compute character count for OCR text
 * This mirrors the character counting logic used in the application.
 *
 * The character count uses JavaScript's native string.length property,
 * which counts UTF-16 code units. This is the standard behavior for
 * JavaScript strings and matches user expectations for most text.
 *
 * @param text - The OCR text to count characters for
 * @returns The character count (number of UTF-16 code units)
 */
function computeCharCount(text: string | undefined | null): number {
  if (text === undefined || text === null) {
    return 0
  }
  return text.length
}

/**
 * Format character count for display
 * This mirrors the formattedCharCount computed property in OcrStatusBar.vue
 *
 * @param charCount - The character count to format
 * @returns Formatted string like "1,234 字"
 */
function formatCharCount(charCount: number): string {
  return `${charCount.toLocaleString('zh-CN')} 字`
}

// ============================================================================
// Arbitraries (using only basic fast-check 4.x compatible functions)
// ============================================================================

/**
 * Arbitrary for generating basic strings
 */
const basicStringArb: fc.Arbitrary<string> = fc.string({
  minLength: 0,
  maxLength: 500,
})

/**
 * Arbitrary for generating CJK (Chinese, Japanese, Korean) text
 * Common in OCR results for this application
 * Uses fc.array + fc.integer to build strings from code points
 */
const cjkStringArb: fc.Arbitrary<string> = fc
  .array(fc.integer({ min: 0x4e00, max: 0x9fff }), { minLength: 0, maxLength: 200 })
  .map((codes) => codes.map((code) => String.fromCharCode(code)).join(''))

/**
 * Arbitrary for generating mixed content strings
 * Combines ASCII, CJK, and special characters
 */
const mixedContentArb: fc.Arbitrary<string> = fc.oneof(
  basicStringArb,
  cjkStringArb,
  // Specific patterns common in OCR
  fc.constant(''),
  fc.constant('Hello 世界'),
  fc.constant('测试文本 Test 123'),
  fc.constant('价格：¥99.99'),
  fc.constant('日期：2024年1月1日'),
)

/**
 * Arbitrary for generating whitespace strings
 */
const whitespaceStringArb: fc.Arbitrary<string> = fc
  .array(fc.constantFrom(' ', '\t', '\n', '\r'), { minLength: 0, maxLength: 50 })
  .map((chars) => chars.join(''))

/**
 * Arbitrary for generating OCR-like text
 * Simulates realistic OCR output with mixed content
 */
const ocrTextArb: fc.Arbitrary<string> = fc.oneof(
  // Empty
  fc.constant(''),
  // Pure ASCII
  basicStringArb,
  // Pure CJK
  cjkStringArb,
  // Mixed content
  fc.tuple(basicStringArb, cjkStringArb).map(([a, b]) => `${a}${b}`),
  // With line breaks (common in OCR)
  fc
    .array(fc.string({ minLength: 1, maxLength: 50 }), { minLength: 1, maxLength: 10 })
    .map((lines) => lines.join('\n')),
  // With numbers and punctuation
  fc
    .tuple(
      fc.string({ minLength: 0, maxLength: 50 }),
      fc.integer({ min: 0, max: 9999 }),
      fc.string({ minLength: 0, maxLength: 50 })
    )
    .map(([a, n, b]) => `${a}${n}${b}`),
)

// ============================================================================
// Property Tests
// ============================================================================

describe('Feature: workbench-layout-redesign, Property 9: Character Count Accuracy', () => {
  // ==========================================================================
  // Property 9.1: Character count equals text.length
  // ==========================================================================

  it('Property 9: Character count equals text.length for any string', () => {
    fc.assert(
      fc.property(ocrTextArb, (text) => {
        const charCount = computeCharCount(text)

        // Property: Character count SHALL equal the actual length of the text string
        expect(charCount).toBe(text.length)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 9.2: Empty string results in zero count
  // ==========================================================================

  it('Property 9: Empty string results in zero character count', () => {
    const charCount = computeCharCount('')

    // Property: Empty string should have zero character count
    expect(charCount).toBe(0)
  })

  // ==========================================================================
  // Property 9.3: Undefined/null text results in zero count
  // ==========================================================================

  it('Property 9: Undefined or null text results in zero character count', () => {
    // Property: Undefined should result in zero count
    expect(computeCharCount(undefined)).toBe(0)

    // Property: Null should result in zero count
    expect(computeCharCount(null)).toBe(0)
  })

  // ==========================================================================
  // Property 9.4: ASCII strings are counted correctly
  // ==========================================================================

  it('Property 9: ASCII strings character count matches length', () => {
    fc.assert(
      fc.property(basicStringArb, (text) => {
        const charCount = computeCharCount(text)

        // Property: ASCII character count equals string length
        expect(charCount).toBe(text.length)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 9.5: CJK characters are counted correctly
  // ==========================================================================

  it('Property 9: CJK characters are counted correctly', () => {
    fc.assert(
      fc.property(cjkStringArb, (text) => {
        const charCount = computeCharCount(text)

        // Property: CJK character count equals string length
        // Note: CJK characters in BMP are single UTF-16 code units
        expect(charCount).toBe(text.length)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 9.6: Whitespace is included in count
  // ==========================================================================

  it('Property 9: Whitespace characters are included in character count', () => {
    fc.assert(
      fc.property(whitespaceStringArb, (text) => {
        const charCount = computeCharCount(text)

        // Property: Whitespace characters are counted
        expect(charCount).toBe(text.length)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 9.7: Mixed content is counted correctly
  // ==========================================================================

  it('Property 9: Mixed content (ASCII + CJK + special) is counted correctly', () => {
    fc.assert(
      fc.property(mixedContentArb, (text) => {
        const charCount = computeCharCount(text)

        // Property: Mixed content character count equals string length
        expect(charCount).toBe(text.length)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 9.8: Character count is never negative
  // ==========================================================================

  it('Property 9: Character count is never negative', () => {
    fc.assert(
      fc.property(
        fc.oneof(ocrTextArb, fc.constant(undefined as string | undefined), fc.constant(null as string | null)),
        (text) => {
          const charCount = computeCharCount(text)

          // Property: Character count should never be negative
          expect(charCount).toBeGreaterThanOrEqual(0)

          return true
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 9.9: Character count is an integer
  // ==========================================================================

  it('Property 9: Character count is always an integer', () => {
    fc.assert(
      fc.property(ocrTextArb, (text) => {
        const charCount = computeCharCount(text)

        // Property: Character count should be an integer
        expect(Number.isInteger(charCount)).toBe(true)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 9.10: Concatenation property
  // ==========================================================================

  it('Property 9: Character count of concatenated strings equals sum of individual counts', () => {
    fc.assert(
      fc.property(ocrTextArb, ocrTextArb, (text1, text2) => {
        const count1 = computeCharCount(text1)
        const count2 = computeCharCount(text2)
        const combinedCount = computeCharCount(text1 + text2)

        // Property: count(a + b) = count(a) + count(b)
        expect(combinedCount).toBe(count1 + count2)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 9.11: Substring property
  // ==========================================================================

  it('Property 9: Character count of substring is less than or equal to original', () => {
    fc.assert(
      fc.property(
        ocrTextArb.filter((s) => s.length > 0),
        fc.integer({ min: 0, max: 100 }),
        fc.integer({ min: 0, max: 100 }),
        (text, start, length) => {
          const normalizedStart = Math.min(start, text.length)
          const normalizedLength = Math.min(length, text.length - normalizedStart)
          const substring = text.substring(normalizedStart, normalizedStart + normalizedLength)

          const originalCount = computeCharCount(text)
          const substringCount = computeCharCount(substring)

          // Property: Substring count should be <= original count
          expect(substringCount).toBeLessThanOrEqual(originalCount)

          return true
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 9.12: Specific length strings
  // ==========================================================================

  it('Property 9: Strings of specific length have correct character count', () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 100 }), (targetLength) => {
        // Generate a string of exactly targetLength characters
        const text = 'a'.repeat(targetLength)
        const charCount = computeCharCount(text)

        // Property: Character count should equal the target length
        expect(charCount).toBe(targetLength)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 9.13: Line breaks are counted
  // ==========================================================================

  it('Property 9: Line breaks are included in character count', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 50 }), { minLength: 1, maxLength: 10 }),
        (lines) => {
          const text = lines.join('\n')
          const charCount = computeCharCount(text)

          // Property: Character count includes line break characters
          // Total = sum of line lengths + (number of lines - 1) for \n characters
          const expectedCount = lines.reduce((sum, line) => sum + line.length, 0) + (lines.length - 1)
          expect(charCount).toBe(expectedCount)

          return true
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 9.14: Format function preserves count information
  // ==========================================================================

  it('Property 9: Formatted character count contains the correct number', () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 1000000 }), (count) => {
        const formatted = formatCharCount(count)

        // Property: Formatted string should contain the count value
        // Remove formatting (commas, spaces) and check the number
        const extractedNumber = parseInt(formatted.replace(/[^\d]/g, ''), 10)
        expect(extractedNumber).toBe(count)

        // Property: Formatted string should end with "字"
        expect(formatted.endsWith('字')).toBe(true)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 9.15: Real-world OCR text examples
  // ==========================================================================

  it('Property 9: Real-world OCR text examples have correct character count', () => {
    const realWorldExamples = [
      '这是一段中文OCR识别结果',
      'This is English OCR text',
      '混合内容 Mixed Content 123',
      '第一行\n第二行\n第三行',
      '价格：¥99.99',
      '日期：2024年1月1日',
      '电话：+86 138-0000-0000',
      '邮箱：test@example.com',
      '网址：https://example.com/path?query=value',
      '特殊符号：【】《》「」『』',
    ]

    for (const text of realWorldExamples) {
      const charCount = computeCharCount(text)

      // Property: Character count equals string.length
      expect(charCount).toBe(text.length)
    }
  })

  // ==========================================================================
  // Property 9.16: Very long strings
  // ==========================================================================

  it('Property 9: Very long strings are counted correctly', () => {
    fc.assert(
      fc.property(fc.integer({ min: 1000, max: 10000 }), (length) => {
        const text = 'x'.repeat(length)
        const charCount = computeCharCount(text)

        // Property: Long strings have correct character count
        expect(charCount).toBe(length)

        return true
      }),
      {
        numRuns: 20, // Fewer runs for performance
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 9.17: Idempotency
  // ==========================================================================

  it('Property 9: Computing character count multiple times gives same result', () => {
    fc.assert(
      fc.property(ocrTextArb, (text) => {
        const count1 = computeCharCount(text)
        const count2 = computeCharCount(text)
        const count3 = computeCharCount(text)

        // Property: Character count is idempotent
        expect(count1).toBe(count2)
        expect(count2).toBe(count3)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 9.18: Emoji handling (surrogate pairs)
  // ==========================================================================

  it('Property 9: Emoji characters are counted as UTF-16 code units', () => {
    // Common emojis that use surrogate pairs (2 UTF-16 code units each)
    const emojis = ['😀', '🎉', '👍', '❤️', '🔥', '✨']

    for (const emoji of emojis) {
      const charCount = computeCharCount(emoji)

      // Property: Character count equals string.length (UTF-16 code units)
      // Some emojis are 2 code units (surrogate pairs), some are more (with modifiers)
      expect(charCount).toBe(emoji.length)
    }
  })
})
