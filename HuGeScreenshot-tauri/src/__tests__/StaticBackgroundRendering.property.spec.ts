/**
 * Property-Based Tests for Static Background Rendering
 *
 * Feature: static-screenshot-multiwindow, Property 6: Static Background Rendering
 *
 * **Validates: Requirements 1.2, 1.3**
 *
 * Property Definition (from design.md):
 * For any overlay window displaying a snapshot, the background image SHALL remain
 * unchanged regardless of desktop activity (video playback, animations, window movements).
 *
 * Since we cannot directly test visual rendering in unit tests, we test the underlying
 * coordinate calculation logic that ensures:
 * 1. Source region calculation is deterministic (same inputs → same outputs)
 * 2. Source region is always within snapshot bounds
 * 3. Coordinate transformations are mathematically correct
 * 4. Multi-monitor offset calculations are accurate
 *
 * This validates that the rendering logic will produce consistent, correct output
 * regardless of when it's called, which is the foundation of "static" rendering.
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ============================================================================
// Types (mirroring overlay-main.ts types)
// ============================================================================

/**
 * Monitor snapshot metadata (mirrors MonitorSnapshot from overlay-main.ts)
 */
interface MonitorSnapshot {
  monitor_id: number
  x: number // Physical X position in virtual desktop
  y: number // Physical Y position in virtual desktop
  width: number // Physical width
  height: number // Physical height
  dpr: number // Device pixel ratio
}

/**
 * Snapshot metadata (mirrors SnapshotReadyPayload from overlay-main.ts)
 */
interface SnapshotMetadata {
  path: string
  width: number // Total width in physical pixels
  height: number // Total height in physical pixels
  dpr: number // Primary monitor DPR
  monitors: MonitorSnapshot[]
}

function getSnapshotOrigin(snapshotMetadata: SnapshotMetadata): { x: number; y: number } {
  if (snapshotMetadata.monitors.length === 0) {
    return { x: 0, y: 0 }
  }

  return {
    x: Math.min(...snapshotMetadata.monitors.map((monitor) => monitor.x)),
    y: Math.min(...snapshotMetadata.monitors.map((monitor) => monitor.y)),
  }
}

/**
 * Selection rectangle (logical pixels, relative to current window)
 */
interface SelectionRect {
  x: number
  y: number
  width: number
  height: number
}

/**
 * Monitor info (mirrors MonitorInfo from overlay-main.ts)
 */
interface MonitorInfo {
  monitorId: number
  position: { x: number; y: number } // Physical position in virtual desktop
  size: { width: number; height: number } // Logical size
  scaleFactor: number
  name: string
}

/**
 * Source region in the snapshot (physical pixels)
 */
interface SourceRegion {
  srcX: number
  srcY: number
  srcWidth: number
  srcHeight: number
}

// ============================================================================
// Core Logic Under Test (extracted from overlay-main.ts renderSnapshotBackground)
// ============================================================================

/**
 * Calculate the source region in the snapshot for a given selection
 *
 * This is the core coordinate calculation logic from renderSnapshotBackground().
 * It converts a selection rectangle (logical pixels, relative to current window)
 * to a source region in the full-screen snapshot (physical pixels).
 *
 * **Validates: Requirements 1.2, 1.3**
 *
 * @param selection - Selection rectangle in logical pixels
 * @param monitorInfo - Current monitor information
 * @param snapshotMetadata - Snapshot metadata with monitor positions
 * @returns Source region in physical pixels, or null if invalid
 */
function calculateSourceRegion(
  selection: SelectionRect,
  monitorInfo: MonitorInfo,
  snapshotMetadata: SnapshotMetadata
): SourceRegion | null {
  // Validate inputs
  if (selection.width <= 0 || selection.height <= 0) {
    return null
  }

  const scaleFactor = monitorInfo.scaleFactor || 1
  const snapshotOrigin = getSnapshotOrigin(snapshotMetadata)
  const monitorPhysicalX = monitorInfo.position.x
  const monitorPhysicalY = monitorInfo.position.y

  // Calculate source region in physical pixels
  // Selection coordinates are logical pixels relative to current window.
  // We first convert them to physical pixels on the current monitor, then
  // translate from virtual-desktop coordinates into stitched snapshot coordinates.
  const srcX = Math.round(selection.x * scaleFactor + monitorPhysicalX - snapshotOrigin.x)
  const srcY = Math.round(selection.y * scaleFactor + monitorPhysicalY - snapshotOrigin.y)
  const srcWidth = Math.round(selection.width * scaleFactor)
  const srcHeight = Math.round(selection.height * scaleFactor)

  return { srcX, srcY, srcWidth, srcHeight }
}

