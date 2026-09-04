import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  shouldAutoOcrOnSelection,
  shouldDestroyCurrentOverlayAfterTeardownFailure,
  shouldDeactivateOverlaySessionForOcrTeardown,
  shouldDeferOcrUntilCaptureComplete,
  shouldHideOverlayBeforeCachedOcrResult,
  shouldHideOverlayBeforeOcr,
  shouldRunOcrInBackendAfterOverlayHidden,
  shouldRestoreOverlayFocus,
  shouldRestoreOverlayFocusAfterCapture,
  shouldScheduleQueuedOcrAfterCapture,
  shouldTeardownOverlayBeforeBackendOcr,
  waitForOverlayVisualTeardown,
  overlayMonitorIdFromLabel,
  overlayOcrCommandName,
  type OcrOverlayRequest,
} from '../ocrOverlaySafety'

describe('ocr overlay safety', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('does not run automatic OCR while the screenshot overlay is still open', () => {
    expect(shouldAutoOcrOnSelection()).toBe(false)
  })

  it('hides the full-screen overlay before any user-facing OCR work', () => {
    const manualRequest: OcrOverlayRequest = {
      openPanel: true,
      copyText: true,
      reason: 'manual',
    }

    expect(shouldHideOverlayBeforeOcr(manualRequest)).toBe(true)
  })

  it('hides the overlay before background OCR too', () => {
    const backgroundRequest: OcrOverlayRequest = {
      openPanel: false,
      copyText: false,
      reason: 'auto',
    }

    expect(shouldHideOverlayBeforeOcr(backgroundRequest)).toBe(true)
  })

  it('hides the overlay before presenting cached OCR results to the user', () => {
    const manualRequest: OcrOverlayRequest = {
      openPanel: true,
      copyText: false,
      reason: 'manual',
    }

    expect(shouldHideOverlayBeforeCachedOcrResult(manualRequest)).toBe(true)
  })

  it('delegates user-facing OCR to the backend after the overlay is hidden', () => {
    const manualRequest: OcrOverlayRequest = {
      openPanel: true,
      copyText: true,
      reason: 'manual',
    }

    expect(shouldRunOcrInBackendAfterOverlayHidden(manualRequest)).toBe(true)
  })

  it('uses only the backend-safe OCR command from the overlay window', () => {
    const manualRequest: OcrOverlayRequest = {
      openPanel: true,
      copyText: true,
      reason: 'manual',
    }
    const backgroundRequest: OcrOverlayRequest = {
      openPanel: false,
      copyText: false,
      reason: 'auto',
    }

    expect(overlayOcrCommandName(manualRequest)).toBe('safe_ocr_after_overlay_hidden')
    expect(overlayOcrCommandName(backgroundRequest)).toBe('safe_ocr_after_overlay_hidden')
  })

  it('tears down frontend overlay state before cached OCR backend presentation', () => {
    const cachedRequest: OcrOverlayRequest = {
      openPanel: true,
      copyText: true,
      reason: 'manual',
    }

    expect(shouldTeardownOverlayBeforeBackendOcr(cachedRequest)).toBe(true)
  })

  it('deactivates the overlay session as soon as OCR teardown starts', () => {
    expect(shouldDeactivateOverlaySessionForOcrTeardown()).toBe(true)
  })

  it('defers OCR while region capture is still in progress even with an old capture result', () => {
    expect(shouldDeferOcrUntilCaptureComplete({
      captureInProgress: true,
      pendingOcrAfterCapture: false,
      hasCaptureResult: true,
    })).toBe(true)
  })

  it('allows OCR after capture is complete and a capture result exists', () => {
    expect(shouldDeferOcrUntilCaptureComplete({
      captureInProgress: false,
      pendingOcrAfterCapture: false,
      hasCaptureResult: true,
    })).toBe(false)
  })

  it('does not schedule queued OCR after the overlay session has been closed', () => {
    expect(shouldScheduleQueuedOcrAfterCapture({
      overlaySessionActive: false,
      hasCaptureResult: true,
      hasQueuedRequest: true,
    })).toBe(false)
  })

  it('schedules queued OCR only for an active session with a capture result', () => {
    expect(shouldScheduleQueuedOcrAfterCapture({
      overlaySessionActive: true,
      hasCaptureResult: true,
      hasQueuedRequest: true,
    })).toBe(true)

    expect(shouldScheduleQueuedOcrAfterCapture({
      overlaySessionActive: true,
      hasCaptureResult: false,
      hasQueuedRequest: true,
    })).toBe(false)
  })

  it('waits for transparent overlay frames before backend teardown', async () => {
    let frameCount = 0
    const delays: number[] = []

    await waitForOverlayVisualTeardown(
      async () => {
        frameCount += 1
      },
      async (ms) => {
        delays.push(ms)
      },
    )

    expect(frameCount).toBe(2)
    expect(delays).toEqual([50])
  })

  it('uses timeout fallback when animation frames are suspended', async () => {
    vi.useFakeTimers()
    const requestAnimationFrame = vi.fn(() => 1)
    vi.stubGlobal('requestAnimationFrame', requestAnimationFrame)

    const wait = waitForOverlayVisualTeardown()

    await vi.advanceTimersByTimeAsync(50)
    await vi.advanceTimersByTimeAsync(50)
    await vi.advanceTimersByTimeAsync(50)
    await wait

    expect(requestAnimationFrame).toHaveBeenCalledTimes(2)
  })

  it('destroys the current overlay shell after backend teardown fails post-visual-clear', () => {
    expect(shouldDestroyCurrentOverlayAfterTeardownFailure({
      overlayVisuallyTornDown: true,
      backendTeardownFailed: true,
    })).toBe(true)
  })

  it('does not restore overlay focus while OCR is tearing the overlay down', () => {
    expect(shouldRestoreOverlayFocus({
      overlaySessionActive: true,
      ocrInProgress: true,
      pendingOcrAfterCapture: false,
      isRecordingMode: false,
      hasSelection: true,
      isSelecting: false,
    })).toBe(false)
  })

  it('does not restore overlay focus after the overlay session has been deactivated', () => {
    expect(shouldRestoreOverlayFocus({
      overlaySessionActive: false,
      ocrInProgress: false,
      pendingOcrAfterCapture: false,
      isRecordingMode: false,
      hasSelection: true,
      isSelecting: false,
    })).toBe(false)
  })

  it('does not restore overlay focus while OCR is queued after capture', () => {
    expect(shouldRestoreOverlayFocus({
      overlaySessionActive: true,
      ocrInProgress: false,
      pendingOcrAfterCapture: true,
      isRecordingMode: false,
      hasSelection: true,
      isSelecting: false,
    })).toBe(false)
  })

  it('restores overlay focus only during an active non-OCR screenshot session', () => {
    expect(shouldRestoreOverlayFocus({
      overlaySessionActive: true,
      ocrInProgress: false,
      pendingOcrAfterCapture: false,
      isRecordingMode: false,
      hasSelection: true,
      isSelecting: false,
    })).toBe(true)
  })

  it('does not restore overlay focus after capture when OCR is queued', () => {
    expect(shouldRestoreOverlayFocusAfterCapture({
      overlaySessionActive: true,
      pendingOcrAfterCapture: true,
      triggerOcr: false,
    })).toBe(false)
  })

  it('does not restore overlay focus after capture when capture should trigger OCR', () => {
    expect(shouldRestoreOverlayFocusAfterCapture({
      overlaySessionActive: true,
      pendingOcrAfterCapture: false,
      triggerOcr: true,
    })).toBe(false)
  })

  it('restores overlay focus after capture only when no OCR is pending', () => {
    expect(shouldRestoreOverlayFocusAfterCapture({
      overlaySessionActive: true,
      pendingOcrAfterCapture: false,
      triggerOcr: false,
    })).toBe(true)
  })

  it('extracts the monitor id from a screenshot overlay window label', () => {
    expect(overlayMonitorIdFromLabel('overlay-0')).toBe(0)
    expect(overlayMonitorIdFromLabel('overlay-12')).toBe(12)
    expect(overlayMonitorIdFromLabel('ocr-result')).toBeNull()
    expect(overlayMonitorIdFromLabel('overlay-preview')).toBeNull()
  })
})
