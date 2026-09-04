/**
 * Property-Based Tests for Search Filter Correctness
 *
 * Feature: workbench-layout-redesign, Property 6: Search Filter Correctness
 *
 * **Validates: Requirements 3.2**
 *
 * Property Definition:
 * For any search query string, all items in the filtered result list SHALL contain
 * the query string in either their OCR text or tags (case-insensitive match).
 *
 * This test file verifies:
 * 1. All filtered items contain the search query in OCR text or tags
 * 2. No items that should match are excluded (no false negatives)
 * 3. No items that shouldn't match are included (no false positives)
 * 4. Search is case-insensitive
 * 5. Empty/whitespace queries return all items
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
// Search Filtering Logic (extracted from HistoryListPanel.vue)
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
 * Arbitrary for search queries that activate filtering after trim()
 */
const nonEmptySearchQueryArb: fc.Arbitrary<string> = fc
  .string({ minLength: 1, maxLength: 50 })
  .filter((s) => s.trim().length > 0)

/**
 * Arbitrary for search queries including empty and whitespace
 */
const searchQueryArb: fc.Arbitrary<string> = fc.oneof(
  fc.constant(''),
  fc.constant('   '),
  nonEmptySearchQueryArb
)

// ============================================================================
// Property Tests
// ============================================================================

