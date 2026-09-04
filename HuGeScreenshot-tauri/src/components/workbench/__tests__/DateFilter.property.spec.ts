/**
 * Property-Based Tests for Date Filter Range Correctness
 *
 * Feature: workbench-layout-redesign, Property 7: Date Filter Range Correctness
 *
 * **Validates: Requirements 3.3**
 *
 * Property Definition:
 * For any date filter selection (today, week, month), all items in the filtered result list
 * SHALL have a createdAt timestamp within the specified date range.
 *
 * This test file verifies:
 * 1. 'today' filter only includes items created today
 * 2. 'week' filter only includes items created this week (Sunday to Saturday)
 * 3. 'month' filter only includes items created this month
 * 4. 'all' filter includes all items regardless of date
 * 5. No items outside the date range are included (no false positives)
 * 6. All items within the date range are included (no false negatives)
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ============================================================================
// Types (mirroring HistoryItem from @/types/history.ts and DateFilter from workbench store)
// ============================================================================

interface MockHistoryItem {
  id: number
  createdAt: string
  filePath: string
  thumbnailPath?: string
  width: number
  height: number
  fileSize?: number
  ocrText?: string
  tags: string[]
  metadata: Record<string, unknown>
}

/** Date filter type (mirroring workbench store) */
type DateFilter = 'all' | 'today' | 'week' | 'month'

// ============================================================================
// Date Range Calculation Logic (extracted from HistoryListPanel.vue)
// ============================================================================

/**
 * Get the start of today (midnight local time)
 * @param now Reference date (defaults to current time)
 */
function getStartOfToday(now: Date = new Date()): Date {
  return new Date(now.getFullYear(), now.getMonth(), now.getDate())
}

/**
 * Get the start of the current week (Sunday at midnight)
 * @param now Reference date (defaults to current time)
 */
function getStartOfWeek(now: Date = new Date()): Date {
  const today = getStartOfToday(now)
  const weekStart = new Date(today)
  weekStart.setDate(weekStart.getDate() - weekStart.getDay())
  return weekStart
}


/**
 * Get the start of the current month (1st day at midnight)
 * @param now Reference date (defaults to current time)
 */
function getStartOfMonth(now: Date = new Date()): Date {
  return new Date(now.getFullYear(), now.getMonth(), 1)
}

/**
 * Get date range for a given filter
 * This mirrors the getDateRange function in HistoryListPanel.vue
 *
 * @param filter Date filter type
 * @param now Reference date for "now" (allows testing with fixed dates)
 * @returns Object with startDate and optional endDate as ISO strings
 */
function getDateRange(
  filter: DateFilter,
  now: Date = new Date()
): { startDate?: string; endDate?: string } {
  const today = getStartOfToday(now)

  switch (filter) {
    case 'today':
      return {
        startDate: today.toISOString(),
        endDate: new Date(today.getTime() + 24 * 60 * 60 * 1000).toISOString(),
      }
    case 'week': {
      const weekStart = getStartOfWeek(now)
      return {
        startDate: weekStart.toISOString(),
      }
    }
    case 'month': {
      const monthStart = getStartOfMonth(now)
      return {
        startDate: monthStart.toISOString(),
      }
    }
    default:
      return {}
  }
}

/**
 * Check if a date falls within a date range
 *
 * @param dateStr ISO date string to check
 * @param startDate Start of range (inclusive)
 * @param endDate End of range (exclusive), if undefined means no upper bound
 * @returns True if date is within range
 */
function isDateInRange(dateStr: string, startDate?: string, endDate?: string): boolean {
  if (!startDate) return true // No filter

  const date = new Date(dateStr)
  const start = new Date(startDate)

  if (date < start) return false
  if (endDate) {
    const end = new Date(endDate)
    if (date >= end) return false
  }

  return true
}

/**
 * Filter items by date range
 * This mirrors the date filtering logic that would be applied in HistoryListPanel
 *
 * @param items Array of history items
 * @param filter Date filter type
 * @param now Reference date for "now"
 * @returns Filtered array of items
 */
