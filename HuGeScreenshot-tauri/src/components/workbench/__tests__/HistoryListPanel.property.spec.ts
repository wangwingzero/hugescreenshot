/**
 * Property-Based Tests for HistoryListPanel Virtual Scrolling
 *
 * Feature: workbench-layout-redesign, Property 3: Virtual Scrolling Renders Only Visible Items
 *
 * **Validates: Requirements 2.3**
 *
 * Property Definition:
 * For any scroll position in the history list, only items within the visible viewport
 * (plus a small buffer) SHALL be rendered in the DOM.
 *
 * This test file verifies:
 * 1. Given any scroll position and container height, only the correct subset of items is rendered
 * 2. The number of rendered items is bounded by (visibleCount + 2 * BUFFER_SIZE)
 * 3. The startIndex and endIndex calculations are correct for any scroll position
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ============================================================================
// Virtual Scrolling Constants (from HistoryListPanel.vue)
// ============================================================================

/** Height of each item in pixels */
const ITEM_HEIGHT = 80

/** Number of buffer items to render above and below the visible area */
const BUFFER_SIZE = 5

// ============================================================================
// Virtual Scrolling Logic (extracted from HistoryListPanel.vue)
// ============================================================================

/**
 * Calculate the start index for visible items
 * This mirrors the logic in HistoryListPanel.vue
 *
 * @param scrollTop - Current scroll position in pixels
 * @returns Start index for slicing the items array
 */
function calculateStartIndex(scrollTop: number): number {
  const index = Math.floor(scrollTop / ITEM_HEIGHT)
  return Math.max(0, index - BUFFER_SIZE)
}

/**
 * Calculate the number of visible items (including buffer)
 * This mirrors the logic in HistoryListPanel.vue
 *
 * @param containerHeight - Height of the visible container in pixels
 * @returns Number of items to render
 */
function calculateVisibleCount(containerHeight: number): number {
  return Math.ceil(containerHeight / ITEM_HEIGHT) + BUFFER_SIZE * 2
}

/**
 * Calculate the end index for visible items
 *
 * @param startIndex - Start index from calculateStartIndex
 * @param visibleCount - Visible count from calculateVisibleCount
 * @param totalItems - Total number of items in the list
 * @returns End index for slicing the items array
 */
function calculateEndIndex(startIndex: number, visibleCount: number, totalItems: number): number {
  return Math.min(startIndex + visibleCount, totalItems)
}

/**
 * Get the visible items for a given scroll state
 *
 * @param items - Array of all items
 * @param scrollTop - Current scroll position in pixels
 * @param containerHeight - Height of the visible container in pixels
 * @returns Array of visible items
 */
function getVisibleItems<T>(items: T[], scrollTop: number, containerHeight: number): T[] {
  const startIndex = calculateStartIndex(scrollTop)
  const visibleCount = calculateVisibleCount(containerHeight)
  const endIndex = calculateEndIndex(startIndex, visibleCount, items.length)
  return items.slice(startIndex, endIndex)
}

/**
 * Calculate the total scrollable height
 *
 * @param totalItems - Total number of items
 * @returns Total height in pixels
 */
function calculateTotalHeight(totalItems: number): number {
  return totalItems * ITEM_HEIGHT
}

/**
 * Calculate the Y offset for positioning the visible list
 *
 * @param startIndex - Start index of visible items
 * @returns Y offset in pixels
 */
function calculateOffsetY(startIndex: number): number {
  return startIndex * ITEM_HEIGHT
}

// ============================================================================
// Arbitraries
// ============================================================================

/**
 * Arbitrary for container heights (typical viewport sizes)
 */
const containerHeightArb: fc.Arbitrary<number> = fc.integer({
  min: 100, // Minimum reasonable container height
  max: 2000, // Maximum reasonable container height (large monitor)
})

/**
 * Arbitrary for total item counts
 */
const totalItemsArb: fc.Arbitrary<number> = fc.integer({
  min: 0,
  max: 10000, // Large list for stress testing
})

/**
 * Arbitrary for scroll positions (will be constrained based on total items)
 */
const scrollPositionArb: fc.Arbitrary<number> = fc.integer({
  min: 0,
  max: 1000000, // Will be clamped to valid range in tests
})