describe('Feature: workbench-layout-redesign, Property 6: Search Filter Correctness', () => {
  // ==========================================================================
  // Property 6.1: All filtered items contain the query (no false positives)
  // ==========================================================================

  it('Property 6: All filtered items contain the search query in OCR text or tags', () => {
    fc.assert(
      fc.property(
        historyItemsArb,
        nonEmptySearchQueryArb,
        (items, searchQuery) => {
          const filteredItems = filterBySearch(items, searchQuery)
          const query = searchQuery.toLowerCase().trim()

          // Property: Every filtered item must contain the query in OCR text or tags
          for (const item of filteredItems) {
            const ocrMatch = item.ocrText?.toLowerCase().includes(query) ?? false
            const tagMatch = item.tags?.some((tag) => tag.toLowerCase().includes(query)) ?? false

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
  // Property 6.2: No matching items are excluded (no false negatives)
  // ==========================================================================

  it('Property 6: All items matching the query are included in filtered results', () => {
    fc.assert(
      fc.property(
        historyItemsArb,
        nonEmptySearchQueryArb,
        (items, searchQuery) => {
          const filteredItems = filterBySearch(items, searchQuery)
          const filteredIds = new Set(filteredItems.map((item) => item.id))
          const query = searchQuery.toLowerCase().trim()

          // Property: Every item that should match is in the filtered results
          for (const item of items) {
            const ocrMatch = item.ocrText?.toLowerCase().includes(query) ?? false
            const tagMatch = item.tags?.some((tag) => tag.toLowerCase().includes(query)) ?? false
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

  // ==========================================================================
  // Property 6.3: Search is case-insensitive
  // ==========================================================================

  it('Property 6: Search filtering is case-insensitive', () => {
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

          // Property: All case variations should return the same results
          expect(lowerFiltered.length).toBe(upperFiltered.length)
          expect(lowerFiltered.length).toBe(mixedFiltered.length)

          // Verify same items are returned
          const lowerIds = new Set(lowerFiltered.map((i) => i.id))
          const upperIds = new Set(upperFiltered.map((i) => i.id))
          const mixedIds = new Set(mixedFiltered.map((i) => i.id))

          for (const id of lowerIds) {
            expect(upperIds.has(id)).toBe(true)
            expect(mixedIds.has(id)).toBe(true)
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
  // Property 6.4: Empty query returns all items
  // ==========================================================================

  it('Property 6: Empty search query returns all items', () => {
    fc.assert(
      fc.property(
        historyItemsArb,
        (items) => {
          const filteredItems = filterBySearch(items, '')

          // Property: Empty query should return all items
          expect(filteredItems.length).toBe(items.length)

          // Verify same items are returned
          const originalIds = new Set(items.map((i) => i.id))
          const filteredIds = new Set(filteredItems.map((i) => i.id))

          for (const id of originalIds) {
            expect(filteredIds.has(id)).toBe(true)
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
  // Property 6.5: Whitespace-only query returns all items
  // ==========================================================================

  it('Property 6: Whitespace-only search query returns all items', () => {
    fc.assert(
      fc.property(
        historyItemsArb,
        fc.integer({ min: 1, max: 10 }).map((n) => ' '.repeat(n)),
        (items, whitespaceQuery) => {
          const filteredItems = filterBySearch(items, whitespaceQuery)

          // Property: Whitespace-only query should return all items
          expect(filteredItems.length).toBe(items.length)

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
  // Property 6.6: Items with matching OCR text are included
  // ==========================================================================

  it('Property 6: Items with matching OCR text are always included', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 3, maxLength: 20 }),
        fc.integer({ min: 1, max: 50 }),
        (searchTerm, itemCount) => {
          // Create items where some have the search term in OCR text
          const items: MockHistoryItem[] = Array.from({ length: itemCount }, (_, i) => ({
            id: i + 1,
            createdAt: new Date().toISOString(),
            filePath: `/path/to/file${i}.png`,
            width: 100,
            height: 100,
            ocrText: i % 2 === 0 ? `Contains ${searchTerm} here` : 'No match at all',
            tags: [],
            metadata: {},
          }))

          const filteredItems = filterBySearch(items, searchTerm)

          // Property: All items with matching OCR text should be included
          const expectedCount = items.filter((item) =>
            item.ocrText?.toLowerCase().includes(searchTerm.toLowerCase())
          ).length

          expect(filteredItems.length).toBe(expectedCount)

          // Verify each filtered item actually matches
          for (const item of filteredItems) {
            expect(item.ocrText?.toLowerCase().includes(searchTerm.toLowerCase())).toBe(true)
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
  // Property 6.7: Items with matching tags are included
  // ==========================================================================

  it('Property 6: Items with matching tags are always included', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 3, maxLength: 20 }),
        fc.integer({ min: 1, max: 50 }),
        (searchTerm, itemCount) => {
          // Create items where some have the search term in tags
          const items: MockHistoryItem[] = Array.from({ length: itemCount }, (_, i) => ({
            id: i + 1,
            createdAt: new Date().toISOString(),
            filePath: `/path/to/file${i}.png`,
            width: 100,
            height: 100,
            ocrText: undefined,
            tags: i % 3 === 0 ? [searchTerm, 'other'] : ['unrelated', 'different'],
            metadata: {},
          }))

          const filteredItems = filterBySearch(items, searchTerm)

          // Property: All items with matching tags should be included
          const expectedCount = items.filter((item) =>
            item.tags?.some((tag) => tag.toLowerCase().includes(searchTerm.toLowerCase()))
          ).length

          expect(filteredItems.length).toBe(expectedCount)

          // Verify each filtered item actually matches
          for (const item of filteredItems) {
            const tagMatch = item.tags?.some((tag) =>
              tag.toLowerCase().includes(searchTerm.toLowerCase())
            )
            expect(tagMatch).toBe(true)
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
  // Property 6.8: OR logic - items matching either OCR or tags are included
  // ==========================================================================

  it('Property 6: Items matching either OCR text OR tags are included (OR logic)', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 3, maxLength: 20 }),
        fc.integer({ min: 4, max: 50 }),
        (searchTerm, itemCount) => {
          // Create items with various combinations:
          // i % 4 === 0: OCR match only
          // i % 4 === 1: Tag match only
          // i % 4 === 2: Both match
          // i % 4 === 3: Neither match
          const items: MockHistoryItem[] = Array.from({ length: itemCount }, (_, i) => ({
            id: i + 1,
            createdAt: new Date().toISOString(),
            filePath: `/path/to/file${i}.png`,
            width: 100,
            height: 100,
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
  // Property 6.9: Filtered count is bounded by total items
  // ==========================================================================

  it('Property 6: Filtered count is always <= total items count', () => {
    fc.assert(
      fc.property(
        historyItemsArb,
        searchQueryArb,
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
  // Property 6.10: Empty items array always returns empty result
  // ==========================================================================

  it('Property 6: Empty items array always returns empty filtered result', () => {
    fc.assert(
      fc.property(
        searchQueryArb,
        (searchQuery) => {
          const emptyItems: MockHistoryItem[] = []
          const filteredItems = filterBySearch(emptyItems, searchQuery)

          // Property: Empty items should always result in empty filtered result
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
  // Property 6.11: Partial match works correctly
  // ==========================================================================

  it('Property 6: Partial string matches are included in results', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 5, maxLength: 30 }),
        fc.integer({ min: 1, max: 4 }), // Substring start position
        fc.integer({ min: 2, max: 5 }), // Substring length
        (fullText, startOffset, length) => {
          // Extract a substring from the full text
          const start = Math.min(startOffset, fullText.length - 1)
          const end = Math.min(start + length, fullText.length)
          const substring = fullText.slice(start, end)

          if (substring.length === 0) return true // Skip if substring is empty

          // Create an item with the full text
          const items: MockHistoryItem[] = [
            {
              id: 1,
              createdAt: new Date().toISOString(),
              filePath: '/path/to/file.png',
              width: 100,
              height: 100,
              ocrText: fullText,
              tags: [],
              metadata: {},
            },
          ]

          const filteredItems = filterBySearch(items, substring)

          // Property: Searching for a substring should find the item
          expect(filteredItems.length).toBe(1)
          expect(filteredItems[0].id).toBe(1)

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
  // Property 6.12: Filter is idempotent
  // ==========================================================================

  it('Property 6: Filtering is idempotent (filtering twice gives same result)', () => {
    fc.assert(
      fc.property(
        historyItemsArb,
        nonEmptySearchQueryArb,
        (items, searchQuery) => {
          const firstFilter = filterBySearch(items, searchQuery)
          const secondFilter = filterBySearch(firstFilter, searchQuery)

          // Property: Filtering twice should give the same result
          expect(secondFilter.length).toBe(firstFilter.length)

          const firstIds = new Set(firstFilter.map((i) => i.id))
          const secondIds = new Set(secondFilter.map((i) => i.id))

          for (const id of firstIds) {
            expect(secondIds.has(id)).toBe(true)
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
  // Property 6.13: Items with undefined/null OCR text don't cause errors
  // ==========================================================================

  it('Property 6: Items with undefined OCR text are handled gracefully', () => {
    fc.assert(
      fc.property(
        // Use non-whitespace search query to avoid the trim() edge case
        fc.string({ minLength: 1, maxLength: 20 }).filter((s) => s.trim().length > 0),
        fc.integer({ min: 1, max: 50 }),
        (searchQuery, itemCount) => {
          // Create items with undefined OCR text
          const items: MockHistoryItem[] = Array.from({ length: itemCount }, (_, i) => ({
            id: i + 1,
            createdAt: new Date().toISOString(),
            filePath: `/path/to/file${i}.png`,
            width: 100,
            height: 100,
            ocrText: undefined, // All items have undefined OCR text
            tags: i % 2 === 0 ? [searchQuery] : ['other'],
            metadata: {},
          }))

          // Property: Should not throw and should filter correctly by tags
          const filteredItems = filterBySearch(items, searchQuery)

          // Only items with matching tags should be included
          const expectedCount = items.filter((item) =>
            item.tags?.some((tag) => tag.toLowerCase().includes(searchQuery.toLowerCase().trim()))
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
  // Property 6.14: Items with empty tags array are handled gracefully
  // ==========================================================================

  it('Property 6: Items with empty tags array are handled gracefully', () => {
    fc.assert(
      fc.property(
        nonEmptySearchQueryArb,
        fc.integer({ min: 1, max: 50 }),
        (searchQuery, itemCount) => {
          // Create items with empty tags array
          const items: MockHistoryItem[] = Array.from({ length: itemCount }, (_, i) => ({
            id: i + 1,
            createdAt: new Date().toISOString(),
            filePath: `/path/to/file${i}.png`,
            width: 100,
            height: 100,
            ocrText: i % 2 === 0 ? `Contains ${searchQuery}` : 'No match',
            tags: [], // All items have empty tags
            metadata: {},
          }))

          // Property: Should not throw and should filter correctly by OCR text
          const filteredItems = filterBySearch(items, searchQuery)

          // Only items with matching OCR text should be included
          const query = searchQuery.toLowerCase().trim()
          const expectedCount = items.filter((item) =>
            item.ocrText?.toLowerCase().includes(query)
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
  // Property 6.15: Special characters in search query are handled
  // ==========================================================================

  it('Property 6: Special characters in search query are handled correctly', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('test.txt', 'hello@world', 'foo/bar', 'a+b', 'x*y', '[test]', '(abc)'),
        fc.integer({ min: 1, max: 20 }),
        (specialQuery, itemCount) => {
          // Create items where some contain the special query
          const items: MockHistoryItem[] = Array.from({ length: itemCount }, (_, i) => ({
            id: i + 1,
            createdAt: new Date().toISOString(),
            filePath: `/path/to/file${i}.png`,
            width: 100,
            height: 100,
            ocrText: i % 2 === 0 ? `Contains ${specialQuery} here` : 'No special chars',
            tags: [],
            metadata: {},
          }))

          // Property: Should not throw and should filter correctly
          const filteredItems = filterBySearch(items, specialQuery)

          // Verify filtered items actually contain the query
          for (const item of filteredItems) {
            expect(item.ocrText?.toLowerCase().includes(specialQuery.toLowerCase())).toBe(true)
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
  // Property 6.16: Unicode characters in search are handled
  // ==========================================================================

  it('Property 6: Unicode characters in search query are handled correctly', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('你好', '世界', 'こんにちは', '🎉', 'café', 'naïve'),
        fc.integer({ min: 1, max: 20 }),
        (unicodeQuery, itemCount) => {
          // Create items where some contain the unicode query
          const items: MockHistoryItem[] = Array.from({ length: itemCount }, (_, i) => ({
            id: i + 1,
            createdAt: new Date().toISOString(),
            filePath: `/path/to/file${i}.png`,
            width: 100,
            height: 100,
            ocrText: i % 2 === 0 ? `Contains ${unicodeQuery} here` : 'No unicode',
            tags: [],
            metadata: {},
          }))

          // Property: Should not throw and should filter correctly
          const filteredItems = filterBySearch(items, unicodeQuery)

          // Verify filtered items actually contain the query
          for (const item of filteredItems) {
            expect(item.ocrText?.toLowerCase().includes(unicodeQuery.toLowerCase())).toBe(true)
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
  // Property 6.17: Filter preserves item order
  // ==========================================================================

  it('Property 6: Filtering preserves the relative order of items', () => {
    fc.assert(
      fc.property(
        historyItemsArb.filter((items) => items.length >= 2),
        nonEmptySearchQueryArb,
        (items, searchQuery) => {
          const filteredItems = filterBySearch(items, searchQuery)

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
})
