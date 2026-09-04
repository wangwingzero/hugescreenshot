/**
 * Property-Based Tests for Value Clamping
 *
 * Feature: settings-enhancement
 *
 * This file tests the clamping behavior for various numeric settings:
 * - Property 5: Opacity Value Clamping (pin image and mouse highlight)
 * - Property 7: Radius Value Clamping (mouse highlight)
 * - Property 9: Timeout Value Clamping (web-to-markdown)
 * - Property 11: Update Interval Clamping
 *
 * **Validates: Requirements 3.2, 4.4, 4.5, 5.4, 8.3**
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ============================================================================
// Clamping Function Under Test
// ============================================================================

/**
 * Generic clamp function that constrains a value to a specified range.
 *
 * This is the core clamping logic used by SliderControl and other components.
 * - If value < min, return min
 * - If value > max, return max
 * - Otherwise, return value
 *
 * @param value - The input value to clamp
 * @param min - The minimum allowed value
 * @param max - The maximum allowed value
 * @returns The clamped value within [min, max]
 */
export function clampValue(value: number, min: number, max: number): number {
  if (value < min) return min
  if (value > max) return max
  return value
}

// ============================================================================
// Property 5: Opacity Value Clamping
// ============================================================================

describe('Feature: settings-enhancement, Property 5: Opacity Value Clamping', () => {
  /**
   * Property 5: Opacity Value Clamping
   *
   * For any opacity input value (pin image or mouse highlight),
   * the stored value SHALL be clamped to the range [0.1, 1.0].
   *
   * **Validates: Requirements 3.2, 4.5**
   */

  const OPACITY_MIN = 0.1
  const OPACITY_MAX = 1.0

  it('should clamp any opacity value to [0.1, 1.0] range', () => {
    fc.assert(
      fc.property(
        // Generate random numbers in a wide range [-1000, 1000]
        fc.double({ min: -1000, max: 1000, noNaN: true, noDefaultInfinity: true }),
        (inputValue: number) => {
          const clampedValue = clampValue(inputValue, OPACITY_MIN, OPACITY_MAX)

          // Property: Output is always within [0.1, 1.0]
          expect(clampedValue).toBeGreaterThanOrEqual(OPACITY_MIN)
          expect(clampedValue).toBeLessThanOrEqual(OPACITY_MAX)
        }
      ),
      {
        numRuns: 100, // Minimum 100 iterations as per spec
        verbose: true,
      }
    )
  })

  it('should preserve values already within [0.1, 1.0] range', () => {
    fc.assert(
      fc.property(
        // Generate values within the valid range
        fc.double({ min: OPACITY_MIN, max: OPACITY_MAX, noNaN: true, noDefaultInfinity: true }),
        (inputValue: number) => {
          const clampedValue = clampValue(inputValue, OPACITY_MIN, OPACITY_MAX)

          // Property: Valid values are preserved
          expect(clampedValue).toBe(inputValue)
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should clamp values below 0.1 to exactly 0.1', () => {
    fc.assert(
      fc.property(
        // Generate values below minimum
        fc.double({ min: -1000, max: OPACITY_MIN - 0.001, noNaN: true, noDefaultInfinity: true }),
        (inputValue: number) => {
          const clampedValue = clampValue(inputValue, OPACITY_MIN, OPACITY_MAX)

          // Property: Values below min are clamped to min
          expect(clampedValue).toBe(OPACITY_MIN)
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should clamp values above 1.0 to exactly 1.0', () => {
    fc.assert(
      fc.property(
        // Generate values above maximum
        fc.double({ min: OPACITY_MAX + 0.001, max: 1000, noNaN: true, noDefaultInfinity: true }),
        (inputValue: number) => {
          const clampedValue = clampValue(inputValue, OPACITY_MIN, OPACITY_MAX)

          // Property: Values above max are clamped to max
          expect(clampedValue).toBe(OPACITY_MAX)
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should handle boundary values correctly', () => {
    // Test exact boundary values
    expect(clampValue(0.1, OPACITY_MIN, OPACITY_MAX)).toBe(0.1)
    expect(clampValue(1.0, OPACITY_MIN, OPACITY_MAX)).toBe(1.0)
    expect(clampValue(0.09, OPACITY_MIN, OPACITY_MAX)).toBe(0.1)
    expect(clampValue(1.01, OPACITY_MIN, OPACITY_MAX)).toBe(1.0)
    expect(clampValue(0, OPACITY_MIN, OPACITY_MAX)).toBe(0.1)
    expect(clampValue(-0.5, OPACITY_MIN, OPACITY_MAX)).toBe(0.1)
    expect(clampValue(2.0, OPACITY_MIN, OPACITY_MAX)).toBe(1.0)
  })
})

// ============================================================================
// Property 7: Radius Value Clamping
// ============================================================================

describe('Feature: settings-enhancement, Property 7: Radius Value Clamping', () => {
  /**
   * Property 7: Radius Value Clamping
   *
   * For any mouse highlight radius input value,
   * the stored value SHALL be clamped to the range [20, 200].
   *
   * **Validates: Requirements 4.4**
   */

  const RADIUS_MIN = 20
  const RADIUS_MAX = 200

  it('should clamp any radius value to [20, 200] range', () => {
    fc.assert(
      fc.property(
        // Generate random integers in a wide range [-1000, 1000]
        fc.integer({ min: -1000, max: 1000 }),
        (inputValue: number) => {
          const clampedValue = clampValue(inputValue, RADIUS_MIN, RADIUS_MAX)

          // Property: Output is always within [20, 200]
          expect(clampedValue).toBeGreaterThanOrEqual(RADIUS_MIN)
          expect(clampedValue).toBeLessThanOrEqual(RADIUS_MAX)
        }
      ),
      {
        numRuns: 100, // Minimum 100 iterations as per spec
        verbose: true,
      }
    )
  })

  it('should preserve values already within [20, 200] range', () => {
    fc.assert(
      fc.property(
        // Generate values within the valid range
        fc.integer({ min: RADIUS_MIN, max: RADIUS_MAX }),
        (inputValue: number) => {
          const clampedValue = clampValue(inputValue, RADIUS_MIN, RADIUS_MAX)

          // Property: Valid values are preserved
          expect(clampedValue).toBe(inputValue)
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should clamp values below 20 to exactly 20', () => {
    fc.assert(
      fc.property(
        // Generate values below minimum
        fc.integer({ min: -1000, max: RADIUS_MIN - 1 }),
        (inputValue: number) => {
          const clampedValue = clampValue(inputValue, RADIUS_MIN, RADIUS_MAX)

          // Property: Values below min are clamped to min
          expect(clampedValue).toBe(RADIUS_MIN)
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should clamp values above 200 to exactly 200', () => {
    fc.assert(
      fc.property(
        // Generate values above maximum
        fc.integer({ min: RADIUS_MAX + 1, max: 1000 }),
        (inputValue: number) => {
          const clampedValue = clampValue(inputValue, RADIUS_MIN, RADIUS_MAX)

          // Property: Values above max are clamped to max
          expect(clampedValue).toBe(RADIUS_MAX)
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should handle boundary values correctly', () => {
    // Test exact boundary values
    expect(clampValue(20, RADIUS_MIN, RADIUS_MAX)).toBe(20)
    expect(clampValue(200, RADIUS_MIN, RADIUS_MAX)).toBe(200)
    expect(clampValue(19, RADIUS_MIN, RADIUS_MAX)).toBe(20)
    expect(clampValue(201, RADIUS_MIN, RADIUS_MAX)).toBe(200)
    expect(clampValue(0, RADIUS_MIN, RADIUS_MAX)).toBe(20)
    expect(clampValue(-100, RADIUS_MIN, RADIUS_MAX)).toBe(20)
    expect(clampValue(500, RADIUS_MIN, RADIUS_MAX)).toBe(200)
  })
})

// ============================================================================
// Property 9: Timeout Value Clamping
// ============================================================================

describe('Feature: settings-enhancement, Property 9: Timeout Value Clamping', () => {
  /**
   * Property 9: Timeout Value Clamping
   *
   * For any web-to-markdown timeout input value,
   * the stored value SHALL be clamped to the range [5, 120].
   *
   * **Validates: Requirements 5.4**
   */

  const TIMEOUT_MIN = 5
  const TIMEOUT_MAX = 120

  it('should clamp any timeout value to [5, 120] range', () => {
    fc.assert(
      fc.property(
        // Generate random integers in a wide range [-1000, 1000]
        fc.integer({ min: -1000, max: 1000 }),
        (inputValue: number) => {
          const clampedValue = clampValue(inputValue, TIMEOUT_MIN, TIMEOUT_MAX)

          // Property: Output is always within [5, 120]
          expect(clampedValue).toBeGreaterThanOrEqual(TIMEOUT_MIN)
          expect(clampedValue).toBeLessThanOrEqual(TIMEOUT_MAX)
        }
      ),
      {
        numRuns: 100, // Minimum 100 iterations as per spec
        verbose: true,
      }
    )
  })

  it('should preserve values already within [5, 120] range', () => {
    fc.assert(
      fc.property(
        // Generate values within the valid range
        fc.integer({ min: TIMEOUT_MIN, max: TIMEOUT_MAX }),
        (inputValue: number) => {
          const clampedValue = clampValue(inputValue, TIMEOUT_MIN, TIMEOUT_MAX)

          // Property: Valid values are preserved
          expect(clampedValue).toBe(inputValue)
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should clamp values below 5 to exactly 5', () => {
    fc.assert(
      fc.property(
        // Generate values below minimum
        fc.integer({ min: -1000, max: TIMEOUT_MIN - 1 }),
        (inputValue: number) => {
          const clampedValue = clampValue(inputValue, TIMEOUT_MIN, TIMEOUT_MAX)

          // Property: Values below min are clamped to min
          expect(clampedValue).toBe(TIMEOUT_MIN)
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should clamp values above 120 to exactly 120', () => {
    fc.assert(
      fc.property(
        // Generate values above maximum
        fc.integer({ min: TIMEOUT_MAX + 1, max: 1000 }),
        (inputValue: number) => {
          const clampedValue = clampValue(inputValue, TIMEOUT_MIN, TIMEOUT_MAX)

          // Property: Values above max are clamped to max
          expect(clampedValue).toBe(TIMEOUT_MAX)
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should handle boundary values correctly', () => {
    // Test exact boundary values
    expect(clampValue(5, TIMEOUT_MIN, TIMEOUT_MAX)).toBe(5)
    expect(clampValue(120, TIMEOUT_MIN, TIMEOUT_MAX)).toBe(120)
    expect(clampValue(4, TIMEOUT_MIN, TIMEOUT_MAX)).toBe(5)
    expect(clampValue(121, TIMEOUT_MIN, TIMEOUT_MAX)).toBe(120)
    expect(clampValue(0, TIMEOUT_MIN, TIMEOUT_MAX)).toBe(5)
    expect(clampValue(-50, TIMEOUT_MIN, TIMEOUT_MAX)).toBe(5)
    expect(clampValue(300, TIMEOUT_MIN, TIMEOUT_MAX)).toBe(120)
  })
})

// ============================================================================
// Property 11: Update Interval Clamping
// ============================================================================

describe('Feature: settings-enhancement, Property 11: Update Interval Clamping', () => {
  /**
   * Property 11: Update Interval Clamping
   *
   * For any update check interval input value,
   * the stored value SHALL be clamped to the range [1, 168].
   *
   * **Validates: Requirements 8.3**
   */

  const INTERVAL_MIN = 1
  const INTERVAL_MAX = 168 // 168 hours = 1 week

  it('should clamp any interval value to [1, 168] range', () => {
    fc.assert(
      fc.property(
        // Generate random integers in a wide range [-1000, 1000]
        fc.integer({ min: -1000, max: 1000 }),
        (inputValue: number) => {
          const clampedValue = clampValue(inputValue, INTERVAL_MIN, INTERVAL_MAX)

          // Property: Output is always within [1, 168]
          expect(clampedValue).toBeGreaterThanOrEqual(INTERVAL_MIN)
          expect(clampedValue).toBeLessThanOrEqual(INTERVAL_MAX)
        }
      ),
      {
        numRuns: 100, // Minimum 100 iterations as per spec
        verbose: true,
      }
    )
  })

  it('should preserve values already within [1, 168] range', () => {
    fc.assert(
      fc.property(
        // Generate values within the valid range
        fc.integer({ min: INTERVAL_MIN, max: INTERVAL_MAX }),
        (inputValue: number) => {
          const clampedValue = clampValue(inputValue, INTERVAL_MIN, INTERVAL_MAX)

          // Property: Valid values are preserved
          expect(clampedValue).toBe(inputValue)
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should clamp values below 1 to exactly 1', () => {
    fc.assert(
      fc.property(
        // Generate values below minimum
        fc.integer({ min: -1000, max: INTERVAL_MIN - 1 }),
        (inputValue: number) => {
          const clampedValue = clampValue(inputValue, INTERVAL_MIN, INTERVAL_MAX)

          // Property: Values below min are clamped to min
          expect(clampedValue).toBe(INTERVAL_MIN)
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should clamp values above 168 to exactly 168', () => {
    fc.assert(
      fc.property(
        // Generate values above maximum
        fc.integer({ min: INTERVAL_MAX + 1, max: 1000 }),
        (inputValue: number) => {
          const clampedValue = clampValue(inputValue, INTERVAL_MIN, INTERVAL_MAX)

          // Property: Values above max are clamped to max
          expect(clampedValue).toBe(INTERVAL_MAX)
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should handle boundary values correctly', () => {
    // Test exact boundary values
    expect(clampValue(1, INTERVAL_MIN, INTERVAL_MAX)).toBe(1)
    expect(clampValue(168, INTERVAL_MIN, INTERVAL_MAX)).toBe(168)
    expect(clampValue(0, INTERVAL_MIN, INTERVAL_MAX)).toBe(1)
    expect(clampValue(169, INTERVAL_MIN, INTERVAL_MAX)).toBe(168)
    expect(clampValue(-10, INTERVAL_MIN, INTERVAL_MAX)).toBe(1)
    expect(clampValue(500, INTERVAL_MIN, INTERVAL_MAX)).toBe(168)
  })
})

// ============================================================================
// Generic Clamping Properties
// ============================================================================

describe('Feature: settings-enhancement, Generic Clamping Properties', () => {
  /**
   * Generic properties that should hold for any clamping operation
   */

  it('should satisfy idempotence: clamp(clamp(x)) === clamp(x)', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1000, max: 1000, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -100, max: 100, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -100, max: 100, noNaN: true, noDefaultInfinity: true }),
        (value: number, a: number, b: number) => {
          // Ensure min <= max
          const min = Math.min(a, b)
          const max = Math.max(a, b)

          // Skip if min === max (degenerate case)
          if (min === max) return true

          const clampedOnce = clampValue(value, min, max)
          const clampedTwice = clampValue(clampedOnce, min, max)

          // Property: Clamping is idempotent
          expect(clampedTwice).toBe(clampedOnce)
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should satisfy monotonicity: if x <= y then clamp(x) <= clamp(y)', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1000, max: 1000, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1000, max: 1000, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -100, max: 100, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -100, max: 100, noNaN: true, noDefaultInfinity: true }),
        (x: number, y: number, a: number, b: number) => {
          // Ensure min <= max
          const min = Math.min(a, b)
          const max = Math.max(a, b)

          // Skip if min === max (degenerate case)
          if (min === max) return true

          // Ensure x <= y
          const smaller = Math.min(x, y)
          const larger = Math.max(x, y)

          const clampedSmaller = clampValue(smaller, min, max)
          const clampedLarger = clampValue(larger, min, max)

          // Property: Clamping preserves order
          expect(clampedSmaller).toBeLessThanOrEqual(clampedLarger)
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('should always return a value within [min, max] for any input', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -10000, max: 10000, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -100, max: 100, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -100, max: 100, noNaN: true, noDefaultInfinity: true }),
        (value: number, a: number, b: number) => {
          // Ensure min <= max
          const min = Math.min(a, b)
          const max = Math.max(a, b)

          // Skip if min === max (degenerate case)
          if (min === max) return true

          const clamped = clampValue(value, min, max)

          // Property: Output is always within bounds
          expect(clamped).toBeGreaterThanOrEqual(min)
          expect(clamped).toBeLessThanOrEqual(max)
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })
})