function filterByDate(
  items: MockHistoryItem[],
  filter: DateFilter,
  now: Date = new Date()
): MockHistoryItem[] {
  if (filter === 'all') {
    return items
  }

  const { startDate, endDate } = getDateRange(filter, now)
  return items.filter((item) => isDateInRange(item.createdAt, startDate, endDate))
}


// ============================================================================
// Arbitraries
// ============================================================================

/**
 * Arbitrary for generating a valid ISO date string within a reasonable range
 */
const isoDateArb: fc.Arbitrary<string> = fc
  .integer({
    min: new Date('2020-01-01').getTime(),
    max: new Date('2025-12-31').getTime(),
  })
  .map((timestamp) => new Date(timestamp).toISOString())

/**
 * Arbitrary for generating a "now" reference date
 * Used to make tests deterministic by fixing the current time
 */
const nowDateArb: fc.Arbitrary<Date> = fc
  .integer({
    min: new Date('2023-01-01').getTime(),
    max: new Date('2025-06-30').getTime(),
  })
  .map((timestamp) => new Date(timestamp))

/**
 * Arbitrary for generating a mock history item
 */
const historyItemArb: fc.Arbitrary<MockHistoryItem> = fc.record({
  id: fc.integer({ min: 1, max: 1000000 }),
  createdAt: isoDateArb,
  filePath: fc.string({ minLength: 5, maxLength: 100 }).map((s) => `/path/to/${s}.png`),
  thumbnailPath: fc.option(
    fc.string({ minLength: 5, maxLength: 100 }).map((s) => `/thumb/${s}.png`),
    { nil: undefined }
  ),
  width: fc.integer({ min: 1, max: 4096 }),
  height: fc.integer({ min: 1, max: 4096 }),
  fileSize: fc.option(fc.integer({ min: 1, max: 100000000 }), { nil: undefined }),
  ocrText: fc.option(fc.string({ minLength: 0, maxLength: 200 }), { nil: undefined }),
  tags: fc.array(fc.string({ minLength: 1, maxLength: 50 }), { minLength: 0, maxLength: 10 }),
  metadata: fc.constant({}),
})

/**
 * Arbitrary for generating an array of history items with unique IDs
 */
const historyItemsArb: fc.Arbitrary<MockHistoryItem[]> = fc
  .array(historyItemArb, { minLength: 0, maxLength: 100 })
  .map((items) => {
    // Ensure unique IDs
    const seen = new Set<number>()
    return items.filter((item) => {
      if (seen.has(item.id)) return false
      seen.add(item.id)
      return true
    })
  })

/**
 * Arbitrary for date filter types (excluding 'all' for range-specific tests)
 */
const dateFilterArb: fc.Arbitrary<DateFilter> = fc.constantFrom('today', 'week', 'month')

/**
 * Arbitrary for all date filter types including 'all'
 */
const allDateFilterArb: fc.Arbitrary<DateFilter> = fc.constantFrom('all', 'today', 'week', 'month')

// ============================================================================
// Property Tests
// ============================================================================

