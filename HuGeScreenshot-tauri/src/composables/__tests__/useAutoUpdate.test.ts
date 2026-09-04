import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAutoUpdate } from '../useAutoUpdate'

const mockCheck = vi.fn()
const mockRelaunch = vi.fn()

vi.mock('@tauri-apps/plugin-updater', () => ({
  check: () => mockCheck(),
}))

vi.mock('@tauri-apps/plugin-process', () => ({
  relaunch: () => mockRelaunch(),
}))

describe('useAutoUpdate', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shares updater state across composable consumers', async () => {
    const first = useAutoUpdate()
    const second = useAutoUpdate()

    mockCheck.mockResolvedValueOnce({
      version: '0.1.13',
      body: 'notes',
    })

    await first.checkForUpdate()

    expect(second.status.value).toBe('available')
    expect(second.updateInfo.value?.version).toBe('0.1.13')
  })

  it('reports up-to-date status when no update is available', async () => {
    const updater = useAutoUpdate()
    mockCheck.mockResolvedValueOnce(null)

    await updater.checkForUpdate()

    expect(updater.status.value).toBe('upToDate')
  })
})
