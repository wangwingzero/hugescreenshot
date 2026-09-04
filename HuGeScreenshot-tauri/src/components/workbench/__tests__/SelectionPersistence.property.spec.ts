/**
 * Property-Based Tests for Selection Persistence Round-Trip
 *
 * Feature: workbench-layout-redesign, Property 12: Selection Persistence Round-Trip
 *
 * **Validates: Requirements 7.4**
 *
 * Property Definition:
 * For any selected item, closing and reopening the workbench window SHALL restore
 * the same item as selected.
 *
 * This test file verifies:
 * 1. Selected item ID is persisted to localStorage
 * 2. Restoring from localStorage restores the correct selection
 * 3. Round-trip persistence maintains selection identity
 * 4. Invalid persisted IDs are handled gracefully
 * 5. Clearing selection removes persisted value
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import * as fc from 'fast-check'
import { useWorkbenchStore } from '@/stores/workbench'
import { useHistoryStore } from '@/stores/history'
import type { HistoryItem, HistoryMetadata } from '@/types'

// ============================================================================
// Mock Tauri APIs
// ============================================================================

// Mock Tauri invoke to prevent actual backend calls
vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn().mockResolvedValue({}),
}))

// Mock clipboard manager
vi.mock('@tauri-apps/plugin-clipboard-manager', () => ({
  writeText: vi.fn().mockResolvedValue(undefined),
}))

// ============================================================================
// Constants (mirrored from workbench.ts)
// ============================================================================

/** Storage key for selected item ID */
const STORAGE_KEY_SELECTED_ITEM_ID = 'workbench_selected_item_id'

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

/**
 * Simulate closing and reopening the workbench window
 * This creates a new Pinia instance and new store instances,
 * simulating what happens when the window is closed and reopened.
 */
function simulateWindowReopen(items: HistoryItem[]): {
  workbenchStore: ReturnType<typeof useWorkbenchStore>
  historyStore: ReturnType<typeof useHistoryStore>
} {
  // Create fresh Pinia instance (simulates window close/reopen)
  setActivePinia(createPinia())

  // Setup stores with the same items
  return setupStoresWithItems(items)
}

// ============================================================================
// Property Tests
// ============================================================================