/**
 * Generate a mock item with an ID
 */
interface MockItem {
  id: number
  data: string
}

/**
 * Generate an array of mock items
 */
function generateMockItems(count: number): MockItem[] {
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    data: `Item ${i + 1}`,
  }))
}

// ============================================================================
// Property Tests
// ============================================================================

describe('Feature: workbench-layout-redesign, Property 3: Virtual Scrolling Renders Only Visible Items', () => {
  // ==========================================================================
  // Property 3.1: Rendered items count is bounded
  // ==========================================================================

  it('Property 3: Virtual scrolling renders bounded number of items for any scroll position', () => {
    fc.assert(
      fc.property(
        totalItemsArb,
        containerHeightArb,
        scrollPositionArb,
        (totalItems, containerHeight, scrollTop) => {
          // Skip empty lists
          if (totalItems === 0) return true

          // Clamp scroll position to valid range
          const maxScroll = Math.max(0, calculateTotalHeight(totalItems) - containerHeight)
          const clampedScrollTop = Math.min(scrollTop, maxScroll)

          // Generate mock items
          const items = generateMockItems(totalItems)

          // Get visible items
          const visibleItems = getVisibleItems(items, clampedScrollTop, containerHeight)

          // Calculate the maximum expected visible items
          const visibleCount = calculateVisibleCount(containerHeight)

          // Property: Number of rendered items should never exceed visibleCount
          // and should never exceed total items
          const maxExpectedItems = Math.min(visibleCount, totalItems)
          expect(visibleItems.length).toBeLessThanOrEqual(maxExpectedItems)

          // Property: Should always render at least 1 item if list is not empty
          expect(visibleItems.length).toBeGreaterThanOrEqual(1)

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
  // Property 3.2: Visible items are within viewport bounds
  // ==========================================================================

  it('Property 3: Visible items are within viewport bounds (plus buffer)', () => {
    fc.assert(
      fc.property(
        totalItemsArb.filter((n) => n > 0), // Non-empty lists only
        containerHeightArb,
        scrollPositionArb,
        (totalItems, containerHeight, scrollTop) => {
          // Clamp scroll position to valid range
          const maxScroll = Math.max(0, calculateTotalHeight(totalItems) - containerHeight)
          const clampedScrollTop = Math.min(scrollTop, maxScroll)

          // Calculate indices
          const startIndex = calculateStartIndex(clampedScrollTop)
          const visibleCount = calculateVisibleCount(containerHeight)
          const endIndex = calculateEndIndex(startIndex, visibleCount, totalItems)

          // Calculate the theoretical visible range without buffer
          const firstVisibleIndex = Math.floor(clampedScrollTop / ITEM_HEIGHT)
          const lastVisibleIndex = Math.ceil((clampedScrollTop + containerHeight) / ITEM_HEIGHT) - 1

          // Property: startIndex should be at most BUFFER_SIZE items before the first visible item
          expect(startIndex).toBeLessThanOrEqual(firstVisibleIndex)
          expect(startIndex).toBeGreaterThanOrEqual(Math.max(0, firstVisibleIndex - BUFFER_SIZE))

          // Property: endIndex should be at least the last visible item
          // (accounting for buffer and total items limit)
          const expectedMinEndIndex = Math.min(lastVisibleIndex + 1, totalItems)
          expect(endIndex).toBeGreaterThanOrEqual(expectedMinEndIndex)

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
  // Property 3.3: Start index calculation is correct
  // ==========================================================================

  it('Property 3: Start index is correctly calculated for any scroll position', () => {
    fc.assert(
      fc.property(
        scrollPositionArb,
        (scrollTop) => {
          const startIndex = calculateStartIndex(scrollTop)

          // Property: startIndex should never be negative
          expect(startIndex).toBeGreaterThanOrEqual(0)

          // Property: startIndex should be based on scroll position
          const expectedBaseIndex = Math.floor(scrollTop / ITEM_HEIGHT)
          const expectedStartIndex = Math.max(0, expectedBaseIndex - BUFFER_SIZE)
          expect(startIndex).toBe(expectedStartIndex)

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
  // Property 3.4: Visible count calculation is correct
  // ==========================================================================

  it('Property 3: Visible count is correctly calculated for any container height', () => {
    fc.assert(
      fc.property(
        containerHeightArb,
        (containerHeight) => {
          const visibleCount = calculateVisibleCount(containerHeight)

          // Property: visibleCount should be positive
          expect(visibleCount).toBeGreaterThan(0)

          // Property: visibleCount should include buffer on both sides
          const baseVisibleCount = Math.ceil(containerHeight / ITEM_HEIGHT)
          const expectedVisibleCount = baseVisibleCount + BUFFER_SIZE * 2
          expect(visibleCount).toBe(expectedVisibleCount)

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
  // Property 3.5: End index never exceeds total items
  // ==========================================================================

  it('Property 3: End index never exceeds total items count', () => {
    fc.assert(
      fc.property(
        totalItemsArb,
        containerHeightArb,
        scrollPositionArb,
        (totalItems, containerHeight, scrollTop) => {
          const startIndex = calculateStartIndex(scrollTop)
          const visibleCount = calculateVisibleCount(containerHeight)
          const endIndex = calculateEndIndex(startIndex, visibleCount, totalItems)

          // Property: endIndex should never exceed totalItems
          expect(endIndex).toBeLessThanOrEqual(totalItems)

          // Property: endIndex should be non-negative
          expect(endIndex).toBeGreaterThanOrEqual(0)

          // Property: For non-empty lists, endIndex should be at least startIndex
          // For empty lists (totalItems=0), both startIndex and endIndex can be 0
          if (totalItems > 0) {
            // startIndex is clamped to valid range, so endIndex >= min(startIndex, totalItems)
            const effectiveStartIndex = Math.min(startIndex, totalItems)
            expect(endIndex).toBeGreaterThanOrEqual(effectiveStartIndex)
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

  // ==========================================================================
  // Property 3.6: Offset Y is correctly calculated
  // ==========================================================================

  it('Property 3: Offset Y is correctly calculated for positioning', () => {
    fc.assert(
      fc.property(
        scrollPositionArb,
        (scrollTop) => {
          const startIndex = calculateStartIndex(scrollTop)
          const offsetY = calculateOffsetY(startIndex)

          // Property: offsetY should be non-negative
          expect(offsetY).toBeGreaterThanOrEqual(0)

          // Property: offsetY should equal startIndex * ITEM_HEIGHT
          expect(offsetY).toBe(startIndex * ITEM_HEIGHT)

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
  // Property 3.7: Scrolling to any position shows correct items
  // ==========================================================================

  it('Property 3: Scrolling to any position shows items that should be visible', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 10, max: 1000 }), // Reasonable item counts
        containerHeightArb,
        fc.integer({ min: 0, max: 100 }), // Target item index (will be clamped)
        (totalItems, containerHeight, targetIndex) => {
          // Clamp target index to valid range
          const clampedTargetIndex = Math.min(targetIndex, totalItems - 1)
          if (clampedTargetIndex < 0) return true

          // Calculate scroll position to show target item
          const scrollTop = clampedTargetIndex * ITEM_HEIGHT

          // Clamp scroll position to valid range
          const maxScroll = Math.max(0, calculateTotalHeight(totalItems) - containerHeight)
          const clampedScrollTop = Math.min(scrollTop, maxScroll)

          // Generate mock items
          const items = generateMockItems(totalItems)

          // Get visible items
          const visibleItems = getVisibleItems(items, clampedScrollTop, containerHeight)

          // Property: The target item should be in the visible items
          // (unless we're at the end of the list and scrolled past it)
          const targetItem = items[clampedTargetIndex]
          const isTargetVisible = visibleItems.some((item) => item.id === targetItem.id)

          // If scroll position was clamped, target might not be visible
          if (clampedScrollTop === scrollTop) {
            expect(isTargetVisible).toBe(true)
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

  // ==========================================================================
  // Property 3.8: Empty list handling
  // ==========================================================================

  it('Property 3: Empty list returns empty visible items', () => {
    fc.assert(
      fc.property(
        containerHeightArb,
        scrollPositionArb,
        (containerHeight, scrollTop) => {
          const items: MockItem[] = []
          const visibleItems = getVisibleItems(items, scrollTop, containerHeight)

          // Property: Empty list should return empty visible items
          expect(visibleItems).toHaveLength(0)

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
  // Property 3.9: Visible items are contiguous
  // ==========================================================================

  it('Property 3: Visible items are contiguous (no gaps)', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 5, max: 1000 }), // Need enough items
        containerHeightArb,
        scrollPositionArb,
        (totalItems, containerHeight, scrollTop) => {
          // Clamp scroll position
          const maxScroll = Math.max(0, calculateTotalHeight(totalItems) - containerHeight)
          const clampedScrollTop = Math.min(scrollTop, maxScroll)

          // Generate mock items
          const items = generateMockItems(totalItems)

          // Get visible items
          const visibleItems = getVisibleItems(items, clampedScrollTop, containerHeight)

          // Property: Visible items should be contiguous (IDs should be sequential)
          for (let i = 1; i < visibleItems.length; i++) {
            expect(visibleItems[i].id).toBe(visibleItems[i - 1].id + 1)
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

  // ==========================================================================
  // Property 3.10: Total height calculation is correct
  // ==========================================================================

  it('Property 3: Total height equals items count times item height', () => {
    fc.assert(
      fc.property(
        totalItemsArb,
        (totalItems) => {
          const totalHeight = calculateTotalHeight(totalItems)

          // Property: Total height should be items * ITEM_HEIGHT
          expect(totalHeight).toBe(totalItems * ITEM_HEIGHT)

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
  // Property 3.11: Scroll at boundaries works correctly
  // ==========================================================================

  it('Property 3: Scroll at boundaries (top and bottom) works correctly', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 20, max: 1000 }), // Need enough items for meaningful test
        containerHeightArb,
        (totalItems, containerHeight) => {
          const items = generateMockItems(totalItems)

          // Test scroll at top (scrollTop = 0)
          const visibleAtTop = getVisibleItems(items, 0, containerHeight)
          expect(visibleAtTop[0].id).toBe(1) // First item should be visible

          // Test scroll at bottom
          const maxScroll = Math.max(0, calculateTotalHeight(totalItems) - containerHeight)
          const visibleAtBottom = getVisibleItems(items, maxScroll, containerHeight)
          expect(visibleAtBottom[visibleAtBottom.length - 1].id).toBe(totalItems) // Last item should be visible

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
  // Property 3.12: Performance - rendered items are O(viewport) not O(total)
  // ==========================================================================

  it('Property 3: Rendered items count is independent of total items (O(viewport))', () => {
    fc.assert(
      fc.property(
        containerHeightArb,
        scrollPositionArb,
        (containerHeight, scrollTop) => {
          // Test with different total item counts
          const smallList = generateMockItems(100)
          const largeList = generateMockItems(10000)

          // Clamp scroll positions
          const maxScrollSmall = Math.max(0, calculateTotalHeight(100) - containerHeight)
          const maxScrollLarge = Math.max(0, calculateTotalHeight(10000) - containerHeight)
          const clampedScrollSmall = Math.min(scrollTop, maxScrollSmall)
          const clampedScrollLarge = Math.min(scrollTop, maxScrollLarge)

          // Get visible items for both lists
          const visibleSmall = getVisibleItems(smallList, clampedScrollSmall, containerHeight)
          const visibleLarge = getVisibleItems(largeList, clampedScrollLarge, containerHeight)

          // Property: The number of visible items should be similar regardless of total items
          // (within the bounds of the smaller list)
          const visibleCount = calculateVisibleCount(containerHeight)
          const maxExpectedSmall = Math.min(visibleCount, 100)
          const maxExpectedLarge = Math.min(visibleCount, 10000)

          expect(visibleSmall.length).toBeLessThanOrEqual(maxExpectedSmall)
          expect(visibleLarge.length).toBeLessThanOrEqual(maxExpectedLarge)

          // For large lists, visible count should be bounded by viewport, not total items
          if (10000 > visibleCount) {
            expect(visibleLarge.length).toBeLessThanOrEqual(visibleCount)
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
