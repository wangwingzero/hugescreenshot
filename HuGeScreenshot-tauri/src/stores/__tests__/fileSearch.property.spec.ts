/**
 * Property-Based Tests for File Search Store State Preservation
 *
 * Feature: everything-file-search, Property 15: Search State Preservation
 *
 * **Validates: Requirements 8.5**
 *
 * Property Definition:
 * For any search state saved to the store, retrieving the state SHALL return
 * an equivalent state with all fields preserved.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import * as fc from 'fast-check'
import { useFileSearchStore, type FileSearchResult, type FileSearchState } from '../fileSearch'

// ============================================================================
// Arbitraries for File Search State
// ============================================================================

/** Arbitrary for generating file search result match indices */
const matchIndicesArb: fc.Arbitrary<[number, number][]> = fc
  .array(
    fc.tuple(
      fc.integer({ min: 0, max: 100 }),
      fc.integer({ min: 0, max: 100 })
    ),
    { minLength: 0, maxLength: 5 }
  )
  .map((indices) =>
    // Ensure start <= end for each tuple
    indices.map(([a, b]) => [Math.min(a, b), Math.max(a, b)] as [number, number])
  )

/** Arbitrary for generating valid ISO date strings */
const validDateStringArb: fc.Arbitrary<string> = fc
  .integer({ min: 946684800000, max: 4102444800000 }) // 2000-01-01 to 2100-01-01
  .map((ts) => new Date(ts).toISOString())

/** Arbitrary for generating a single FileSearchResult */
const fileSearchResultArb: fc.Arbitrary<FileSearchResult> = fc.record({
  fileId: fc.string({ minLength: 1, maxLength: 20 }),
  name: fc.string({ minLength: 1, maxLength: 100 }),
  path: fc.string({ minLength: 1, maxLength: 200 }),
  size: fc.integer({ min: 0, max: 1_000_000_000 }),
  modified: validDateStringArb,
  isDirectory: fc.boolean(),
  score: fc.integer({ min: 0, max: 1000 }),
  matchIndices: matchIndicesArb,
})

/** Arbitrary for generating an array of FileSearchResults */
const fileSearchResultsArb: fc.Arbitrary<FileSearchResult[]> = fc.array(fileSearchResultArb, {
  minLength: 0,
  maxLength: 20,
})

/** Arbitrary for generating a search query string */
const searchQueryArb: fc.Arbitrary<string> = fc.string({ minLength: 0, maxLength: 100 })

/** Arbitrary for generating a non-empty search query string */
const nonEmptySearchQueryArb: fc.Arbitrary<string> = fc.string({ minLength: 1, maxLength: 100 })

/** Arbitrary for generating total count */
const totalCountArb: fc.Arbitrary<number> = fc.integer({ min: 0, max: 100000 })

/** Arbitrary for generating search time in ms */
const searchTimeMsArb: fc.Arbitrary<number> = fc.integer({ min: 0, max: 10000 })

/** Arbitrary for generating selected index */
const selectedIndexArb: fc.Arbitrary<number> = fc.integer({ min: 0, max: 100 })

// ============================================================================
// Property Tests
// ============================================================================

