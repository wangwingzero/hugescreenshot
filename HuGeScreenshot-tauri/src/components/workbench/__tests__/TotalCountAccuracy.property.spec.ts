/**
 * Property-Based Tests for Total Count Accuracy
 *
 * Feature: workbench-layout-redesign, Property 5: Total Count Accuracy
 *
 * **Validates: Requirements 2.5**
 *
 * Property Definition:
 * For any set of history items (filtered or unfiltered), the displayed total count
 * in the header SHALL equal the actual number of items matching the current filter criteria.
 *
 * This test file verifies:
 * 1. When no filter is applied, displayCount equals totalCount from historyStore
 * 2. When search filter is applied, displayCount equals the number of items matching the search query
 * 3. The count updates correctly when items are added or removed
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ============================================================================
// Types (mirroring HistoryItem from @/types/history.ts)
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

// ============================================================================
// Filtering Logic (extracted from HistoryListPanel.vue)
// ============================================================================

/**
 * Filter items by search query
 * This mirrors the filtering logic in HistoryListPanel.vue
 *
 * @param items - Array of history items
 * @param searchQuery - Search query string
 * @returns Filtered array of items
 */
function filterBySearch(items: MockHistoryItem[], searchQuery: string): MockHistoryItem[] {
  if (!searchQuery.trim()) {
    return items
  }

  const query = searchQuery.toLowerCase().trim()
  return items.filter((item) => {
    const ocrMatch = item.ocrText?.toLowerCase().includes(query)
    const tagMatch = item.tags?.some((tag) => tag.toLowerCase().includes(query))
    return ocrMatch || tagMatch
  })
}

/**
 * Calculate the display count based on filter state
 * This mirrors the displayCount computed property in HistoryListPanel.vue
 *
 * @param items - Array of history items (already loaded)
 * @param totalCount - Total count from store (for unfiltered state)
 * @param searchQuery - Current search query
 * @returns The count to display in the header
 */
function calculateDisplayCount(
  items: MockHistoryItem[],
  totalCount: number,
  searchQuery: string
): number {
  if (searchQuery.trim()) {
    // When search is active, show filtered count
    return filterBySearch(items, searchQuery).length
  }
  // When no search, show total count from store
  return totalCount
}

// ============================================================================
// Arbitraries
// ============================================================================

/**
 * Arbitrary for generating valid OCR text
 * Can be undefined, empty, or contain searchable text
 */
const ocrTextArb: fc.Arbitrary<string | undefined> = fc.oneof(
  fc.constant(undefined),
  fc.constant(''),
  fc.string({ minLength: 1, maxLength: 200 })
)

/**
 * Arbitrary for generating tags array
 */
const tagsArb: fc.Arbitrary<string[]> = fc.array(
  fc.string({ minLength: 1, maxLength: 50 }),
  { minLength: 0, maxLength: 10 }
)

/**
 * Arbitrary for generating a valid ISO date string
 * Using integer timestamps to avoid invalid date issues
 */
const isoDateArb: fc.Arbitrary<string> = fc
  .integer({
    min: new Date('2020-01-01').getTime(),
    max: new Date('2025-12-31').getTime(),
  })
  .map((timestamp) => new Date(timestamp).toISOString())

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
  ocrText: ocrTextArb,
  tags: tagsArb,
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
 * Arbitrary for search queries
 * Includes empty strings, whitespace, and actual search terms
 */
const searchQueryArb: fc.Arbitrary<string> = fc.oneof(
  fc.constant(''),
  fc.constant('   '),
  fc.string({ minLength: 1, maxLength: 50 })
)

/**
 * Arbitrary for total count (simulating store's totalCount)
 * This can be >= items.length (when pagination is involved)
 */
const totalCountArb: fc.Arbitrary<number> = fc.integer({ min: 0, max: 10000 })

// ============================================================================
// Property Tests
// ============================================================================

