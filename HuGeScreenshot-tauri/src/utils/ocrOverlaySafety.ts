export interface OcrOverlayRequest {
  openPanel: boolean
  copyText: boolean
  reason: 'auto' | 'manual'
}

export type OverlayOcrCommandName = 'safe_ocr_after_overlay_hidden'

export interface OverlayFocusRestoreState {
  overlaySessionActive: boolean
  ocrInProgress: boolean
  pendingOcrAfterCapture: boolean
  isRecordingMode: boolean
  hasSelection: boolean
  isSelecting: boolean
}

export interface OverlayPostCaptureState {
  overlaySessionActive: boolean
  pendingOcrAfterCapture: boolean
  triggerOcr: boolean
}

export interface OverlayTeardownFailureState {
  overlayVisuallyTornDown: boolean
  backendTeardownFailed: boolean
}

export interface OcrStartGateState {
  captureInProgress: boolean
  pendingOcrAfterCapture: boolean
  hasCaptureResult: boolean
}

export interface QueuedOcrAfterCaptureState {
  overlaySessionActive: boolean
  hasCaptureResult: boolean
  hasQueuedRequest: boolean
}

export type OverlayFrameWaiter = () => Promise<void>
export type OverlayDelay = (ms: number) => Promise<void>

const OVERLAY_TEARDOWN_RENDER_FRAMES = 2
const OVERLAY_TEARDOWN_SETTLE_MS = 50

export function shouldAutoOcrOnSelection(): boolean {
  return false
}

export function shouldHideOverlayBeforeOcr(request: OcrOverlayRequest): boolean {
  void request
  return true
}

export function shouldHideOverlayBeforeCachedOcrResult(request: OcrOverlayRequest): boolean {
  return shouldHideOverlayBeforeOcr(request)
}

export function shouldRunOcrInBackendAfterOverlayHidden(request: OcrOverlayRequest): boolean {
  return shouldHideOverlayBeforeOcr(request)
}

export function overlayOcrCommandName(request: OcrOverlayRequest): OverlayOcrCommandName {
  void request
  return 'safe_ocr_after_overlay_hidden'
}

export function shouldTeardownOverlayBeforeBackendOcr(request: OcrOverlayRequest): boolean {
  return shouldRunOcrInBackendAfterOverlayHidden(request)
}

export function shouldDeactivateOverlaySessionForOcrTeardown(): boolean {
  return true
}

export function shouldDeferOcrUntilCaptureComplete(state: OcrStartGateState): boolean {
  return state.captureInProgress || (state.pendingOcrAfterCapture && !state.hasCaptureResult)
}

export function shouldScheduleQueuedOcrAfterCapture(state: QueuedOcrAfterCaptureState): boolean {
  return state.overlaySessionActive && state.hasCaptureResult && state.hasQueuedRequest
}

export function shouldDestroyCurrentOverlayAfterTeardownFailure(
  state: OverlayTeardownFailureState,
): boolean {
  return state.overlayVisuallyTornDown && state.backendTeardownFailed
}

function waitForNextAnimationFrame(): Promise<void> {
  return new Promise((resolve) => {
    let resolved = false
    const timeoutId = window.setTimeout(() => {
      if (resolved) return
      resolved = true
      resolve()
    }, OVERLAY_TEARDOWN_SETTLE_MS)

    requestAnimationFrame(() => {
      if (resolved) return
      resolved = true
      window.clearTimeout(timeoutId)
      resolve()
    })
  })
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

export async function waitForOverlayVisualTeardown(
  waitForNextFrame: OverlayFrameWaiter = waitForNextAnimationFrame,
  waitForDelay: OverlayDelay = delay,
): Promise<void> {
  for (let i = 0; i < OVERLAY_TEARDOWN_RENDER_FRAMES; i += 1) {
    await waitForNextFrame()
  }

  await waitForDelay(OVERLAY_TEARDOWN_SETTLE_MS)
}

export function shouldRestoreOverlayFocus(state: OverlayFocusRestoreState): boolean {
  return (
    state.overlaySessionActive &&
    !state.ocrInProgress &&
    !state.pendingOcrAfterCapture &&
    !state.isRecordingMode &&
    (state.hasSelection || state.isSelecting)
  )
}

export function shouldRestoreOverlayFocusAfterCapture(state: OverlayPostCaptureState): boolean {
  return state.overlaySessionActive && !state.pendingOcrAfterCapture && !state.triggerOcr
}

export function overlayMonitorIdFromLabel(label: string): number | null {
  const match = /^overlay-(\d+)$/.exec(label)
  if (!match) return null

  const monitorId = Number.parseInt(match[1], 10)
  return Number.isSafeInteger(monitorId) ? monitorId : null
}
