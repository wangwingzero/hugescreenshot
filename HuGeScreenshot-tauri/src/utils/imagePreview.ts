export function getImageMimeType(path: string): string {
  const lower = path.toLowerCase()
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg'
  if (lower.endsWith('.webp')) return 'image/webp'
  if (lower.endsWith('.gif')) return 'image/gif'
  if (lower.endsWith('.bmp')) return 'image/bmp'
  return 'image/png'
}

export function createImageObjectUrl(bytes: Uint8Array, path: string): string {
  const blob = new Blob([bytes], { type: getImageMimeType(path) })
  return URL.createObjectURL(blob)
}
