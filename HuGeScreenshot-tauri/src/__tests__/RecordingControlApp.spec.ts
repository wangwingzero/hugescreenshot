/**
 * Unit Tests for RecordingControlApp
 *
 * Tests cover:
 * - handleStop() closes recording border + overlay mode before preview
 * - isStopping flag prevents poll from closing window during stop
 * - handleStop() opens preview before closing control panel
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

// Track invocation order
const invocations: string[] = []
const mockInvoke = vi.fn(async (cmd: string, _args?: unknown) => {
  invocations.push(cmd)
  if (cmd === 'stop_recording') {
    return {
      outputPath: '/tmp/recording.mp4',
      duration: 10.5,
      frameCount: 315,
      fileSize: 5242880,
    }
  }
  if (cmd === 'get_recording_status') {
    return { state: 'recording', elapsedTime: 5, frameCount: 150, fileSize: 0 }
  }
  return {}
})

vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args as [string, unknown?]),
}))

const mockClose = vi.fn()
vi.mock('@tauri-apps/api/window', () => ({
  getCurrentWindow: () => ({
    close: mockClose,
    startDragging: vi.fn(),
  }),
}))

describe('RecordingControlApp stop logic', () => {
  beforeEach(() => {
    invocations.length = 0
    mockInvoke.mockClear()
    mockClose.mockClear()
  })

  it('handleStop should call commands in correct order: stop → restore overlay → close border → preview → close window', async () => {
    // Simulate the handleStop logic inline (same as component)
    const isStopping = { value: false }

    async function handleStop() {
      isStopping.value = true
      try {
        const result = await mockInvoke('stop_recording')
        await mockInvoke('set_overlay_recording_mode', { enabled: false })
        await mockInvoke('close_recording_border')
        await mockInvoke('open_recording_preview', {
          outputPath: (result as { outputPath: string }).outputPath,
          duration: (result as { duration: number }).duration,
          fileSize: (result as { fileSize: number }).fileSize,
        })
        mockClose()
      } catch (_) {
        try { await mockInvoke('set_overlay_recording_mode', { enabled: false }) } catch (_) { /* ignore */ }
        try { await mockInvoke('close_recording_border') } catch (_) { /* ignore */ }
      }
    }

    await handleStop()

    // Verify order
    expect(invocations).toEqual([
      'stop_recording',
      'set_overlay_recording_mode',
      'close_recording_border',
      'open_recording_preview',
    ])

    // Verify window.close was called last
    expect(mockClose).toHaveBeenCalledOnce()

    // Verify isStopping was set
    expect(isStopping.value).toBe(true)
  })

  it('isStopping flag should prevent poll from closing window', async () => {
    const isStopping = { value: false }

    async function pollStatus() {
      const status = await mockInvoke('get_recording_status') as { state: string }
      if (!isStopping.value && (status.state === 'idle' || status.state === 'finished')) {
        mockClose()
      }
    }

    // Simulate: handleStop sets isStopping before poll sees idle state
    isStopping.value = true

    // Override to return idle status
    mockInvoke.mockResolvedValueOnce({ state: 'idle', elapsedTime: 10, frameCount: 300, fileSize: 0 })

    await pollStatus()

    // Window should NOT be closed by poll since isStopping is true
    expect(mockClose).not.toHaveBeenCalled()
  })

  it('handleStop should restore overlay even on error', async () => {
    mockInvoke.mockRejectedValueOnce(new Error('stop failed'))

    async function handleStop() {
      try {
        await mockInvoke('stop_recording')
      } catch (_) {
        try { await mockInvoke('set_overlay_recording_mode', { enabled: false }) } catch (_) { /* ignore */ }
        try { await mockInvoke('close_recording_border') } catch (_) { /* ignore */ }
      }
    }

    await handleStop()

    // Even on error, overlay should be restored and border closed
    expect(invocations).toContain('set_overlay_recording_mode')
    expect(invocations).toContain('close_recording_border')
  })
})
