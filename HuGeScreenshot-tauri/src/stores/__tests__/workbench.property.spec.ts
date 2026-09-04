/**
 * Property-Based Tests for Workbench Store Selection Synchronization
 *
 * Feature: workbench-layout-redesign, Property 8: Selection Synchronizes OCR Panel
 *
 * **Validates: Requirements 7.1, 7.3, 9.1**
 *
 * Property Definition:
 * For any selection change (via click or keyboard), the OCR panel SHALL display
 * the OCR text of the newly selected item within 100ms.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import * as fc from 'fast-check'
import { useWorkbenchStore } from '../workbench'
import { useHistoryStore } from '../history'
import type { HistoryItem, HistoryMetadata } from '@/types'

// ============================================================================
// Mock Tauri APIs
// ============================================================================

// Mock Tauri invoke to prevent actual backend calls
vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn().mockResolvedValue({}),
}))

// ============================================================================
// Arbitraries for HistoryItem generation
// ============================================================================

/** Arbitrary for HistoryMetadata */
const historyMetadataArb: fc.Arbitrary<HistoryMetadata> = fc.record({
  captureMode: fc.option(fc.constantFrom('fullscreen', 'region', 'window'), { nil: undefined }),
  monitorId: fc.option(fc.integer({ min: 0, max: 3 }), { nil: undefined }),
  appName: fc.option(fc.string({ minLength: 0, maxLength: 50 }), { nil: undefined }),
  windowTitle: fc.option(fc.string({ minLength: 0, maxLength: 100 }), { nil: undefined }),
  hasAnnotations: fc.option(fc.boolean(), { nil: undefined }),
})

/** Generate a valid ISO date string */
const isoDateStringArb: fc.Arbitrary<string> = fc
  .integer({ min: 1577836800000, max: 1767225600000 }) // 2020-01-01 to 2025-12-31
  .map((timestamp) => new Date(timestamp).toISOString())

/** Arbitrary for HistoryItem */
const historyItemArb: fc.Arbitrary<HistoryItem> = fc.record({
  id: fc.integer({ min: 1, max: 10000 }),
  createdAt: isoDateStringArb,
  filePath: fc.string({ minLength: 1, maxLength: 50 })
    .filter((s) => s.length > 0)
    .map((s) => `C:/screenshots/${s.replace(/[<>:"|?*\\/]/g, '_')}.png`),
  thumbnailPath: fc.option(
    fc.string({ minLength: 1, maxLength: 50 })
      .filter((s) => s.length > 0)
      .map((s) => `C:/thumbnails/${s.replace(/[<>:"|?*\\/]/g, '_')}_thumb.png`),
    { nil: undefined }
  ),
  width: fc.integer({ min: 100, max: 4000 }),
  height: fc.integer({ min: 100, max: 3000 }),
  fileSize: fc.option(fc.integer({ min: 1000, max: 10000000 }), { nil: undefined }),
  ocrText: fc.option(fc.string({ minLength: 0, maxLength: 1000 }), { nil: undefined }),
  tags: fc.array(fc.string({ minLength: 1, maxLength: 30 }).filter((s) => s.length > 0), { minLength: 0, maxLength: 5 }),
  metadata: historyMetadataArb,
})

/** Arbitrary for non-empty array of HistoryItems with unique IDs */
const historyItemsArb: fc.Arbitrary<HistoryItem[]> = fc
  .array(historyItemArb, { minLength: 1, maxLength: 20 })
  .map((items) => {
    // Ensure unique IDs by reassigning
    return items.map((item, index) => ({ ...item, id: index + 1 }))
  })

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Setup stores with mock history items
 */
function setupStoresWithItems(items: HistoryItem[]): {
  workbenchStore: ReturnType<typeof useWorkbenchStore>
  historyStore: ReturnType<typeof useHistoryStore>
} {
  const historyStore = useHistoryStore()
  const workbenchStore = useWorkbenchStore()

  // Directly set items in history store (bypassing Tauri invoke)
  historyStore.items = [...items]
  historyStore.totalCount = items.length

  return { workbenchStore, historyStore }
}