describe('Feature: everything-file-search, Property 15: Search State Preservation', () => {
  beforeEach(() => {
    // Create a fresh Pinia instance before each test
    setActivePinia(createPinia())
    // Clear localStorage to ensure clean state
    localStorage.clear()
  })

  /**
   * Property 15: Search State Preservation - saveState and getState round-trip
   *
   * For any search state saved via saveState(), calling getState() SHALL return
   * an equivalent state with all fields preserved.
   *
   * **Validates: Requirements 8.5**
   */
  it('should preserve all state fields through saveState/getState round-trip', () => {
    fc.assert(
      fc.property(
        nonEmptySearchQueryArb,
        fileSearchResultsArb,
        totalCountArb,
        searchTimeMsArb,
        selectedIndexArb,
        (query, results, totalCount, searchTimeMs, selectedIndex) => {
          const store = useFileSearchStore()

          // Adjust selectedIndex to be within valid range
          const validSelectedIndex =
            results.length > 0 ? Math.min(selectedIndex, results.length - 1) : 0

          // Save state
          store.saveState(query, results, totalCount, searchTimeMs, validSelectedIndex)

          // Get state
          const retrievedState = store.getState()

          // Verify all fields are preserved
          expect(retrievedState.query).toBe(query)
          expect(retrievedState.results).toEqual(results)
          expect(retrievedState.totalCount).toBe(totalCount)
          expect(retrievedState.searchTimeMs).toBe(searchTimeMs)
          expect(retrievedState.selectedIndex).toBe(validSelectedIndex)
          expect(retrievedState.lastSearchTime).toBeGreaterThan(0)
        }
      ),
      {
        numRuns: 50,
        verbose: true,
      }
    )
  })

  /**
   * Property 15: Search State Preservation - restoreState preserves all fields
   *
   * For any FileSearchState, calling restoreState() SHALL set all store fields
   * to match the provided state.
   *
   * **Validates: Requirements 8.5**
   */
  it('should restore all state fields from a FileSearchState object', () => {
    fc.assert(
      fc.property(
        nonEmptySearchQueryArb,
        fileSearchResultsArb,
        totalCountArb,
        searchTimeMsArb,
        selectedIndexArb,
        fc.integer({ min: 1, max: Date.now() }),
        (query, results, totalCount, searchTimeMs, selectedIndex, lastSearchTime) => {
          const store = useFileSearchStore()

          // Create a state object
          const state: FileSearchState = {
            query,
            results,
            totalCount,
            searchTimeMs,
            selectedIndex,
            lastSearchTime,
          }

          // Restore state
          store.restoreState(state)

          // Verify all fields are restored
          expect(store.query).toBe(query)
          expect(store.results).toEqual(results)
          expect(store.totalCount).toBe(totalCount)
          expect(store.searchTimeMs).toBe(searchTimeMs)
          expect(store.selectedIndex).toBe(selectedIndex)
          expect(store.lastSearchTime).toBe(lastSearchTime)
        }
      ),
      {
        numRuns: 50,
        verbose: true,
      }
    )
  })

  /**
   * Property 15: Search State Preservation - clearState resets all fields
   *
   * After calling clearState(), all state fields SHALL be reset to their
   * initial values.
   *
   * **Validates: Requirements 8.5**
   */
  it('should reset all state fields when clearState is called', () => {
    fc.assert(
      fc.property(
        nonEmptySearchQueryArb,
        fileSearchResultsArb,
        totalCountArb,
        searchTimeMsArb,
        selectedIndexArb,
        (query, results, totalCount, searchTimeMs, selectedIndex) => {
          const store = useFileSearchStore()

          // First save some state
          store.saveState(query, results, totalCount, searchTimeMs, selectedIndex)

          // Clear state
          store.clearState()

          // Verify all fields are reset
          expect(store.query).toBe('')
          expect(store.results).toEqual([])
          expect(store.totalCount).toBe(0)
          expect(store.searchTimeMs).toBe(0)
          expect(store.selectedIndex).toBe(0)
          expect(store.lastSearchTime).toBe(0)
        }
      ),
      {
        numRuns: 50,
        verbose: true,
      }
    )
  })

  /**
   * Property 15: Search State Preservation - hasValidState computed property
   *
   * hasValidState SHALL return true only when:
   * 1. query is non-empty
   * 2. results array is non-empty
   * 3. lastSearchTime is within the expiry window (5 minutes)
   *
   * **Validates: Requirements 8.5**
   */
  it('should correctly compute hasValidState based on state conditions', () => {
    fc.assert(
      fc.property(
        searchQueryArb,
        fileSearchResultsArb,
        (query, results) => {
          const store = useFileSearchStore()

          // Save state with current timestamp
          store.saveState(query, results, results.length, 100, 0)

          // hasValidState should be true only if query is non-empty AND results is non-empty
          const expectedValid = query.length > 0 && results.length > 0

          expect(store.hasValidState).toBe(expectedValid)
        }
      ),
      {
        numRuns: 50,
        verbose: true,
      }
    )
  })

  /**
   * Property 15: Search State Preservation - selectedResult computed property
   *
   * selectedResult SHALL return the result at selectedIndex if valid,
   * or null if selectedIndex is out of bounds.
   *
   * **Validates: Requirements 8.5**
   */
  it('should return correct selectedResult based on selectedIndex', () => {
    fc.assert(
      fc.property(
        nonEmptySearchQueryArb,
        fc.array(fileSearchResultArb, { minLength: 1, maxLength: 10 }),
        fc.integer({ min: 0, max: 20 }),
        (query, results, selectedIndex) => {
          const store = useFileSearchStore()

          // Save state
          store.saveState(query, results, results.length, 100, selectedIndex)

          // Check selectedResult
          if (selectedIndex >= 0 && selectedIndex < results.length) {
            expect(store.selectedResult).toEqual(results[selectedIndex])
          } else {
            expect(store.selectedResult).toBeNull()
          }
        }
      ),
      {
        numRuns: 50,
        verbose: true,
      }
    )
  })

  /**
   * Property 15: Search State Preservation - setSelectedIndex bounds checking
   *
   * setSelectedIndex SHALL only update selectedIndex if the new value is
   * within the valid range [0, results.length - 1].
   *
   * **Validates: Requirements 8.5**
   */
  it('should only update selectedIndex when within valid bounds', () => {
    fc.assert(
      fc.property(
        nonEmptySearchQueryArb,
        fc.array(fileSearchResultArb, { minLength: 1, maxLength: 10 }),
        fc.integer({ min: -10, max: 20 }),
        (query, results, newIndex) => {
          const store = useFileSearchStore()

          // Save initial state with selectedIndex = 0
          store.saveState(query, results, results.length, 100, 0)
          const initialIndex = store.selectedIndex

          // Try to set new index
          store.setSelectedIndex(newIndex)

          // Check if index was updated
          if (newIndex >= 0 && newIndex < results.length) {
            expect(store.selectedIndex).toBe(newIndex)
          } else {
            expect(store.selectedIndex).toBe(initialIndex)
          }
        }
      ),
      {
        numRuns: 50,
        verbose: true,
      }
    )
  })

  /**
   * Property 15: Search State Preservation - localStorage persistence
   *
   * The query string SHALL be persisted to localStorage and retrievable
   * via initialize() within the expiry window.
   *
   * **Validates: Requirements 8.5**
   */
  it('should persist query to localStorage and retrieve via initialize', () => {
    fc.assert(
      fc.property(
        // Use alphanumeric strings to avoid edge cases with whitespace-only strings
        fc.string({ minLength: 1, maxLength: 100 }).filter((s) => s.trim().length > 0),
        (query) => {
          // Create fresh pinia for each iteration
          setActivePinia(createPinia())
          localStorage.clear()

          // First store instance saves state
          const store1 = useFileSearchStore()
          store1.saveState(query, [], 0, 0, 0)

          // Create a new pinia instance to simulate app restart
          setActivePinia(createPinia())
          const store2 = useFileSearchStore()

          // Initialize should restore the query from localStorage
          const savedQuery = store2.initialize()

          expect(savedQuery).toBe(query)
          expect(store2.query).toBe(query)
        }
      ),
      {
        numRuns: 50,
        verbose: true,
      }
    )
  })

  /**
   * Property 15: Search State Preservation - multiple save/restore cycles
   *
   * Multiple consecutive save/restore cycles SHALL preserve state correctly.
   *
   * **Validates: Requirements 8.5**
   */
  it('should handle multiple save/restore cycles correctly', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.tuple(nonEmptySearchQueryArb, fileSearchResultsArb, totalCountArb, searchTimeMsArb),
          { minLength: 1, maxLength: 5 }
        ),
        (stateUpdates) => {
          const store = useFileSearchStore()

          // Apply multiple state updates
          for (const [query, results, totalCount, searchTimeMs] of stateUpdates) {
            store.saveState(query, results, totalCount, searchTimeMs, 0)
          }

          // Get final state
          const finalState = store.getState()

          // Should match the last update
          const [lastQuery, lastResults, lastTotalCount, lastSearchTimeMs] =
            stateUpdates[stateUpdates.length - 1]

          expect(finalState.query).toBe(lastQuery)
          expect(finalState.results).toEqual(lastResults)
          expect(finalState.totalCount).toBe(lastTotalCount)
          expect(finalState.searchTimeMs).toBe(lastSearchTimeMs)
        }
      ),
      {
        numRuns: 50,
        verbose: true,
      }
    )
  })
})
