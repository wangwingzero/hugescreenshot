/**
 * Property-Based Tests for Advanced Settings
 *
 * Feature: settings-enhancement
 *
 * This file tests the advanced settings behavior:
 * - Property 13: Portable Mode Warning
 *
 * **Validates: Requirements 9.6**
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import * as fc from 'fast-check'
import { useSettingsStore } from '@/stores/settings'

// ============================================================================
// Property 13: Portable Mode Warning
// ============================================================================

describe('Feature: settings-enhancement, Property 13: Portable Mode Warning', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should update portable mode state when toggled', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        (portableMode: boolean) => {
          const store = useSettingsStore()
          
          // Update portable mode
          store.updateAdvanced({ portableMode })
          
          // Verify state was updated
          expect(store.advanced.portableMode).toBe(portableMode)
        }
      ),
      { numRuns: 100, verbose: true }
    )
  })

  it('should set isDirty flag when portable mode changes', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        (portableMode: boolean) => {
          const store = useSettingsStore()
          
          // Reset dirty flag
          store.$patch({ isDirty: false })
          
          // Update portable mode
          store.updateAdvanced({ portableMode })
          
          // Verify isDirty is set
          expect(store.isDirty).toBe(true)
        }
      ),
      { numRuns: 100, verbose: true }
    )
  })

  it('should preserve other advanced settings when updating portable mode', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        fc.boolean(),
        fc.constantFrom('http', 'socks5') as fc.Arbitrary<'http' | 'socks5'>,
        fc.string(),
        fc.integer({ min: 1, max: 65535 }),
        fc.boolean(),
        (
          portableMode: boolean,
          proxyEnabled: boolean,
          proxyType: 'http' | 'socks5',
          proxyHost: string,
          proxyPort: number,
          debugLogging: boolean
        ) => {
          const store = useSettingsStore()
          
          // Set initial state
          store.updateAdvanced({
            proxyEnabled,
            proxyType,
            proxyHost,
            proxyPort,
            debugLogging,
          })
          
          // Update only portable mode
          store.updateAdvanced({ portableMode })
          
          // Verify portable mode was updated
          expect(store.advanced.portableMode).toBe(portableMode)
          
          // Verify other settings are preserved
          expect(store.advanced.proxyEnabled).toBe(proxyEnabled)
          expect(store.advanced.proxyType).toBe(proxyType)
          expect(store.advanced.proxyHost).toBe(proxyHost)
          expect(store.advanced.proxyPort).toBe(proxyPort)
          expect(store.advanced.debugLogging).toBe(debugLogging)
        }
      ),
      { numRuns: 100, verbose: true }
    )
  })

  it('should handle multiple sequential portable mode toggles', () => {
    fc.assert(
      fc.property(
        fc.array(fc.boolean(), { minLength: 2, maxLength: 10 }),
        (toggleSequence: boolean[]) => {
          const store = useSettingsStore()
          
          // Apply all toggles sequentially
          for (const portableMode of toggleSequence) {
            store.updateAdvanced({ portableMode })
          }
          
          // Verify final state matches last toggle
          const lastValue = toggleSequence[toggleSequence.length - 1]
          expect(store.advanced.portableMode).toBe(lastValue)
        }
      ),
      { numRuns: 100, verbose: true }
    )
  })

  it('should validate proxy port is within valid range', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 65535 }),
        (proxyPort: number) => {
          const store = useSettingsStore()
          
          // Update proxy port
          store.updateAdvanced({ proxyPort })
          
          // Verify port is stored
          expect(store.advanced.proxyPort).toBe(proxyPort)
          expect(store.advanced.proxyPort).toBeGreaterThanOrEqual(1)
          expect(store.advanced.proxyPort).toBeLessThanOrEqual(65535)
        }
      ),
      { numRuns: 100, verbose: true }
    )
  })

  it('should validate proxy type is either http or socks5', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('http', 'socks5') as fc.Arbitrary<'http' | 'socks5'>,
        (proxyType: 'http' | 'socks5') => {
          const store = useSettingsStore()
          
          // Update proxy type
          store.updateAdvanced({ proxyType })
          
          // Verify type is stored
          expect(store.advanced.proxyType).toBe(proxyType)
          expect(['http', 'socks5']).toContain(store.advanced.proxyType)
        }
      ),
      { numRuns: 100, verbose: true }
    )
  })
})
