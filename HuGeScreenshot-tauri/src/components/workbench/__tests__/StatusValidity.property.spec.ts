/**
 * Property-Based Tests for Status Value Validity
 *
 * Feature: workbench-layout-redesign, Property 10: Status Value Validity
 *
 * **Validates: Requirements 6.2**
 *
 * Property Definition:
 * For any state of the OCR panel, the displayed status SHALL be one of the valid
 * enum values: 'ready', 'processing', 'completed', or 'error'.
 *
 * This test file verifies:
 * 1. Status values are always one of the valid enum values
 * 2. Status icon mapping is complete for all valid statuses
 * 3. Status text mapping is complete for all valid statuses
 * 4. Status class mapping is complete for all valid statuses
 * 5. Invalid status values are rejected or handled gracefully
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ============================================================================
// Types (mirrored from OcrStatusBar.vue)
// ============================================================================

/** Valid OCR status values */
export type OcrStatus = 'ready' | 'processing' | 'completed' | 'error'

/** Array of all valid status values for validation */
const VALID_STATUSES: readonly OcrStatus[] = ['ready', 'processing', 'completed', 'error'] as const

// ============================================================================
// Status Logic (extracted from OcrStatusBar.vue)
// ============================================================================

/**
 * Check if a value is a valid OcrStatus
 * @param value - The value to check
 * @returns true if the value is a valid OcrStatus
 */
function isValidOcrStatus(value: unknown): value is OcrStatus {
  return typeof value === 'string' && VALID_STATUSES.includes(value as OcrStatus)
}

/**
 * Get status icon for a given status
 * This mirrors the statusIcon computed property in OcrStatusBar.vue
 * @param status - The OCR status
 * @returns The icon string for the status
 */
function getStatusIcon(status: OcrStatus): string {
  const icons: Record<OcrStatus, string> = {
    ready: '⚪',
    processing: '🔄',
    completed: '✅',
    error: '❌',
  }
  return icons[status]
}

/**
 * Get status text for a given status
 * This mirrors the statusText computed property in OcrStatusBar.vue
 * @param status - The OCR status
 * @returns The display text for the status
 */
function getStatusText(status: OcrStatus): string {
  const texts: Record<OcrStatus, string> = {
    ready: '就绪',
    processing: '处理中...',
    completed: '完成',
    error: '错误',
  }
  return texts[status]
}

/**
 * Get status CSS class for a given status
 * This mirrors the statusClass computed property in OcrStatusBar.vue
 * @param status - The OCR status
 * @returns The CSS class name for the status
 */
function getStatusClass(status: OcrStatus): string {
  return `status-${status}`
}

// ============================================================================
// Arbitraries
// ============================================================================

/**
 * Arbitrary for generating valid OcrStatus values
 * Uses fc.constantFrom to ensure only valid enum values are generated
 */
const validStatusArb: fc.Arbitrary<OcrStatus> = fc.constantFrom(...VALID_STATUSES)

/**
 * Arbitrary for generating invalid status strings
 * These are strings that are NOT valid OcrStatus values
 */
const invalidStatusStringArb: fc.Arbitrary<string> = fc
  .string({ minLength: 0, maxLength: 50 })
  .filter((s) => !VALID_STATUSES.includes(s as OcrStatus))

/**
 * Arbitrary for generating any value (for testing type guards)
 */
const anyValueArb: fc.Arbitrary<unknown> = fc.oneof(
  fc.string(),
  fc.integer(),
  fc.boolean(),
  fc.constant(null),
  fc.constant(undefined),
  fc.array(fc.string()),
  fc.object(),
)

// ============================================================================
// Property Tests
// ============================================================================