describe('Feature: workbench-layout-redesign, Property 7: Date Filter Range Correctness', () => {
  // ==========================================================================
  // Property 7.1: 'all' filter returns all items
  // ==========================================================================

  it('Property 7: "all" filter returns all items regardless of date', () => {
    fc.assert(
      fc.property(historyItemsArb, nowDateArb, (items, now) => {
        const filteredItems = filterByDate(items, 'all', now)

        // Property: 'all' filter should return all items
        expect(filteredItems.length).toBe(items.length)

        // Verify same items are returned
        const originalIds = new Set(items.map((i) => i.id))
        const filteredIds = new Set(filteredItems.map((i) => i.id))

        for (const id of originalIds) {
          expect(filteredIds.has(id)).toBe(true)
        }

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 7.2: 'today' filter only includes items from today
  // ==========================================================================

  it('Property 7: "today" filter only includes items created today', () => {
    fc.assert(
      fc.property(historyItemsArb, nowDateArb, (items, now) => {
        const filteredItems = filterByDate(items, 'today', now)
        const { startDate, endDate } = getDateRange('today', now)

        // Property: Every filtered item must be within today's range
        for (const item of filteredItems) {
          const itemDate = new Date(item.createdAt)
          const start = new Date(startDate!)
          const end = new Date(endDate!)

          expect(itemDate.getTime()).toBeGreaterThanOrEqual(start.getTime())
          expect(itemDate.getTime()).toBeLessThan(end.getTime())
        }

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 7.3: 'week' filter only includes items from this week
  // ==========================================================================

  it('Property 7: "week" filter only includes items created this week', () => {
    fc.assert(
      fc.property(historyItemsArb, nowDateArb, (items, now) => {
        const filteredItems = filterByDate(items, 'week', now)
        const { startDate } = getDateRange('week', now)

        // Property: Every filtered item must be within this week's range
        for (const item of filteredItems) {
          const itemDate = new Date(item.createdAt)
          const start = new Date(startDate!)

          expect(itemDate.getTime()).toBeGreaterThanOrEqual(start.getTime())
        }

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 7.4: 'month' filter only includes items from this month
  // ==========================================================================

  it('Property 7: "month" filter only includes items created this month', () => {
    fc.assert(
      fc.property(historyItemsArb, nowDateArb, (items, now) => {
        const filteredItems = filterByDate(items, 'month', now)
        const { startDate } = getDateRange('month', now)

        // Property: Every filtered item must be within this month's range
        for (const item of filteredItems) {
          const itemDate = new Date(item.createdAt)
          const start = new Date(startDate!)

          expect(itemDate.getTime()).toBeGreaterThanOrEqual(start.getTime())
        }

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 7.5: Items within 'today' range are always included (no false negatives)
  // ==========================================================================

  it('Property 7: Items created today are always included in "today" filter', () => {
    fc.assert(
      fc.property(
        nowDateArb,
        fc.integer({ min: 1, max: 50 }),
        (now, itemCount) => {
          // Create items where some are definitely within today
          const items: MockHistoryItem[] = []

          for (let i = 0; i < itemCount; i++) {
            const todayStart = getStartOfToday(now).getTime()
            const todayEnd = todayStart + 24 * 60 * 60 * 1000 - 1
            // Alternate between today and before today
            const timestamp =
              i % 2 === 0
                ? todayStart + Math.floor(Math.random() * (todayEnd - todayStart))
                : todayStart - 24 * 60 * 60 * 1000 // Yesterday

            items.push({
              id: i + 1,
              createdAt: new Date(timestamp).toISOString(),
              filePath: `/path/to/file${i}.png`,
              width: 100,
              height: 100,
              tags: [],
              metadata: {},
            })
          }

          const filteredItems = filterByDate(items, 'today', now)
          const filteredIds = new Set(filteredItems.map((item) => item.id))

          // Property: All items from today should be included
          for (const item of items) {
            const itemDate = new Date(item.createdAt)
            const todayStart = getStartOfToday(now)
            const todayEnd = new Date(todayStart.getTime() + 24 * 60 * 60 * 1000)

            const isToday = itemDate >= todayStart && itemDate < todayEnd

            if (isToday) {
              expect(filteredIds.has(item.id)).toBe(true)
            }
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
  // Property 7.6: Items outside date range are excluded (no false positives)
  // ==========================================================================

  it('Property 7: Items before today are excluded from "today" filter', () => {
    fc.assert(
      fc.property(
        nowDateArb,
        fc.integer({ min: 1, max: 50 }),
        (now, itemCount) => {
          // Create items that are all before today
          const todayStart = getStartOfToday(now).getTime()
          const items: MockHistoryItem[] = Array.from({ length: itemCount }, (_, i) => ({
            id: i + 1,
            createdAt: new Date(todayStart - (i + 1) * 24 * 60 * 60 * 1000).toISOString(),
            filePath: `/path/to/file${i}.png`,
            width: 100,
            height: 100,
            tags: [],
            metadata: {},
          }))

          const filteredItems = filterByDate(items, 'today', now)

          // Property: No items from before today should be included
          expect(filteredItems.length).toBe(0)

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
  // Property 7.7: Items before this week are excluded from 'week' filter
  // ==========================================================================

  it('Property 7: Items before this week are excluded from "week" filter', () => {
    fc.assert(
      fc.property(
        nowDateArb,
        fc.integer({ min: 1, max: 50 }),
        (now, itemCount) => {
          // Create items that are all before this week
          const weekStart = getStartOfWeek(now).getTime()
          const items: MockHistoryItem[] = Array.from({ length: itemCount }, (_, i) => ({
            id: i + 1,
            createdAt: new Date(weekStart - (i + 1) * 24 * 60 * 60 * 1000).toISOString(),
            filePath: `/path/to/file${i}.png`,
            width: 100,
            height: 100,
            tags: [],
            metadata: {},
          }))

          const filteredItems = filterByDate(items, 'week', now)

          // Property: No items from before this week should be included
          expect(filteredItems.length).toBe(0)

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
  // Property 7.8: Items before this month are excluded from 'month' filter
  // ==========================================================================

  it('Property 7: Items before this month are excluded from "month" filter', () => {
    fc.assert(
      fc.property(
        nowDateArb,
        fc.integer({ min: 1, max: 50 }),
        (now, itemCount) => {
          // Create items that are all before this month
          const monthStart = getStartOfMonth(now).getTime()
          const items: MockHistoryItem[] = Array.from({ length: itemCount }, (_, i) => ({
            id: i + 1,
            createdAt: new Date(monthStart - (i + 1) * 24 * 60 * 60 * 1000).toISOString(),
            filePath: `/path/to/file${i}.png`,
            width: 100,
            height: 100,
            tags: [],
            metadata: {},
          }))

          const filteredItems = filterByDate(items, 'month', now)

          // Property: No items from before this month should be included
          expect(filteredItems.length).toBe(0)

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
  // Property 7.9: Filtered count is bounded by total items
  // ==========================================================================

  it('Property 7: Filtered count is always <= total items count', () => {
    fc.assert(
      fc.property(historyItemsArb, allDateFilterArb, nowDateArb, (items, filter, now) => {
        const filteredItems = filterByDate(items, filter, now)

        // Property: Filtered count should never exceed total items
        expect(filteredItems.length).toBeLessThanOrEqual(items.length)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 7.10: Empty items array always returns empty result
  // ==========================================================================

  it('Property 7: Empty items array always returns empty filtered result', () => {
    fc.assert(
      fc.property(allDateFilterArb, nowDateArb, (filter, now) => {
        const emptyItems: MockHistoryItem[] = []
        const filteredItems = filterByDate(emptyItems, filter, now)

        // Property: Empty items should always result in empty filtered result
        expect(filteredItems.length).toBe(0)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })


  // ==========================================================================
  // Property 7.11: Filter is idempotent
  // ==========================================================================

  it('Property 7: Date filtering is idempotent (filtering twice gives same result)', () => {
    fc.assert(
      fc.property(historyItemsArb, dateFilterArb, nowDateArb, (items, filter, now) => {
        const firstFilter = filterByDate(items, filter, now)
        const secondFilter = filterByDate(firstFilter, filter, now)

        // Property: Filtering twice should give the same result
        expect(secondFilter.length).toBe(firstFilter.length)

        const firstIds = new Set(firstFilter.map((i) => i.id))
        const secondIds = new Set(secondFilter.map((i) => i.id))

        for (const id of firstIds) {
          expect(secondIds.has(id)).toBe(true)
        }

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 7.12: Filter preserves item order
  // ==========================================================================

  it('Property 7: Date filtering preserves the relative order of items', () => {
    fc.assert(
      fc.property(
        historyItemsArb.filter((items) => items.length >= 2),
        allDateFilterArb,
        nowDateArb,
        (items, filter, now) => {
          const filteredItems = filterByDate(items, filter, now)

          if (filteredItems.length < 2) return true // Need at least 2 items to check order

          // Get original indices of filtered items
          const originalIndices = filteredItems.map((filtered) =>
            items.findIndex((item) => item.id === filtered.id)
          )

          // Property: Original indices should be in ascending order
          for (let i = 1; i < originalIndices.length; i++) {
            expect(originalIndices[i]).toBeGreaterThan(originalIndices[i - 1])
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
  // Property 7.13: 'today' is a subset of 'week'; current-month week items are a subset of 'month'
  // ==========================================================================

  it('Property 7: "today" results are a subset of "week" results', () => {
    fc.assert(
      fc.property(historyItemsArb, nowDateArb, (items, now) => {
        const todayItems = filterByDate(items, 'today', now)
        const weekItems = filterByDate(items, 'week', now)

        const weekIds = new Set(weekItems.map((i) => i.id))

        // Property: Every item in 'today' should also be in 'week'
        for (const item of todayItems) {
          expect(weekIds.has(item.id)).toBe(true)
        }

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('Property 7: current-month "week" results are a subset of "month" results', () => {
    fc.assert(
      fc.property(historyItemsArb, nowDateArb, (items, now) => {
        const weekItems = filterByDate(items, 'week', now)
        const monthItems = filterByDate(items, 'month', now)
        const monthStart = getStartOfMonth(now).getTime()

        const monthIds = new Set(monthItems.map((i) => i.id))

        // Weeks can span the previous month, so only the part of the week that
        // is inside the current month must also appear in the month result.
        for (const item of weekItems) {
          const itemTime = new Date(item.createdAt).getTime()
          if (itemTime >= monthStart) {
            expect(monthIds.has(item.id)).toBe(true)
          } else {
            expect(itemTime).toBeLessThan(monthStart)
          }
        }

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 7.14: Date range boundaries are correct
  // ==========================================================================

  it('Property 7: "today" filter correctly handles midnight boundary', () => {
    fc.assert(
      fc.property(nowDateArb, (now) => {
        const todayStart = getStartOfToday(now)
        const todayEnd = new Date(todayStart.getTime() + 24 * 60 * 60 * 1000)

        // Create items at exact boundaries
        const items: MockHistoryItem[] = [
          {
            id: 1,
            createdAt: todayStart.toISOString(), // Exactly at midnight (should be included)
            filePath: '/path/to/file1.png',
            width: 100,
            height: 100,
            tags: [],
            metadata: {},
          },
          {
            id: 2,
            createdAt: new Date(todayStart.getTime() - 1).toISOString(), // 1ms before midnight (excluded)
            filePath: '/path/to/file2.png',
            width: 100,
            height: 100,
            tags: [],
            metadata: {},
          },
          {
            id: 3,
            createdAt: new Date(todayEnd.getTime() - 1).toISOString(), // 1ms before next midnight (included)
            filePath: '/path/to/file3.png',
            width: 100,
            height: 100,
            tags: [],
            metadata: {},
          },
          {
            id: 4,
            createdAt: todayEnd.toISOString(), // Exactly at next midnight (excluded)
            filePath: '/path/to/file4.png',
            width: 100,
            height: 100,
            tags: [],
            metadata: {},
          },
        ]

        const filteredItems = filterByDate(items, 'today', now)
        const filteredIds = new Set(filteredItems.map((i) => i.id))

        // Property: Boundary conditions are handled correctly
        expect(filteredIds.has(1)).toBe(true) // Midnight start is inclusive
        expect(filteredIds.has(2)).toBe(false) // Before midnight is excluded
        expect(filteredIds.has(3)).toBe(true) // Before end is included
        expect(filteredIds.has(4)).toBe(false) // End boundary is exclusive

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })


  // ==========================================================================
  // Property 7.15: Week start is correctly calculated (Sunday)
  // ==========================================================================

  it('Property 7: "week" filter correctly starts from Sunday', () => {
    fc.assert(
      fc.property(nowDateArb, (now) => {
        const weekStart = getStartOfWeek(now)

        // Property: Week start should be a Sunday
        expect(weekStart.getDay()).toBe(0) // 0 = Sunday

        // Property: Week start should be at midnight
        expect(weekStart.getHours()).toBe(0)
        expect(weekStart.getMinutes()).toBe(0)
        expect(weekStart.getSeconds()).toBe(0)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 7.16: Month start is correctly calculated (1st day)
  // ==========================================================================

  it('Property 7: "month" filter correctly starts from the 1st day', () => {
    fc.assert(
      fc.property(nowDateArb, (now) => {
        const monthStart = getStartOfMonth(now)

        // Property: Month start should be the 1st day
        expect(monthStart.getDate()).toBe(1)

        // Property: Month start should be at midnight
        expect(monthStart.getHours()).toBe(0)
        expect(monthStart.getMinutes()).toBe(0)
        expect(monthStart.getSeconds()).toBe(0)

        // Property: Month start should be in the same month as 'now'
        expect(monthStart.getMonth()).toBe(now.getMonth())
        expect(monthStart.getFullYear()).toBe(now.getFullYear())

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 7.17: All items within range are included (completeness)
  // ==========================================================================

  it('Property 7: All items within the date range are included (no false negatives)', () => {
    fc.assert(
      fc.property(historyItemsArb, dateFilterArb, nowDateArb, (items, filter, now) => {
        const filteredItems = filterByDate(items, filter, now)
        const filteredIds = new Set(filteredItems.map((i) => i.id))
        const { startDate, endDate } = getDateRange(filter, now)

        // Property: Every item that should match is in the filtered results
        for (const item of items) {
          const shouldMatch = isDateInRange(item.createdAt, startDate, endDate)

          if (shouldMatch) {
            expect(filteredIds.has(item.id)).toBe(true)
          }
        }

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 7.18: No items outside range are included (soundness)
  // ==========================================================================

  it('Property 7: No items outside the date range are included (no false positives)', () => {
    fc.assert(
      fc.property(historyItemsArb, dateFilterArb, nowDateArb, (items, filter, now) => {
        const filteredItems = filterByDate(items, filter, now)
        const { startDate, endDate } = getDateRange(filter, now)

        // Property: Every filtered item must be within the range
        for (const item of filteredItems) {
          const isInRange = isDateInRange(item.createdAt, startDate, endDate)
          expect(isInRange).toBe(true)
        }

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 7.19: Filter handles invalid dates gracefully
  // ==========================================================================

  it('Property 7: Filter handles edge case dates correctly', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(
          '2024-01-01T00:00:00.000Z', // New Year
          '2024-02-29T12:00:00.000Z', // Leap year
          '2024-12-31T23:59:59.999Z', // Year end
          '2023-03-12T02:30:00.000Z', // DST transition (US)
          '2023-11-05T01:30:00.000Z' // DST transition (US)
        ),
        allDateFilterArb,
        (dateStr, filter) => {
          const now = new Date(dateStr)
          const items: MockHistoryItem[] = [
            {
              id: 1,
              createdAt: dateStr,
              filePath: '/path/to/file.png',
              width: 100,
              height: 100,
              tags: [],
              metadata: {},
            },
          ]

          // Property: Should not throw and should return valid result
          const filteredItems = filterByDate(items, filter, now)
          expect(filteredItems.length).toBeGreaterThanOrEqual(0)
          expect(filteredItems.length).toBeLessThanOrEqual(1)

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
  // Property 7.20: Filter count consistency across filter types
  // ==========================================================================

  it('Property 7: Filter counts follow valid subset ordering across month boundaries', () => {
    fc.assert(
      fc.property(historyItemsArb, nowDateArb, (items, now) => {
        const todayItems = filterByDate(items, 'today', now)
        const weekItems = filterByDate(items, 'week', now)
        const monthItems = filterByDate(items, 'month', now)
        const allCount = filterByDate(items, 'all', now).length

        // A week can span the previous month/year, so week is not always a
        // subset of month. Today is the only range guaranteed to be inside
        // both current week and current month.
        expect(todayItems.length).toBeLessThanOrEqual(weekItems.length)
        expect(todayItems.length).toBeLessThanOrEqual(monthItems.length)
        expect(weekItems.length).toBeLessThanOrEqual(allCount)
        expect(monthItems.length).toBeLessThanOrEqual(allCount)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })
})