describe('Feature: workbench-layout-redesign, Property 12: Selection Persistence Round-Trip', () => {
  beforeEach(() => {
    // Create a fresh Pinia instance before each test
    setActivePinia(createPinia())
    // Clear localStorage to prevent state persistence interference
    localStorage.clear()
  })

  // ==========================================================================
  // Property 12.1: Selected item ID is persisted to localStorage
  // ==========================================================================

  it('Property 12: Selection is persisted to localStorage when item is selected', async () => {
    await fc.assert(
      fc.asyncProperty(historyItemsArb, async (items) => {
        // Fresh pinia for each iteration
        setActivePinia(createPinia())
        localStorage.clear()

        const { workbenchStore } = setupStoresWithItems(items)

        // Select an item
        const itemToSelect = items[0]
        await workbenchStore.selectItem(itemToSelect.id)

        // Verify localStorage contains the selected item ID
        const storedValue = localStorage.getItem(STORAGE_KEY_SELECTED_ITEM_ID)
        expect(storedValue).not.toBeNull()
        expect(parseInt(storedValue!, 10)).toBe(itemToSelect.id)

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 12.2: Round-trip persistence maintains selection identity
  // ==========================================================================

  it('Property 12: Closing and reopening workbench restores the same selected item', async () => {
    await fc.assert(
      fc.asyncProperty(
        historyItemsArb,
        fc.nat({ max: 100 }),
        async (items, indexSeed) => {
          // Fresh pinia for each iteration
          setActivePinia(createPinia())
          localStorage.clear()

          const { workbenchStore } = setupStoresWithItems(items)

          // Select a random item
          const itemIndex = indexSeed % items.length
          const itemToSelect = items[itemIndex]
          await workbenchStore.selectItem(itemToSelect.id)

          // Verify selection is set
          expect(workbenchStore.selectedItemId).toBe(itemToSelect.id)

          // Simulate window close and reopen
          const { workbenchStore: newWorkbenchStore } = simulateWindowReopen(items)

          // Restore from storage (simulates initialize on mount)
          newWorkbenchStore.restoreFromStorage()

          // Property: The same item SHALL be selected after reopening
          expect(newWorkbenchStore.selectedItemId).toBe(itemToSelect.id)

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
  // Property 12.3: Full initialization restores selection and OCR text
  // ==========================================================================

  it('Property 12: Full initialization restores selection and loads OCR text', async () => {
    await fc.assert(
      fc.asyncProperty(
        historyItemsArb,
        fc.nat({ max: 100 }),
        async (items, indexSeed) => {
          // Fresh pinia for each iteration
          setActivePinia(createPinia())
          localStorage.clear()

          const { workbenchStore } = setupStoresWithItems(items)

          // Select a random item
          const itemIndex = indexSeed % items.length
          const itemToSelect = items[itemIndex]
          await workbenchStore.selectItem(itemToSelect.id)

          // Verify initial state
          const originalOcrText = itemToSelect.ocrText ?? ''
          expect(workbenchStore.ocrText).toBe(originalOcrText)

          // Simulate window close and reopen
          const { workbenchStore: newWorkbenchStore } = simulateWindowReopen(items)

          // Call initialize (what happens on component mount)
          await newWorkbenchStore.initialize()

          // Property: Selection and OCR text SHALL be restored
          expect(newWorkbenchStore.selectedItemId).toBe(itemToSelect.id)
          expect(newWorkbenchStore.ocrText).toBe(originalOcrText)

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
  // Property 12.4: Clearing selection removes persisted value
  // ==========================================================================

  it('Property 12: Clearing selection removes persisted value from localStorage', async () => {
    await fc.assert(
      fc.asyncProperty(historyItemsArb, async (items) => {
        // Fresh pinia for each iteration
        setActivePinia(createPinia())
        localStorage.clear()

        const { workbenchStore } = setupStoresWithItems(items)

        // Select an item
        await workbenchStore.selectItem(items[0].id)

        // Verify localStorage has the value
        expect(localStorage.getItem(STORAGE_KEY_SELECTED_ITEM_ID)).not.toBeNull()

        // Clear selection
        workbenchStore.clearSelection()

        // Property: localStorage SHALL NOT contain the selected item ID after clearing
        expect(localStorage.getItem(STORAGE_KEY_SELECTED_ITEM_ID)).toBeNull()

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 12.5: Invalid persisted ID is handled gracefully
  // ==========================================================================

  it('Property 12: Invalid persisted ID does not crash and sets selectedItemId', async () => {
    await fc.assert(
      fc.asyncProperty(
        historyItemsArb,
        fc.integer({ min: 100000, max: 999999 }), // ID that won't exist in items
        async (items, invalidId) => {
          // Fresh pinia for each iteration
          setActivePinia(createPinia())
          localStorage.clear()

          // Manually set an invalid ID in localStorage
          localStorage.setItem(STORAGE_KEY_SELECTED_ITEM_ID, String(invalidId))

          const { workbenchStore } = setupStoresWithItems(items)

          // Restore from storage should not crash
          workbenchStore.restoreFromStorage()

          // The selectedItemId is set from localStorage (even if item doesn't exist)
          // This is the current behavior - the ID is restored, but selectedItem computed will be null
          expect(workbenchStore.selectedItemId).toBe(invalidId)

          // The selectedItem computed property should be null since item doesn't exist
          expect(workbenchStore.selectedItem).toBeNull()

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
  // Property 12.6: Non-numeric persisted value is handled gracefully
  // ==========================================================================

  it('Property 12: Non-numeric persisted value is handled gracefully', async () => {
    await fc.assert(
      fc.asyncProperty(
        historyItemsArb,
        fc.string({ minLength: 1, maxLength: 20 }).filter((s) => isNaN(parseInt(s, 10))),
        async (items, invalidValue) => {
          // Fresh pinia for each iteration
          setActivePinia(createPinia())
          localStorage.clear()

          // Manually set a non-numeric value in localStorage
          localStorage.setItem(STORAGE_KEY_SELECTED_ITEM_ID, invalidValue)

          const { workbenchStore } = setupStoresWithItems(items)

          // Restore from storage should not crash
          workbenchStore.restoreFromStorage()

          // Property: Non-numeric values should result in null selection (NaN check in code)
          // The parseInt returns NaN, and the code checks !isNaN(id) before setting
          expect(workbenchStore.selectedItemId).toBeNull()

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
  // Property 12.7: Empty localStorage results in no selection
  // ==========================================================================

  it('Property 12: Empty localStorage results in no selection after restore', async () => {
    await fc.assert(
      fc.asyncProperty(historyItemsArb, async (items) => {
        // Fresh pinia for each iteration
        setActivePinia(createPinia())
        localStorage.clear()

        const { workbenchStore } = setupStoresWithItems(items)

        // Restore from empty storage
        workbenchStore.restoreFromStorage()

        // Property: No selection should be set
        expect(workbenchStore.selectedItemId).toBeNull()
        expect(workbenchStore.selectedItem).toBeNull()

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 12.8: Multiple selections persist only the last one
  // ==========================================================================

  it('Property 12: Multiple selections persist only the last selected item', async () => {
    await fc.assert(
      fc.asyncProperty(
        historyItemsArb.filter((items) => items.length >= 3),
        async (items) => {
          // Fresh pinia for each iteration
          setActivePinia(createPinia())
          localStorage.clear()

          const { workbenchStore } = setupStoresWithItems(items)

          // Select multiple items in sequence
          await workbenchStore.selectItem(items[0].id)
          await workbenchStore.selectItem(items[1].id)
          await workbenchStore.selectItem(items[2].id)

          // Verify only the last selection is persisted
          const storedValue = localStorage.getItem(STORAGE_KEY_SELECTED_ITEM_ID)
          expect(parseInt(storedValue!, 10)).toBe(items[2].id)

          // Simulate window reopen
          const { workbenchStore: newWorkbenchStore } = simulateWindowReopen(items)
          newWorkbenchStore.restoreFromStorage()

          // Property: Only the last selected item SHALL be restored
          expect(newWorkbenchStore.selectedItemId).toBe(items[2].id)

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
  // Property 12.9: Persistence is idempotent
  // ==========================================================================

  it('Property 12: Selecting the same item multiple times persists the same value', async () => {
    await fc.assert(
      fc.asyncProperty(
        historyItemsArb,
        fc.integer({ min: 1, max: 10 }),
        async (items, repeatCount) => {
          // Fresh pinia for each iteration
          setActivePinia(createPinia())
          localStorage.clear()

          const { workbenchStore } = setupStoresWithItems(items)

          const itemToSelect = items[0]

          // Select the same item multiple times
          for (let i = 0; i < repeatCount; i++) {
            await workbenchStore.selectItem(itemToSelect.id)
          }

          // Verify localStorage contains the correct value
          const storedValue = localStorage.getItem(STORAGE_KEY_SELECTED_ITEM_ID)
          expect(parseInt(storedValue!, 10)).toBe(itemToSelect.id)

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
  // Property 12.10: Persistence survives multiple window reopens
  // ==========================================================================

  it('Property 12: Selection persists across multiple window close/reopen cycles', async () => {
    await fc.assert(
      fc.asyncProperty(
        historyItemsArb,
        fc.integer({ min: 2, max: 5 }),
        async (items, reopenCount) => {
          // Fresh pinia for each iteration
          setActivePinia(createPinia())
          localStorage.clear()

          let workbenchStore = setupStoresWithItems(items).workbenchStore

          // Select an item
          const itemToSelect = items[0]
          await workbenchStore.selectItem(itemToSelect.id)

          // Simulate multiple window close/reopen cycles
          for (let i = 0; i < reopenCount; i++) {
            const { workbenchStore: newStore } = simulateWindowReopen(items)
            newStore.restoreFromStorage()

            // Property: Selection SHALL be maintained across each reopen
            expect(newStore.selectedItemId).toBe(itemToSelect.id)

            workbenchStore = newStore
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
  // Property 12.11: Selection persistence works for all items in list
  // ==========================================================================

  it('Property 12: Any item in the list can be persisted and restored', async () => {
    await fc.assert(
      fc.asyncProperty(historyItemsArb, async (items) => {
        // Test persistence for each item in the list
        for (const item of items) {
          // Fresh pinia for each item test
          setActivePinia(createPinia())
          localStorage.clear()

          const { workbenchStore } = setupStoresWithItems(items)

          // Select this item
          await workbenchStore.selectItem(item.id)

          // Simulate window reopen
          const { workbenchStore: newWorkbenchStore } = simulateWindowReopen(items)
          await newWorkbenchStore.initialize()

          // Property: This specific item SHALL be restored
          expect(newWorkbenchStore.selectedItemId).toBe(item.id)
          expect(newWorkbenchStore.ocrText).toBe(item.ocrText ?? '')
        }

        return true
      }),
      {
        numRuns: 50, // Fewer runs since we test each item
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 12.12: Persisted value format is correct
  // ==========================================================================

  it('Property 12: Persisted value is stored as a string representation of the ID', async () => {
    await fc.assert(
      fc.asyncProperty(historyItemsArb, async (items) => {
        // Fresh pinia for each iteration
        setActivePinia(createPinia())
        localStorage.clear()

        const { workbenchStore } = setupStoresWithItems(items)

        const itemToSelect = items[0]
        await workbenchStore.selectItem(itemToSelect.id)

        // Verify the stored value is a string
        const storedValue = localStorage.getItem(STORAGE_KEY_SELECTED_ITEM_ID)
        expect(typeof storedValue).toBe('string')

        // Verify it can be parsed back to the original ID
        expect(parseInt(storedValue!, 10)).toBe(itemToSelect.id)

        // Verify the string representation matches
        expect(storedValue).toBe(String(itemToSelect.id))

        return true
      }),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  // ==========================================================================
  // Property 12.13: Selection and OCR text are consistent after restore
  // ==========================================================================

  it('Property 12: Restored selection has consistent OCR text', async () => {
    await fc.assert(
      fc.asyncProperty(
        historyItemsArb,
        fc.nat({ max: 100 }),
        async (items, indexSeed) => {
          // Fresh pinia for each iteration
          setActivePinia(createPinia())
          localStorage.clear()

          const { workbenchStore } = setupStoresWithItems(items)

          // Select a random item
          const itemIndex = indexSeed % items.length
          const itemToSelect = items[itemIndex]
          await workbenchStore.selectItem(itemToSelect.id)

          // Simulate window reopen and initialize
          const { workbenchStore: newWorkbenchStore, historyStore: _newHistoryStore } = simulateWindowReopen(items)
          await newWorkbenchStore.initialize()

          // Property: selectedItem computed should return the correct item
          const restoredItem = newWorkbenchStore.selectedItem
          expect(restoredItem).not.toBeNull()
          expect(restoredItem?.id).toBe(itemToSelect.id)

          // Property: OCR text should match the item's OCR text
          expect(newWorkbenchStore.ocrText).toBe(itemToSelect.ocrText ?? '')

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
  // Property 12.14: Deleted item handling after restore
  // ==========================================================================

  it('Property 12: Restoring selection for deleted item results in null selectedItem', async () => {
    await fc.assert(
      fc.asyncProperty(
        historyItemsArb.filter((items) => items.length >= 2),
        async (items) => {
          // Fresh pinia for each iteration
          setActivePinia(createPinia())
          localStorage.clear()

          const { workbenchStore } = setupStoresWithItems(items)

          // Select the first item
          const itemToSelect = items[0]
          await workbenchStore.selectItem(itemToSelect.id)

          // Simulate window reopen with the item removed from the list
          const itemsWithoutFirst = items.slice(1)
          const { workbenchStore: newWorkbenchStore } = simulateWindowReopen(itemsWithoutFirst)
          newWorkbenchStore.restoreFromStorage()

          // The ID is restored from localStorage
          expect(newWorkbenchStore.selectedItemId).toBe(itemToSelect.id)

          // But selectedItem computed should be null since item doesn't exist
          expect(newWorkbenchStore.selectedItem).toBeNull()

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