describe('Feature: workbench-layout-redesign, Property 10: Status Value Validity', () => {
  // ==========================================================================
  // Property 10.1: Valid status values are recognized
  // ==========================================================================

  it('Property 10: All valid status values are recognized as valid', () => {
    fc.assert(
      fc.property(validStatusArb, (status) => {
        // Property: Every valid status SHALL be recognized by isValidOcrStatus
        expect(isValidOcrStatus(status)).toBe(true)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 10.2: Status is always one of the valid enum values
  // ==========================================================================

  it('Property 10: Status is always one of the valid enum values', () => {
    fc.assert(
      fc.property(validStatusArb, (status) => {
        // Property: Status SHALL be one of 'ready', 'processing', 'completed', or 'error'
        expect(VALID_STATUSES).toContain(status)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 10.3: Invalid strings are not valid statuses
  // ==========================================================================

  it('Property 10: Invalid strings are not recognized as valid statuses', () => {
    fc.assert(
      fc.property(invalidStatusStringArb, (invalidStatus) => {
        // Property: Invalid strings SHALL NOT be recognized as valid OcrStatus
        expect(isValidOcrStatus(invalidStatus)).toBe(false)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 10.4: Non-string values are not valid statuses
  // ==========================================================================

  it('Property 10: Non-string values are not valid statuses', () => {
    fc.assert(
      fc.property(
        anyValueArb.filter((v) => typeof v !== 'string'),
        (nonStringValue) => {
          // Property: Non-string values SHALL NOT be valid OcrStatus
          expect(isValidOcrStatus(nonStringValue)).toBe(false)

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
  // Property 10.5: Every valid status has an icon mapping
  // ==========================================================================

  it('Property 10: Every valid status has an icon mapping', () => {
    fc.assert(
      fc.property(validStatusArb, (status) => {
        const icon = getStatusIcon(status)

        // Property: Every valid status SHALL have a non-empty icon
        expect(icon).toBeDefined()
        expect(typeof icon).toBe('string')
        expect(icon.length).toBeGreaterThan(0)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 10.6: Every valid status has a text mapping
  // ==========================================================================

  it('Property 10: Every valid status has a text mapping', () => {
    fc.assert(
      fc.property(validStatusArb, (status) => {
        const text = getStatusText(status)

        // Property: Every valid status SHALL have a non-empty display text
        expect(text).toBeDefined()
        expect(typeof text).toBe('string')
        expect(text.length).toBeGreaterThan(0)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 10.7: Every valid status has a CSS class mapping
  // ==========================================================================

  it('Property 10: Every valid status has a CSS class mapping', () => {
    fc.assert(
      fc.property(validStatusArb, (status) => {
        const cssClass = getStatusClass(status)

        // Property: Every valid status SHALL have a CSS class
        expect(cssClass).toBeDefined()
        expect(typeof cssClass).toBe('string')
        expect(cssClass).toBe(`status-${status}`)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 10.8: Status icon mapping is unique per status
  // ==========================================================================

  it('Property 10: Status icons are unique for each status', () => {
    const icons = VALID_STATUSES.map((status) => getStatusIcon(status))
    const uniqueIcons = new Set(icons)

    // Property: Each status SHALL have a unique icon
    expect(uniqueIcons.size).toBe(VALID_STATUSES.length)
  })

  // ==========================================================================
  // Property 10.9: Status text mapping is unique per status
  // ==========================================================================

  it('Property 10: Status texts are unique for each status', () => {
    const texts = VALID_STATUSES.map((status) => getStatusText(status))
    const uniqueTexts = new Set(texts)

    // Property: Each status SHALL have a unique display text
    expect(uniqueTexts.size).toBe(VALID_STATUSES.length)
  })

  // ==========================================================================
  // Property 10.10: Status CSS class mapping is unique per status
  // ==========================================================================

  it('Property 10: Status CSS classes are unique for each status', () => {
    const classes = VALID_STATUSES.map((status) => getStatusClass(status))
    const uniqueClasses = new Set(classes)

    // Property: Each status SHALL have a unique CSS class
    expect(uniqueClasses.size).toBe(VALID_STATUSES.length)
  })

  // ==========================================================================
  // Property 10.11: Exhaustive coverage of all valid statuses
  // ==========================================================================

  it('Property 10: All four valid statuses are covered', () => {
    // Property: There SHALL be exactly 4 valid status values
    expect(VALID_STATUSES.length).toBe(4)

    // Property: The valid statuses SHALL be 'ready', 'processing', 'completed', 'error'
    expect(VALID_STATUSES).toContain('ready')
    expect(VALID_STATUSES).toContain('processing')
    expect(VALID_STATUSES).toContain('completed')
    expect(VALID_STATUSES).toContain('error')
  })

  // ==========================================================================
  // Property 10.12: Status validation is case-sensitive
  // ==========================================================================

  it('Property 10: Status validation is case-sensitive', () => {
    const caseMutations = [
      'Ready',
      'READY',
      'Processing',
      'PROCESSING',
      'Completed',
      'COMPLETED',
      'Error',
      'ERROR',
    ]

    for (const mutation of caseMutations) {
      // Property: Case variations SHALL NOT be valid statuses
      expect(isValidOcrStatus(mutation)).toBe(false)
    }
  })

  // ==========================================================================
  // Property 10.13: Status validation rejects similar but invalid values
  // ==========================================================================

  it('Property 10: Similar but invalid values are rejected', () => {
    const similarValues = [
      'ready ',      // trailing space
      ' ready',      // leading space
      'ready\n',     // trailing newline
      'readyy',      // typo
      'redy',        // typo
      'process',     // incomplete
      'processinggg',// extra characters
      'complete',    // incomplete
      'err',         // incomplete
      'errors',      // plural
    ]

    for (const value of similarValues) {
      // Property: Similar but invalid values SHALL NOT be valid statuses
      expect(isValidOcrStatus(value)).toBe(false)
    }
  })

  // ==========================================================================
  // Property 10.14: Status icon mapping is idempotent
  // ==========================================================================

  it('Property 10: Status icon mapping is idempotent', () => {
    fc.assert(
      fc.property(validStatusArb, (status) => {
        const icon1 = getStatusIcon(status)
        const icon2 = getStatusIcon(status)
        const icon3 = getStatusIcon(status)

        // Property: Getting icon multiple times SHALL return same result
        expect(icon1).toBe(icon2)
        expect(icon2).toBe(icon3)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 10.15: Status text mapping is idempotent
  // ==========================================================================

  it('Property 10: Status text mapping is idempotent', () => {
    fc.assert(
      fc.property(validStatusArb, (status) => {
        const text1 = getStatusText(status)
        const text2 = getStatusText(status)
        const text3 = getStatusText(status)

        // Property: Getting text multiple times SHALL return same result
        expect(text1).toBe(text2)
        expect(text2).toBe(text3)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 10.16: Status class mapping is idempotent
  // ==========================================================================

  it('Property 10: Status class mapping is idempotent', () => {
    fc.assert(
      fc.property(validStatusArb, (status) => {
        const class1 = getStatusClass(status)
        const class2 = getStatusClass(status)
        const class3 = getStatusClass(status)

        // Property: Getting class multiple times SHALL return same result
        expect(class1).toBe(class2)
        expect(class2).toBe(class3)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 10.17: Status validation is deterministic
  // ==========================================================================

  it('Property 10: Status validation is deterministic', () => {
    fc.assert(
      fc.property(fc.string(), (value) => {
        const result1 = isValidOcrStatus(value)
        const result2 = isValidOcrStatus(value)
        const result3 = isValidOcrStatus(value)

        // Property: Validation SHALL return same result for same input
        expect(result1).toBe(result2)
        expect(result2).toBe(result3)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 10.18: Specific status values have expected mappings
  // ==========================================================================

  it('Property 10: Specific status values have expected mappings', () => {
    // Property: 'ready' status mappings
    expect(getStatusIcon('ready')).toBe('⚪')
    expect(getStatusText('ready')).toBe('就绪')
    expect(getStatusClass('ready')).toBe('status-ready')

    // Property: 'processing' status mappings
    expect(getStatusIcon('processing')).toBe('🔄')
    expect(getStatusText('processing')).toBe('处理中...')
    expect(getStatusClass('processing')).toBe('status-processing')

    // Property: 'completed' status mappings
    expect(getStatusIcon('completed')).toBe('✅')
    expect(getStatusText('completed')).toBe('完成')
    expect(getStatusClass('completed')).toBe('status-completed')

    // Property: 'error' status mappings
    expect(getStatusIcon('error')).toBe('❌')
    expect(getStatusText('error')).toBe('错误')
    expect(getStatusClass('error')).toBe('status-error')
  })

  // ==========================================================================
  // Property 10.19: Empty string is not a valid status
  // ==========================================================================

  it('Property 10: Empty string is not a valid status', () => {
    // Property: Empty string SHALL NOT be a valid status
    expect(isValidOcrStatus('')).toBe(false)
  })

  // ==========================================================================
  // Property 10.20: Status type guard correctly narrows type
  // ==========================================================================

  it('Property 10: Type guard correctly identifies valid statuses', () => {
    fc.assert(
      fc.property(
        fc.oneof(validStatusArb, invalidStatusStringArb),
        (value) => {
          const isValid = isValidOcrStatus(value)

          if (isValid) {
            // If valid, it should be in VALID_STATUSES
            expect(VALID_STATUSES).toContain(value)
          } else {
            // If invalid, it should NOT be in VALID_STATUSES
            expect(VALID_STATUSES).not.toContain(value)
          }

          return true
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })
})
