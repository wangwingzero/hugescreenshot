import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

describe('Tauri CSP config', () => {
  it('allows screenshot previews from Tauri asset URLs and blob fallbacks', () => {
    const configPath = resolve(__dirname, '../../src-tauri/tauri.conf.json')
    const config = JSON.parse(readFileSync(configPath, 'utf8')) as {
      app?: {
        security?: {
          csp?: string
        }
      }
    }
    const csp = config.app?.security?.csp ?? ''

    expect(csp).toContain('img-src')
    expect(csp).toContain('http://asset.localhost')
    expect(csp).toContain('https://asset.localhost')
    expect(csp).toContain('blob:')
  })
})
