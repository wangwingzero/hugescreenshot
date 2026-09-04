import { describe, expect, it } from 'vitest'
import { getImageMimeType } from '../imagePreview'

describe('imagePreview', () => {
  it('detects common image MIME types from file paths', () => {
    expect(getImageMimeType('C:\\temp\\capture.png')).toBe('image/png')
    expect(getImageMimeType('C:\\temp\\capture.JPG')).toBe('image/jpeg')
    expect(getImageMimeType('C:\\temp\\capture.jpeg')).toBe('image/jpeg')
    expect(getImageMimeType('C:\\temp\\capture.webp')).toBe('image/webp')
    expect(getImageMimeType('C:\\temp\\capture.gif')).toBe('image/gif')
    expect(getImageMimeType('C:\\temp\\capture.bmp')).toBe('image/bmp')
  })

  it('defaults to PNG for extensionless temporary preview paths', () => {
    expect(getImageMimeType('C:\\temp\\hugescreenshot\\crop_123')).toBe('image/png')
  })
})
