import { describe, expect, it } from 'vitest'

import { imageMimeTypeForPath, replaceTempImageExtension } from '../tempImagePath'

describe('temp image path helpers', () => {
  it('builds derived OCR paths for BMP captures without overwriting the source file', () => {
    expect(replaceTempImageExtension('C:\\Temp\\hugescreenshot\\capture.bmp', '_composite_ocr.png'))
      .toBe('C:\\Temp\\hugescreenshot\\capture_composite_ocr.png')
  })

  it('builds derived paths for extensionless temp files', () => {
    expect(replaceTempImageExtension('C:\\Temp\\hugescreenshot\\capture', '_save.png'))
      .toBe('C:\\Temp\\hugescreenshot\\capture_save.png')
  })

  it('detects BMP image MIME type from Windows paths', () => {
    expect(imageMimeTypeForPath('C:\\Temp\\hugescreenshot\\capture.bmp')).toBe('image/bmp')
  })
})