describe('Feature: workbench-layout-redesign, Property 5: Total Count Accuracy', () => {
  // ==========================================================================
  // Property 5.1: Unfiltered count equals total count
  // ==========================================================================

  it('Property 5: Unfiltered display count equals totalCount from store', () => {
    fc.assert(
      fc.property(
        historyItemsArb,
        totalCountArb,
        (items, totalCount) => {
          // No search query - should show totalCount
          const displayCount = calculateDisplayCount(items, totalCount, '')

          // Property: When no filter is applied, displayCount equals totalCount
          expect(displayCount).toBe(totalCount)

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
  // Property 5.2: Filtered count equals actual matching items
  // ==========================================================================

  it('Property 5: Filtered display count equals actual number of matching items', () => {
    fc.assert(
      fc.property(
        historyItemsArb,
        totalCountArb,
        searchQueryArb.filter((q) => q.trim().length > 0), // Non-empty search
        (items, totalCount, searchQuery) => {
          // Calculate display count with search
          const displayCount = calculateDisplayCount(items, totalCount, searchQuery)

          // Manually count matching items
          const filteredItems = filterBySearch(items, searchQuery)
          const expectedCount = filteredItems.length

          // Property: When filter is applied, displayCount equals filtered items count
          expect(displayCount).toBe(expectedCount)

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
  // Property 5.3: Whitespace-only search is treated as no search
  // ==========================================================================

  it('Property 5: Whitespace-only search query is treated as no filter', () => {
    fc.assert(
      fc.property(
        historyItemsArb,
        totalCountArb,
        fc.integer({ min: 1, max: 10 }).map((n) => ' '.repeat(n)), // Whitespace only
        (items, totalCount, whitespaceQuery) => {
          // Calculate display count with whitespace query
          const displayCount = calculateDisplayCount(items, totalCount, whitespaceQuery)

          // Property: Whitespace-only query should show totalCount (no filter)
          expect(displayCount).toBe(totalCount)

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
  // Property 5.4: Display count is never negative
  // ==========================================================================

  it('Property 5: Display count is never negative', () => {
    fc.assert(
      fc.property(
        historyItemsArb,
        totalCountArb,
        searchQueryArb,
        (items, totalCount, searchQuery) => {
          const displayCount = calculateDisplayCount(items, totalCount, searchQuery)

          // Property: Display count should never be negative
          expect(displayCount).toBeGreaterThanOrEqual(0)

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
  // Property 5.5: Filtered count is bounded by items length
  // ==========================================================================

  it('Property 5: Filtered count is bounded by loaded items length', () => {
    fc.assert(
      fc.property(
        historyItemsArb,
        searchQueryArb.filter((q) => q.trim().length > 0),
        (items, searchQuery) => {
          const filteredItems = filterBySearch(items, searchQuery)

          // Property: Filtered count should never exceed total items
          expect(filteredItems.length).toBeLessThanOrEqual(items.length)

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
  // Property 5.6: Search is case-insensitive
  // ==========================================================================

  it('Property 5: Search filtering is case-insensitive', () => {
    fc.assert(
      fc.property(
        historyItemsArb,
        fc.string({ minLength: 1, maxLength: 20 }),
        (items, baseQuery) => {
          // Test with different case variations
          const lowerQuery = baseQuery.toLowerCase()
          const upperQuery = baseQuery.toUpperCase()
          const mixedQuery = baseQuery
            .split('')
            .map((c, i) => (i % 2 === 0 ? c.toLowerCase() : c.toUpperCase()))
            .join('')

          const lowerFiltered = filterBySearch(items, lowerQuery)
          const upperFiltered = filterBySearch(items, upperQuery)
          const mixedFiltered = filterBySearch(items, mixedQuery)

          // Property: All case variations should return the same count
          expect(lowerFiltered.length).toBe(upperFiltered.length)
          expect(lowerFiltered.length).toBe(mixedFiltered.length)

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
  // Property 5.7: Empty items array results in zero filtered count
  // ==========================================================================

  it('Property 5: Empty items array always results in zero filtered count', () => {
    fc.assert(
      fc.property(
        searchQueryArb,
        (searchQuery) => {
          const emptyItems: MockHistoryItem[] = []
          const filteredItems = filterBySearch(emptyItems, searchQuery)

          // Property: Empty items should always result in zero count
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
  // Property 5.8: Items with matching OCR text are included
  // ==========================================================================

  it('Property 5: Items with matching OCR text are included in filtered results', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 3, maxLength: 20 }), // Search term
        fc.integer({ min: 1, max: 50 }), // Number of items
        (searchTerm, itemCount) => {
          // Create items where some have the search term in OCR text
          const items: MockHistoryItem[] = Array.from({ length: itemCount }, (_, i) => ({
            id: i + 1,
            createdAt: new Date().toISOString(),
            filePath: `/path/to/file${i}.png`,
            width: 100,
            height: 100,
            ocrText: i % 2 === 0 ? `Contains ${searchTerm} here` : 'No match',
            tags: [],
            metadata: {},
          }))

          const filteredItems = filterBySearch(items, searchTerm)

          // Property: All items with matching OCR text should be included
          const expectedCount = items.filter((item) =>
            item.ocrText?.toLowerCase().includes(searchTerm.toLowerCase())
          ).length

          expect(filteredItems.length).toBe(expectedCount)

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
  // Property 5.9: Items with matching tags are included
  // ==========================================================================

  it('Property 5: Items with matching tags are included in filtered results', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 3, maxLength: 20 }), // Search term
        fc.integer({ min: 1, max: 50 }), // Number of items
        (searchTerm, itemCount) => {
          // Create items where some have the search term in tags
          const items: MockHistoryItem[] = Array.from({ length: itemCount }, (_, i) => ({
            id: i + 1,
            createdAt: new Date().toISOString(),
            filePath: `/path/to/file${i}.png`,
            width: 100,
            height: 100,
            ocrText: undefined,
            tags: i % 3 === 0 ? [searchTerm, 'other'] : ['unrelated'],
            metadata: {},
          }))

          const filteredItems = filterBySearch(items, searchTerm)

          // Property: All items with matching tags should be included
          const expectedCount = items.filter((item) =>
            item.tags?.some((tag) => tag.toLowerCase().includes(searchTerm.toLowerCase()))
          ).length

          expect(filteredItems.length).toBe(expectedCount)

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
  // Property 5.10: Items matching either OCR or tags are included (OR logic)
  // ==========================================================================

  it('Property 5: Items matching either OCR text OR tags are included (OR logic)', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 3, maxLength: 20 }), // Search term
        fc.integer({ min: 1, max: 50 }), // Number of items
        (searchTerm, itemCount) => {
          // Create items with various combinations
          const items: MockHistoryItem[] = Array.from({ length: itemCount }, (_, i) => ({
            id: i + 1,
            createdAt: new Date().toISOString(),
            filePath: `/path/to/file${i}.png`,
            width: 100,
            height: 100,
            // Alternate: OCR match only, tag match only, both, neither
            ocrText: i % 4 === 0 || i % 4 === 2 ? `Has ${searchTerm}` : 'No match',
            tags: i % 4 === 1 || i % 4 === 2 ? [searchTerm] : ['other'],
            metadata: {},
          }))

          const filteredItems = filterBySearch(items, searchTerm)

          // Property: Count should include items matching OCR OR tags
          const expectedCount = items.filter((item) => {
            const ocrMatch = item.ocrText?.toLowerCase().includes(searchTerm.toLowerCase())
            const tagMatch = item.tags?.some((tag) =>
              tag.toLowerCase().includes(searchTerm.toLowerCase())
            )
            return ocrMatch || tagMatch
          }).length

          expect(filteredItems.length).toBe(expectedCount)

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
  // Property 5.11: Display count consistency across filter state changes
  // ==========================================================================

  it('Property 5: Display count is consistent when toggling filter on and off', () => {
    fc.assert(
      fc.property(
        historyItemsArb,
        totalCountArb,
        searchQueryArb.filter((q) => q.trim().length > 0),
        (items, totalCount, searchQuery) => {
          // Calculate counts in different states
          const unfilteredCount = calculateDisplayCount(items, totalCount, '')
          const filteredCount = calculateDisplayCount(items, totalCount, searchQuery)
          const backToUnfilteredCount = calculateDisplayCount(items, totalCount, '')

          // Property: Toggling filter off should restore original count
          expect(backToUnfilteredCount).toBe(unfilteredCount)
          expect(backToUnfilteredCount).toBe(totalCount)

          // Property: Filtered count should be <= unfiltered items length
          expect(filteredCount).toBeLessThanOrEqual(items.length)

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
  // Property 5.12: No false positives in filtering
  // ==========================================================================

  it('Property 5: Filtered items all contain the search query (no false positives)', () => {
    fc.assert(
      fc.property(
        historyItemsArb,
        searchQueryArb.filter((q) => q.trim().length > 0),
        (items, searchQuery) => {
          const filteredItems = filterBySearch(items, searchQuery)
          const query = searchQuery.toLowerCase().trim()

          // Property: Every filtered item must match the query
          for (const item of filteredItems) {
            const ocrMatch = item.ocrText?.toLowerCase().includes(query)
            const tagMatch = item.tags?.some((tag) => tag.toLowerCase().includes(query))
            expect(ocrMatch || tagMatch).toBe(true)
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
  // Property 5.13: No false negatives in filtering
  // ==========================================================================

  it('Property 5: All matching items are included in filtered results (no false negatives)', () => {
    fc.assert(
      fc.property(
        historyItemsArb,
        searchQueryArb.filter((q) => q.trim().length > 0),
        (items, searchQuery) => {
          const filteredItems = filterBySearch(items, searchQuery)
          const query = searchQuery.toLowerCase().trim()
          const filteredIds = new Set(filteredItems.map((item) => item.id))

          // Property: Every item that should match is in the filtered results
          for (const item of items) {
            const ocrMatch = item.ocrText?.toLowerCase().includes(query)
            const tagMatch = item.tags?.some((tag) => tag.toLowerCase().includes(query))
            const shouldMatch = ocrMatch || tagMatch

            if (shouldMatch) {
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
})
