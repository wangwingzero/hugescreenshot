export function replaceTempImageExtension(path: string, suffix: string): string {
  const lastSlash = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'))
  const lastDot = path.lastIndexOf('.')
  if (lastDot > lastSlash) {
    return `${path.slice(0, lastDot)}${suffix}`
  }
  return `${path}${suffix}`
}

export function imageMimeTypeForPath(path: string): string {
  const extension = path.split(/[\\/]/).pop()?.split('.').pop()?.toLowerCase()
  switch (extension) {
    case 'bmp':
      return 'image/bmp'
    case 'jpg':
    case 'jpeg':
      return 'image/jpeg'
    case 'webp':
      return 'image/webp'
    case 'png':
    default:
      return 'image/png'
  }
}