// ============================================================================
// Property Tests
// ============================================================================

describe('Feature: workbench-layout-redesign, Property 8: Selection Synchronizes OCR Panel', () => {
  beforeEach(() => {
    // Create a fresh Pinia instance before each test
    setActivePinia(createPinia())
    // Clear localStorage to prevent state persistence interference
    localStorage.clear()
  })

  /**
   * Property 8: Selection Synchronizes OCR Panel
   *
   * For any selection change (via click or keyboard), the OCR panel SHALL display
   * the OCR text of the newly selected item within 100ms.
   *
   * **Validates: Requirements 7.1, 7.3, 9.1**
   *
   * This test verifies that:
   * 1. When selectItem(id) is called, the ocrText is updated to match the selected item's ocrText
   * 2. The selectedItemId is correctly set
   * 3. The selectedItem computed property returns the correct item
   */
  it('Property 8: Selection synchronizes OCR panel - selectItem updates ocrText to match selected item', async () => {
    await fc.assert(
      fc.asyncProperty(historyItemsArb, async (items) => {
        // Fresh pinia for each iteration
        setActivePinia(createPinia())
        localStorage.clear()

        const { workbenchStore } = setupStoresWithItems(items)

        // Test selecting each item
        for (const item of items) {
          await workbenchStore.selectItem(item.id)

          // Verify selectedItemId is set correctly
          expect(workbenchStore.selectedItemId).toBe(item.id)

          // Verify ocrText matches the selected item's ocrText
          const expectedOcrText = item.ocrText ?? ''
          expect(workbenchStore.ocrText).toBe(expectedOcrText)

          // Verify originalOcrText is also set (for restore functionality)
          expect(workbenchStore.originalOcrText).toBe(expectedOcrText)

          // Verify selectedItem computed property returns correct item
          expect(workbenchStore.selectedItem).not.toBeNull()
          expect(workbenchStore.selectedItem?.id).toBe(item.id)
        }

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Property 8 (Variant): Keyboard navigation (selectNext/selectPrevious) synchronizes OCR panel
   *
   * **Validates: Requirements 7.2, 7.3**
   */
  it('Property 8: Selection synchronizes OCR panel - selectNext updates ocrText correctly', async () => {
    await fc.assert(
      fc.asyncProperty(historyItemsArb, async (items) => {
        // Need at least 2 items for navigation testing
        if (items.length < 2) return true

        setActivePinia(createPinia())
        localStorage.clear()

        const { workbenchStore } = setupStoresWithItems(items)

        // Select first item
        await workbenchStore.selectItem(items[0].id)
        expect(workbenchStore.ocrText).toBe(items[0].ocrText ?? '')

        // Navigate to next item
        workbenchStore.selectNext()

        // Verify OCR text is updated to second item
        const expectedOcrText = items[1].ocrText ?? ''
        expect(workbenchStore.ocrText).toBe(expectedOcrText)
        expect(workbenchStore.selectedItemId).toBe(items[1].id)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Property 8 (Variant): selectPrevious synchronizes OCR panel
   *
   * **Validates: Requirements 7.2, 7.3**
   */
  it('Property 8: Selection synchronizes OCR panel - selectPrevious updates ocrText correctly', async () => {
    await fc.assert(
      fc.asyncProperty(historyItemsArb, async (items) => {
        // Need at least 2 items for navigation testing
        if (items.length < 2) return true

        setActivePinia(createPinia())
        localStorage.clear()

        const { workbenchStore } = setupStoresWithItems(items)

        // Select second item
        await workbenchStore.selectItem(items[1].id)
        expect(workbenchStore.ocrText).toBe(items[1].ocrText ?? '')

        // Navigate to previous item
        workbenchStore.selectPrevious()

        // Verify OCR text is updated to first item
        const expectedOcrText = items[0].ocrText ?? ''
        expect(workbenchStore.ocrText).toBe(expectedOcrText)
        expect(workbenchStore.selectedItemId).toBe(items[0].id)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Property 8 (Variant): Rapid selection changes should always reflect the final selection
   *
   * **Validates: Requirements 9.1** (100ms response time)
   *
   * This tests that even with rapid selection changes, the final state is consistent.
   */
  it('Property 8: Selection synchronizes OCR panel - rapid selection changes reflect final state', async () => {
    await fc.assert(
      fc.asyncProperty(
        historyItemsArb,
        fc.array(fc.nat({ max: 100 }), { minLength: 1, maxLength: 20 }),
        async (items, selectionIndices) => {
          if (items.length === 0) return true

          setActivePinia(createPinia())
          localStorage.clear()

          const { workbenchStore } = setupStoresWithItems(items)

          // Perform rapid selection changes
          let lastSelectedItem: HistoryItem | null = null
          for (const index of selectionIndices) {
            const itemIndex = index % items.length
            lastSelectedItem = items[itemIndex]
            await workbenchStore.selectItem(lastSelectedItem.id)
          }

          // Verify final state matches last selected item
          if (lastSelectedItem) {
            expect(workbenchStore.selectedItemId).toBe(lastSelectedItem.id)
            expect(workbenchStore.ocrText).toBe(lastSelectedItem.ocrText ?? '')
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

  /**
   * Property 8 (Variant): Selecting the same item twice should not change state
   *
   * **Validates: Requirements 7.1**
   */
  it('Property 8: Selection synchronizes OCR panel - selecting same item is idempotent', async () => {
    await fc.assert(
      fc.asyncProperty(historyItemsArb, async (items) => {
        setActivePinia(createPinia())
        localStorage.clear()

        const { workbenchStore } = setupStoresWithItems(items)

        const item = items[0]

        // Select item first time
        await workbenchStore.selectItem(item.id)
        const firstOcrText = workbenchStore.ocrText
        const firstSelectedId = workbenchStore.selectedItemId

        // Select same item again
        await workbenchStore.selectItem(item.id)

        // State should remain the same
        expect(workbenchStore.ocrText).toBe(firstOcrText)
        expect(workbenchStore.selectedItemId).toBe(firstSelectedId)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Property 8 (Variant): clearSelection should clear OCR text
   *
   * **Validates: Requirements 7.1**
   */
  it('Property 8: Selection synchronizes OCR panel - clearSelection clears ocrText', async () => {
    await fc.assert(
      fc.asyncProperty(historyItemsArb, async (items) => {
        setActivePinia(createPinia())
        localStorage.clear()

        const { workbenchStore } = setupStoresWithItems(items)

        // Select an item
        await workbenchStore.selectItem(items[0].id)
        expect(workbenchStore.ocrText).toBe(items[0].ocrText ?? '')

        // Clear selection
        workbenchStore.clearSelection()

        // Verify OCR text is cleared
        expect(workbenchStore.selectedItemId).toBeNull()
        expect(workbenchStore.ocrText).toBe('')
        expect(workbenchStore.originalOcrText).toBe('')
        expect(workbenchStore.selectedItem).toBeNull()

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Property 8 (Variant): OCR stats charCount should match ocrText length after selection
   *
   * **Validates: Requirements 6.1, 7.1**
   */
  it('Property 8: Selection synchronizes OCR panel - charCount matches ocrText length', async () => {
    await fc.assert(
      fc.asyncProperty(historyItemsArb, async (items) => {
        setActivePinia(createPinia())
        localStorage.clear()

        const { workbenchStore } = setupStoresWithItems(items)

        for (const item of items) {
          await workbenchStore.selectItem(item.id)

          // Verify charCount computed property matches ocrText length
          expect(workbenchStore.charCount).toBe(workbenchStore.ocrText.length)

          // Also verify ocrStats.charCount if stats exist
          if (workbenchStore.ocrStats) {
            expect(workbenchStore.ocrStats.charCount).toBe(workbenchStore.ocrText.length)
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

  /**
   * Property 8 (Variant): Selection with empty ocrText should set empty string, not undefined
   *
   * **Validates: Requirements 7.1, 4.3**
   */
  it('Property 8: Selection synchronizes OCR panel - handles undefined ocrText gracefully', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(
          fc.record({
            id: fc.integer({ min: 1, max: 10000 }),
            createdAt: isoDateStringArb,
            filePath: fc.constant('C:/test.png'),
            width: fc.constant(100),
            height: fc.constant(100),
            // Explicitly test undefined ocrText
            ocrText: fc.constant(undefined),
            tags: fc.constant([] as string[]),
            metadata: fc.constant({} as HistoryMetadata),
          }),
          { minLength: 1, maxLength: 10 }
        ).map((items) => {
          // Ensure unique IDs
          return items.map((item, index) => ({ ...item, id: index + 1 }))
        }),
        async (items) => {
          setActivePinia(createPinia())
          localStorage.clear()

          const { workbenchStore } = setupStoresWithItems(items as HistoryItem[])

          for (const item of items) {
            await workbenchStore.selectItem(item.id)

            // ocrText should be empty string, not undefined
            expect(workbenchStore.ocrText).toBe('')
            expect(typeof workbenchStore.ocrText).toBe('string')
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


// ============================================================================
// Property 11: Keyboard Navigation Changes Selection
// ============================================================================

/**
 * Property-Based Tests for Keyboard Navigation
 *
 * Feature: workbench-layout-redesign, Property 11: Keyboard Navigation Changes Selection
 *
 * **Validates: Requirements 7.2**
 *
 * Property Definition:
 * For any arrow key press (up/down) when the history list has focus, the selection
 * SHALL move to the adjacent item in the list (if one exists).
 */
describe('Feature: workbench-layout-redesign, Property 11: Keyboard Navigation Changes Selection', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  /**
   * Property 11: selectNext moves selection to the next adjacent item
   *
   * For any list of items and any starting position (except the last),
   * calling selectNext SHALL move selection to the item at index + 1.
   *
   * **Validates: Requirements 7.2**
   */
  it('Property 11: Keyboard Navigation Changes Selection - selectNext moves to adjacent item', async () => {
    await fc.assert(
      fc.asyncProperty(
        historyItemsArb,
        fc.nat({ max: 100 }),
        async (items, startIndexSeed) => {
          // Need at least 2 items to test navigation
          if (items.length < 2) return true

          setActivePinia(createPinia())
          localStorage.clear()

          const { workbenchStore } = setupStoresWithItems(items)

          // Select a starting item (not the last one)
          const startIndex = startIndexSeed % (items.length - 1)
          await workbenchStore.selectItem(items[startIndex].id)

          // Verify initial selection
          expect(workbenchStore.selectedItemId).toBe(items[startIndex].id)

          // Call selectNext (simulates ArrowDown key press)
          workbenchStore.selectNext()

          // Verify selection moved to adjacent (next) item
          const expectedNextItem = items[startIndex + 1]
          expect(workbenchStore.selectedItemId).toBe(expectedNextItem.id)

          return true
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Property 11: selectPrevious moves selection to the previous adjacent item
   *
   * For any list of items and any starting position (except the first),
   * calling selectPrevious SHALL move selection to the item at index - 1.
   *
   * **Validates: Requirements 7.2**
   */
  it('Property 11: Keyboard Navigation Changes Selection - selectPrevious moves to adjacent item', async () => {
    await fc.assert(
      fc.asyncProperty(
        historyItemsArb,
        fc.nat({ max: 100 }),
        async (items, startIndexSeed) => {
          // Need at least 2 items to test navigation
          if (items.length < 2) return true

          setActivePinia(createPinia())
          localStorage.clear()

          const { workbenchStore } = setupStoresWithItems(items)

          // Select a starting item (not the first one)
          const startIndex = 1 + (startIndexSeed % (items.length - 1))
          await workbenchStore.selectItem(items[startIndex].id)

          // Verify initial selection
          expect(workbenchStore.selectedItemId).toBe(items[startIndex].id)

          // Call selectPrevious (simulates ArrowUp key press)
          workbenchStore.selectPrevious()

          // Verify selection moved to adjacent (previous) item
          const expectedPrevItem = items[startIndex - 1]
          expect(workbenchStore.selectedItemId).toBe(expectedPrevItem.id)

          return true
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Property 11: selectNext at last item does not change selection
   *
   * For any list of items, when the last item is selected,
   * calling selectNext SHALL NOT change the selection (boundary condition).
   *
   * **Validates: Requirements 7.2**
   */
  it('Property 11: Keyboard Navigation Changes Selection - selectNext at boundary stays at last item', async () => {
    await fc.assert(
      fc.asyncProperty(historyItemsArb, async (items) => {
        setActivePinia(createPinia())
        localStorage.clear()

        const { workbenchStore } = setupStoresWithItems(items)

        // Select the last item
        const lastItem = items[items.length - 1]
        await workbenchStore.selectItem(lastItem.id)

        // Verify initial selection
        expect(workbenchStore.selectedItemId).toBe(lastItem.id)

        // Call selectNext at boundary
        workbenchStore.selectNext()

        // Selection should remain at last item (no wrap-around)
        expect(workbenchStore.selectedItemId).toBe(lastItem.id)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Property 11: selectPrevious at first item does not change selection
   *
   * For any list of items, when the first item is selected,
   * calling selectPrevious SHALL NOT change the selection (boundary condition).
   *
   * **Validates: Requirements 7.2**
   */
  it('Property 11: Keyboard Navigation Changes Selection - selectPrevious at boundary stays at first item', async () => {
    await fc.assert(
      fc.asyncProperty(historyItemsArb, async (items) => {
        setActivePinia(createPinia())
        localStorage.clear()

        const { workbenchStore } = setupStoresWithItems(items)

        // Select the first item
        const firstItem = items[0]
        await workbenchStore.selectItem(firstItem.id)

        // Verify initial selection
        expect(workbenchStore.selectedItemId).toBe(firstItem.id)

        // Call selectPrevious at boundary
        workbenchStore.selectPrevious()

        // Selection should remain at first item (no wrap-around)
        expect(workbenchStore.selectedItemId).toBe(firstItem.id)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Property 11: selectNext with no selection selects first item
   *
   * For any list of items, when no item is selected,
   * calling selectNext SHALL select the first item in the list.
   *
   * **Validates: Requirements 7.2**
   */
  it('Property 11: Keyboard Navigation Changes Selection - selectNext with no selection selects first item', async () => {
    await fc.assert(
      fc.asyncProperty(historyItemsArb, async (items) => {
        setActivePinia(createPinia())
        localStorage.clear()

        const { workbenchStore } = setupStoresWithItems(items)

        // Ensure no selection
        expect(workbenchStore.selectedItemId).toBeNull()

        // Call selectNext with no selection
        workbenchStore.selectNext()

        // Should select the first item
        expect(workbenchStore.selectedItemId).toBe(items[0].id)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Property 11: selectPrevious with no selection selects last item
   *
   * For any list of items, when no item is selected,
   * calling selectPrevious SHALL select the last item in the list.
   *
   * **Validates: Requirements 7.2**
   */
  it('Property 11: Keyboard Navigation Changes Selection - selectPrevious with no selection selects last item', async () => {
    await fc.assert(
      fc.asyncProperty(historyItemsArb, async (items) => {
        setActivePinia(createPinia())
        localStorage.clear()

        const { workbenchStore } = setupStoresWithItems(items)

        // Ensure no selection
        expect(workbenchStore.selectedItemId).toBeNull()

        // Call selectPrevious with no selection
        workbenchStore.selectPrevious()

        // Should select the last item
        const lastItem = items[items.length - 1]
        expect(workbenchStore.selectedItemId).toBe(lastItem.id)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Property 11: Sequential navigation traverses all items
   *
   * For any list of items, starting from the first item and calling selectNext
   * (items.length - 1) times SHALL visit every item in order.
   *
   * **Validates: Requirements 7.2**
   */
  it('Property 11: Keyboard Navigation Changes Selection - sequential selectNext traverses all items', async () => {
    await fc.assert(
      fc.asyncProperty(historyItemsArb, async (items) => {
        setActivePinia(createPinia())
        localStorage.clear()

        const { workbenchStore } = setupStoresWithItems(items)

        // Start from first item
        await workbenchStore.selectItem(items[0].id)

        // Navigate through all items using selectNext
        const visitedIds: number[] = [workbenchStore.selectedItemId!]

        for (let i = 1; i < items.length; i++) {
          workbenchStore.selectNext()
          visitedIds.push(workbenchStore.selectedItemId!)
        }

        // Verify we visited all items in order
        expect(visitedIds).toHaveLength(items.length)
        for (let i = 0; i < items.length; i++) {
          expect(visitedIds[i]).toBe(items[i].id)
        }

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Property 11: Sequential reverse navigation traverses all items
   *
   * For any list of items, starting from the last item and calling selectPrevious
   * (items.length - 1) times SHALL visit every item in reverse order.
   *
   * **Validates: Requirements 7.2**
   */
  it('Property 11: Keyboard Navigation Changes Selection - sequential selectPrevious traverses all items in reverse', async () => {
    await fc.assert(
      fc.asyncProperty(historyItemsArb, async (items) => {
        setActivePinia(createPinia())
        localStorage.clear()

        const { workbenchStore } = setupStoresWithItems(items)

        // Start from last item
        const lastItem = items[items.length - 1]
        await workbenchStore.selectItem(lastItem.id)

        // Navigate through all items using selectPrevious
        const visitedIds: number[] = [workbenchStore.selectedItemId!]

        for (let i = items.length - 2; i >= 0; i--) {
          workbenchStore.selectPrevious()
          visitedIds.push(workbenchStore.selectedItemId!)
        }

        // Verify we visited all items in reverse order
        expect(visitedIds).toHaveLength(items.length)
        for (let i = 0; i < items.length; i++) {
          expect(visitedIds[i]).toBe(items[items.length - 1 - i].id)
        }

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  /**
   * Property 11: Random navigation sequence maintains valid selection
   *
   * For any list of items and any random sequence of up/down navigation commands,
   * the selection SHALL always be a valid item in the list.
   *
   * **Validates: Requirements 7.2**
   */
  it('Property 11: Keyboard Navigation Changes Selection - random navigation maintains valid selection', async () => {
    // Arbitrary for navigation commands
    const navigationCommandArb = fc.constantFrom('next', 'previous') as fc.Arbitrary<'next' | 'previous'>
    const navigationSequenceArb = fc.array(navigationCommandArb, { minLength: 1, maxLength: 50 })

    await fc.assert(
      fc.asyncProperty(
        historyItemsArb,
        navigationSequenceArb,
        async (items, commands) => {
          setActivePinia(createPinia())
          localStorage.clear()

          const { workbenchStore } = setupStoresWithItems(items)

          // Start with first item selected
          await workbenchStore.selectItem(items[0].id)

          // Execute random navigation sequence
          for (const command of commands) {
            if (command === 'next') {
              workbenchStore.selectNext()
            } else {
              workbenchStore.selectPrevious()
            }

            // Invariant: selection is always valid
            expect(workbenchStore.selectedItemId).not.toBeNull()
            const selectedItem = items.find((item) => item.id === workbenchStore.selectedItemId)
            expect(selectedItem).toBeDefined()
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

  /**
   * Property 11: Navigation on empty list does nothing
   *
   * For an empty list, calling selectNext or selectPrevious SHALL NOT crash
   * and SHALL leave selection as null.
   *
   * **Validates: Requirements 7.2**
   */
  it('Property 11: Keyboard Navigation Changes Selection - navigation on empty list is safe', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom('next', 'previous') as fc.Arbitrary<'next' | 'previous'>,
        fc.nat({ max: 10 }),
        async (command, repeatCount) => {
          setActivePinia(createPinia())
          localStorage.clear()

          const { workbenchStore } = setupStoresWithItems([])

          // Execute navigation on empty list multiple times
          for (let i = 0; i <= repeatCount; i++) {
            if (command === 'next') {
              workbenchStore.selectNext()
            } else {
              workbenchStore.selectPrevious()
            }

            // Selection should remain null
            expect(workbenchStore.selectedItemId).toBeNull()
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