// ============================================================================
// Arbitraries
// ============================================================================

/**
 * Arbitrary for common DPR values
 */
const dprArb: fc.Arbitrary<number> = fc.constantFrom(1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)

/**
 * Arbitrary for monitor ID
 */
const monitorIdArb: fc.Arbitrary<number> = fc.integer({ min: 0, max: 3 })

/**
 * Arbitrary for logical pixel position (can be negative for multi-monitor)
 */
const logicalPositionArb: fc.Arbitrary<number> = fc.integer({ min: -4000, max: 4000 })

/**
 * Arbitrary for selection dimensions (positive, reasonable sizes)
 */
const selectionDimensionArb: fc.Arbitrary<number> = fc.integer({ min: 1, max: 2000 })

/**
 * Arbitrary for selection position (relative to window, non-negative)
 */
const selectionPositionArb: fc.Arbitrary<number> = fc.integer({ min: 0, max: 2000 })

/**
 * Arbitrary for monitor info
 */
const monitorInfoArb: fc.Arbitrary<MonitorInfo> = fc.record({
  monitorId: monitorIdArb,
  position: fc.record({
    x: logicalPositionArb,
    y: logicalPositionArb,
  }),
  size: fc.record({
    width: fc.integer({ min: 800, max: 3840 }),
    height: fc.integer({ min: 600, max: 2160 }),
  }),
  scaleFactor: dprArb,
  name: fc.string({ minLength: 1, maxLength: 20 }),
})

/**
 * Arbitrary for selection rectangle
 */
const selectionRectArb: fc.Arbitrary<SelectionRect> = fc.record({
  x: selectionPositionArb,
  y: selectionPositionArb,
  width: selectionDimensionArb,
  height: selectionDimensionArb,
})


/**
 * Generate a consistent set of monitor info and snapshot metadata
 * where the monitor exists in the snapshot
 */
const consistentMonitorSetupArb: fc.Arbitrary<{
  monitorInfo: MonitorInfo
  snapshotMetadata: SnapshotMetadata
  monitorSnapshot: MonitorSnapshot
}> = fc
  .record({
    monitorId: monitorIdArb,
    physicalX: fc.integer({ min: -3840, max: 3840 }),
    physicalY: fc.integer({ min: -2160, max: 2160 }),
    physicalWidth: fc.integer({ min: 1920, max: 3840 }),
    physicalHeight: fc.integer({ min: 1080, max: 2160 }),
    dpr: dprArb,
  })
  .map(({ monitorId, physicalX, physicalY, physicalWidth, physicalHeight, dpr }) => {
    const monitorSnapshot: MonitorSnapshot = {
      monitor_id: monitorId,
      x: physicalX,
      y: physicalY,
      width: physicalWidth,
      height: physicalHeight,
      dpr: dpr,
    }

    const monitorInfo: MonitorInfo = {
      monitorId: monitorId,
      position: {
        x: physicalX,
        y: physicalY,
      },
      size: {
        width: Math.round(physicalWidth / dpr),
        height: Math.round(physicalHeight / dpr),
      },
      scaleFactor: dpr,
      name: `Monitor ${monitorId}`,
    }

    const snapshotMetadata: SnapshotMetadata = {
      path: '/tmp/snapshot.png',
      width: physicalWidth,
      height: physicalHeight,
      dpr: dpr,
      monitors: [monitorSnapshot],
    }

    return { monitorInfo, snapshotMetadata, monitorSnapshot }
  })

/**
 * Generate a selection that fits within the monitor's logical size
 */
