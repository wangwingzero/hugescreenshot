/**
 * Property-Based Tests for Notification Settings
 *
 * Feature: settings-enhancement
 *
 * This file tests the notification toggle behavior:
 * - Property 10: Toggle State Reactivity
 *
 * **Validates: Requirements 7.3**
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import * as fc from 'fast-check'
import { useSettingsStore } from '@/stores/settings'

// ============================================================================
// Test Setup
// ============================================================================

/**
 * All notification toggle keys
 */
const notificationKeys = [
  'startup',
  'screenshotSave',
  'pinImage',
  'recordingComplete',
  'softwareUpdate',
] as const

type NotificationKey = typeof notificationKeys[number]

// ============================================================================
// Property 10: Toggle State Reactivity
// ============================================================================

describe('Feature: settings-enhancement, Property 10: Toggle State Reactivity', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should update notification state immediately when toggle changes', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...notificationKeys),
        fc.boolean(),
        (key: NotificationKey, value: boolean) => {
          const store = useSettingsStore()
          
          // Update the notification setting
          store.updateNotification({ [key]: value })
          
          // Verify the state was updated immediately
          expect(store.notification[key]).toBe(value)
        }
      ),
      { numRuns: 100, verbose: true }
    )
  })

  it('should set isDirty flag when any notification toggle changes', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...notificationKeys),
        fc.boolean(),
        (key: NotificationKey, value: boolean) => {
          const store = useSettingsStore()
          
          // Reset dirty flag
          store.$patch({ isDirty: false })
          
          // Update the notification setting
          store.updateNotification({ [key]: value })
          
          // Verify isDirty is set
          expect(store.isDirty).toBe(true)
        }
      ),
      { numRuns: 100, verbose: true }
    )
  })

  it('should preserve other notification settings when updating one', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...notificationKeys),
        fc.boolean(),
        fc.record({
          startup: fc.boolean(),
          screenshotSave: fc.boolean(),
          pinImage: fc.boolean(),
          recordingComplete: fc.boolean(),
          softwareUpdate: fc.boolean(),
        }),
        (keyToUpdate: NotificationKey, newValue: boolean, initialState: Record<NotificationKey, boolean>) => {
          const store = useSettingsStore()
          
          // Set initial state for all notification settings
          store.updateNotification(initialState)
          
          // Update only one setting
          store.updateNotification({ [keyToUpdate]: newValue })
          
          // Verify the updated setting has the new value
          expect(store.notification[keyToUpdate]).toBe(newValue)
          
          // Verify other settings are preserved
          for (const key of notificationKeys) {
            if (key !== keyToUpdate) {
              expect(store.notification[key]).toBe(initialState[key])
            }
          }
        }
      ),
      { numRuns: 100, verbose: true }
    )
  })

  it('should handle multiple sequential toggle updates correctly', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            key: fc.constantFrom(...notificationKeys),
            value: fc.boolean(),
          }),
          { minLength: 1, maxLength: 10 }
        ),
        (updates: Array<{ key: NotificationKey; value: boolean }>) => {
          const store = useSettingsStore()
          
          // Apply all updates sequentially
          for (const update of updates) {
            store.updateNotification({ [update.key]: update.value })
          }
          
          // Build expected final state by applying updates in order
          const expectedState: Partial<Record<NotificationKey, boolean>> = {}
          for (const update of updates) {
            expectedState[update.key] = update.value
          }
          
          // Verify final state matches expected
          for (const [key, value] of Object.entries(expectedState)) {
            expect(store.notification[key as NotificationKey]).toBe(value)
          }
        }
      ),
      { numRuns: 100, verbose: true }
    )
  })

  it('should have exactly 5 notification toggle options', () => {
    expect(notificationKeys.length).toBe(5)
  })

  it('should have all notification keys defined in store', () => {
    const store = useSettingsStore()
    
    for (const key of notificationKeys) {
      expect(store.notification).toHaveProperty(key)
      expect(typeof store.notification[key]).toBe('boolean')
    }
  })
})