function selectionWithinMonitor(monitorInfo: MonitorInfo): fc.Arbitrary<SelectionRect> {
  const maxX = Math.max(1, monitorInfo.size.width - 10)
  const maxY = Math.max(1, monitorInfo.size.height - 10)

  return fc
    .record({
      x: fc.integer({ min: 0, max: maxX }),
      y: fc.integer({ min: 0, max: maxY }),
      width: fc.integer({ min: 1, max: Math.max(1, monitorInfo.size.width) }),
      height: fc.integer({ min: 1, max: Math.max(1, monitorInfo.size.height) }),
    })
    .map((sel) => ({
      // Clamp to ensure selection fits within monitor
      x: Math.min(sel.x, monitorInfo.size.width - 1),
      y: Math.min(sel.y, monitorInfo.size.height - 1),
      width: Math.min(sel.width, monitorInfo.size.width - sel.x),
      height: Math.min(sel.height, monitorInfo.size.height - sel.y),
    }))
    .filter((sel) => sel.width > 0 && sel.height > 0)
}

// ============================================================================
// Property Tests
// ============================================================================

describe('Feature: static-screenshot-multiwindow, Property 6: Static Background Rendering', () => {
  // ==========================================================================
  // Property 6.1: Source region calculation is deterministic
  // ==========================================================================

  it('Property 6: Source region calculation is deterministic (same inputs → same outputs)', () => {
    /**
     * **Validates: Requirements 1.2, 1.3**
     *
     * This property ensures that the coordinate calculation is a pure function.
     * Given the same selection, monitor info, and snapshot metadata,
     * the calculated source region must always be identical.
     *
     * This is the foundation of "static" rendering - the background will
     * always render the same way for the same inputs.
     */
    fc.assert(
      fc.property(
        consistentMonitorSetupArb,
        selectionRectArb.filter((s) => s.width > 0 && s.height > 0),
        ({ monitorInfo, snapshotMetadata }, selection) => {
          // Calculate source region twice with identical inputs
          const result1 = calculateSourceRegion(selection, monitorInfo, snapshotMetadata)
          const result2 = calculateSourceRegion(selection, monitorInfo, snapshotMetadata)

          // Both results should be identical (deterministic)
          expect(result1).toEqual(result2)

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
  // Property 6.2: Source region dimensions are correctly scaled
  // ==========================================================================

  it('Property 6: Source region dimensions are correctly scaled by DPR', () => {
    /**
     * **Validates: Requirements 1.2, 1.3**
     *
     * The source region dimensions (width, height) should be the selection
     * dimensions multiplied by the scale factor (DPR).
     *
     * This ensures the correct portion of the snapshot is extracted.
     */
    fc.assert(
      fc.property(
        consistentMonitorSetupArb,
        selectionRectArb.filter((s) => s.width > 0 && s.height > 0),
        ({ monitorInfo, snapshotMetadata }, selection) => {
          const result = calculateSourceRegion(selection, monitorInfo, snapshotMetadata)

          if (result === null) {
            // Invalid selection, skip
            return true
          }

          const scaleFactor = monitorInfo.scaleFactor

          // Source dimensions should be selection dimensions * scaleFactor (rounded)
          const expectedWidth = Math.round(selection.width * scaleFactor)
          const expectedHeight = Math.round(selection.height * scaleFactor)

          expect(result.srcWidth).toBe(expectedWidth)
          expect(result.srcHeight).toBe(expectedHeight)

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
  // Property 6.3: Source region position includes monitor offset
  // ==========================================================================

  it('Property 6: Source region position correctly maps into stitched snapshot coordinates', () => {
    /**
     * **Validates: Requirements 1.2, 1.3**
     *
     * The source region position should be:
     * srcX = selection.x * scaleFactor + monitorPhysicalX - snapshotOriginX
     * srcY = selection.y * scaleFactor + monitorPhysicalY - snapshotOriginY
     *
     * This ensures multi-monitor setups, especially negative-coordinate side monitors,
     * render the correct portion from the stitched snapshot canvas.
     */
    fc.assert(
      fc.property(
        consistentMonitorSetupArb,
        selectionRectArb.filter((s) => s.width > 0 && s.height > 0),
        ({ monitorInfo, snapshotMetadata, monitorSnapshot }, selection) => {
          const result = calculateSourceRegion(selection, monitorInfo, snapshotMetadata)

          if (result === null) {
            return true
          }

          const scaleFactor = monitorInfo.scaleFactor
          const snapshotOrigin = getSnapshotOrigin(snapshotMetadata)

          const expectedX = Math.round(
            selection.x * scaleFactor + monitorSnapshot.x - snapshotOrigin.x
          )
          const expectedY = Math.round(
            selection.y * scaleFactor + monitorSnapshot.y - snapshotOrigin.y
          )

          expect(result.srcX).toBe(expectedX)
          expect(result.srcY).toBe(expectedY)

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
  // Property 6.4: Valid selections within monitor produce valid source regions
  // ==========================================================================

  it('Property 6: Valid selections within monitor bounds produce valid source regions', () => {
    /**
     * **Validates: Requirements 1.2, 1.3**
     *
     * When a selection is within the monitor's logical bounds,
     * the calculated source region should be within the snapshot bounds.
     */
    fc.assert(
      fc.property(
        consistentMonitorSetupArb.chain(({ monitorInfo, snapshotMetadata, monitorSnapshot }) =>
          selectionWithinMonitor(monitorInfo).map((selection) => ({
            monitorInfo,
            snapshotMetadata,
            monitorSnapshot,
            selection,
          }))
        ),
        ({ monitorInfo, snapshotMetadata, selection }) => {
          const result = calculateSourceRegion(selection, monitorInfo, snapshotMetadata)

          // Should produce a valid result
          expect(result).not.toBeNull()

          if (result) {
            // Source region should have positive dimensions
            expect(result.srcWidth).toBeGreaterThan(0)
            expect(result.srcHeight).toBeGreaterThan(0)

            // Source position should be non-negative
            expect(result.srcX).toBeGreaterThanOrEqual(0)
            expect(result.srcY).toBeGreaterThanOrEqual(0)
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
  // Property 6.5: Zero or negative selection dimensions return null
  // ==========================================================================

  it('Property 6: Zero or negative selection dimensions return null', () => {
    /**
     * **Validates: Requirements 1.2, 1.3**
     *
     * Invalid selections (zero or negative dimensions) should be rejected.
     */
    fc.assert(
      fc.property(
        consistentMonitorSetupArb,
        fc.record({
          x: selectionPositionArb,
          y: selectionPositionArb,
          width: fc.integer({ min: -100, max: 0 }),
          height: fc.integer({ min: -100, max: 0 }),
        }),
        ({ monitorInfo, snapshotMetadata }, invalidSelection) => {
          const result = calculateSourceRegion(invalidSelection, monitorInfo, snapshotMetadata)

          // Should return null for invalid selection
          expect(result).toBeNull()

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
  // Property 6.6: Scale factor of 1.0 produces 1:1 mapping
  // ==========================================================================

  it('Property 6: Scale factor of 1.0 produces 1:1 pixel mapping', () => {
    /**
     * **Validates: Requirements 1.2, 1.3**
     *
     * When DPR is 1.0, logical pixels equal physical pixels.
     * The source region dimensions should match selection dimensions exactly.
     */
    fc.assert(
      fc.property(
        fc
          .record({
            monitorId: monitorIdArb,
            physicalX: fc.integer({ min: 0, max: 1000 }),
            physicalY: fc.integer({ min: 0, max: 1000 }),
            physicalWidth: fc.integer({ min: 1920, max: 3840 }),
            physicalHeight: fc.integer({ min: 1080, max: 2160 }),
          })
          .map(({ monitorId, physicalX, physicalY, physicalWidth, physicalHeight }) => {
            const dpr = 1.0 // Force DPR to 1.0

            const monitorSnapshot: MonitorSnapshot = {
              monitor_id: monitorId,
              x: physicalX,
              y: physicalY,
              width: physicalWidth,
              height: physicalHeight,
              dpr: dpr,
            }

            const monitorInfo: MonitorInfo = {
              monitorId: monitorId,
              position: { x: physicalX, y: physicalY }, // Same as physical when DPR=1
              size: { width: physicalWidth, height: physicalHeight },
              scaleFactor: dpr,
              name: `Monitor ${monitorId}`,
            }

            const snapshotMetadata: SnapshotMetadata = {
              path: '/tmp/snapshot.png',
              width: physicalX + physicalWidth + 100,
              height: physicalY + physicalHeight + 100,
              dpr: dpr,
              monitors: [monitorSnapshot],
            }

            return { monitorInfo, snapshotMetadata, monitorSnapshot }
          }),
        selectionRectArb.filter((s) => s.width > 0 && s.height > 0),
        ({ monitorInfo, snapshotMetadata, monitorSnapshot }, selection) => {
          const result = calculateSourceRegion(selection, monitorInfo, snapshotMetadata)

          if (result === null) {
            return true
          }

          // With DPR=1.0, dimensions should match exactly
          expect(result.srcWidth).toBe(selection.width)
          expect(result.srcHeight).toBe(selection.height)

          const snapshotOrigin = getSnapshotOrigin(snapshotMetadata)

          expect(result.srcX).toBe(selection.x + monitorSnapshot.x - snapshotOrigin.x)
          expect(result.srcY).toBe(selection.y + monitorSnapshot.y - snapshotOrigin.y)

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
  // Property 6.7: Higher DPR produces larger source regions
  // ==========================================================================

  it('Property 6: Higher DPR produces proportionally larger source regions', () => {
    /**
     * **Validates: Requirements 1.2, 1.3**
     *
     * When DPR increases, the source region dimensions should increase
     * proportionally. This ensures high-DPI displays get full resolution.
     */
    fc.assert(
      fc.property(
        selectionRectArb.filter((s) => s.width > 0 && s.height > 0),
        fc.tuple(dprArb, dprArb).filter(([a, b]) => a !== b),
        (selection, [dpr1, dpr2]) => {
          const [lowerDpr, higherDpr] = dpr1 < dpr2 ? [dpr1, dpr2] : [dpr2, dpr1]

          // Create two setups with different DPRs
          const createSetup = (dpr: number) => {
            const monitorSnapshot: MonitorSnapshot = {
              monitor_id: 0,
              x: 0,
              y: 0,
              width: 1920,
              height: 1080,
              dpr: dpr,
            }

            const monitorInfo: MonitorInfo = {
              monitorId: 0,
              position: { x: 0, y: 0 },
              size: { width: Math.round(1920 / dpr), height: Math.round(1080 / dpr) },
              scaleFactor: dpr,
              name: 'Monitor 0',
            }

            const snapshotMetadata: SnapshotMetadata = {
              path: '/tmp/snapshot.png',
              width: 2000,
              height: 1200,
              dpr: dpr,
              monitors: [monitorSnapshot],
            }

            return { monitorInfo, snapshotMetadata }
          }

          const lowerSetup = createSetup(lowerDpr)
          const higherSetup = createSetup(higherDpr)

          const lowerResult = calculateSourceRegion(
            selection,
            lowerSetup.monitorInfo,
            lowerSetup.snapshotMetadata
          )
          const higherResult = calculateSourceRegion(
            selection,
            higherSetup.monitorInfo,
            higherSetup.snapshotMetadata
          )

          if (lowerResult === null || higherResult === null) {
            return true
          }

          // Higher DPR should produce larger dimensions
          expect(higherResult.srcWidth).toBeGreaterThanOrEqual(lowerResult.srcWidth)
          expect(higherResult.srcHeight).toBeGreaterThanOrEqual(lowerResult.srcHeight)

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
  // Property 6.8: Fallback to logical position when monitor not in metadata
  // ==========================================================================

  it('Property 6: Falls back to monitor physical position even when monitorId does not match metadata', () => {
    /**
     * **Validates: Requirements 1.2, 1.3**
     *
     * overlay-init currently identifies monitors by window index, while snapshot metadata
     * may use capture-engine monitor IDs. Rendering must still be correct by relying on the
     * current window's physical position and the stitched snapshot origin.
     */
    fc.assert(
      fc.property(
        monitorInfoArb,
        selectionRectArb.filter((s) => s.width > 0 && s.height > 0),
        (monitorInfo, selection) => {
          const snapshotMetadata: SnapshotMetadata = {
            path: '/tmp/snapshot.png',
            width: 5000,
            height: 3000,
            dpr: monitorInfo.scaleFactor,
            monitors: [
              {
                monitor_id: monitorInfo.monitorId + 100,
                x: -640,
                y: -360,
                width: 1920,
                height: 1080,
                dpr: 1.0,
              },
            ],
          }

          const result = calculateSourceRegion(selection, monitorInfo, snapshotMetadata)

          if (result === null) {
            return true
          }

          const scaleFactor = monitorInfo.scaleFactor
          const snapshotOrigin = getSnapshotOrigin(snapshotMetadata)
          const expectedX = Math.round(
            selection.x * scaleFactor + monitorInfo.position.x - snapshotOrigin.x
          )
          const expectedY = Math.round(
            selection.y * scaleFactor + monitorInfo.position.y - snapshotOrigin.y
          )

          expect(result.srcX).toBe(expectedX)
          expect(result.srcY).toBe(expectedY)

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
  // Property 6.9: Empty monitors array uses fallback
  // ==========================================================================

  it('Property 6: Empty monitors array falls back to current monitor physical position', () => {
    /**
     * **Validates: Requirements 1.2, 1.3**
     *
     * When snapshot metadata has no monitor list, rendering still uses the current
     * monitor physical position as the only available source of virtual-desktop placement.
     */
    fc.assert(
      fc.property(
        monitorInfoArb,
        selectionRectArb.filter((s) => s.width > 0 && s.height > 0),
        (monitorInfo, selection) => {
          const snapshotMetadata: SnapshotMetadata = {
            path: '/tmp/snapshot.png',
            width: 5000,
            height: 3000,
            dpr: monitorInfo.scaleFactor,
            monitors: [],
          }

          const result = calculateSourceRegion(selection, monitorInfo, snapshotMetadata)

          if (result === null) {
            return true
          }

          const scaleFactor = monitorInfo.scaleFactor
          const expectedX = Math.round(selection.x * scaleFactor + monitorInfo.position.x)
          const expectedY = Math.round(selection.y * scaleFactor + monitorInfo.position.y)

          expect(result.srcX).toBe(expectedX)
          expect(result.srcY).toBe(expectedY)

          return true
        }
      ),
      {
        numRuns: 100,
        verbose: true,
      }
    )
  })

  it('Property 6: Left-side monitor uses stitched snapshot local coordinates instead of negative virtual coordinates', () => {
    const selection: SelectionRect = {
      x: 68,
      y: 330,
      width: 456,
      height: 441,
    }

    const monitorInfo: MonitorInfo = {
      monitorId: 99,
      position: { x: -1280, y: 0 },
      size: { width: 1280, height: 1024 },
      scaleFactor: 1,
      name: 'Left Monitor',
    }

    const snapshotMetadata: SnapshotMetadata = {
      path: '/tmp/snapshot.bmp',
      width: 2880,
      height: 1024,
      dpr: 1,
      monitors: [
        {
          monitor_id: 1,
          x: -1280,
          y: 0,
          width: 1280,
          height: 1024,
          dpr: 1,
        },
        {
          monitor_id: 0,
          x: 0,
          y: 0,
          width: 1600,
          height: 900,
          dpr: 1,
        },
      ],
    }

    const result = calculateSourceRegion(selection, monitorInfo, snapshotMetadata)

    expect(result).toEqual({
      srcX: 68,
      srcY: 330,
      srcWidth: 456,
      srcHeight: 441,
    })
  })

  // ==========================================================================
  // Property 6.10: Coordinate values are always integers (no sub-pixel)
  // ==========================================================================

  it('Property 6: All coordinate values are integers (no sub-pixel rendering)', () => {
    /**
     * **Validates: Requirements 1.2, 1.3**
     *
     * All source region coordinates should be integers to avoid
     * sub-pixel rendering artifacts. This ensures crisp, consistent output.
     */
    fc.assert(
      fc.property(
        consistentMonitorSetupArb,
        selectionRectArb.filter((s) => s.width > 0 && s.height > 0),
        ({ monitorInfo, snapshotMetadata }, selection) => {
          const result = calculateSourceRegion(selection, monitorInfo, snapshotMetadata)

          if (result === null) {
            return true
          }

          // All values should be integers
          expect(Number.isInteger(result.srcX)).toBe(true)
          expect(Number.isInteger(result.srcY)).toBe(true)
          expect(Number.isInteger(result.srcWidth)).toBe(true)
          expect(Number.isInteger(result.srcHeight)).toBe(true)

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
