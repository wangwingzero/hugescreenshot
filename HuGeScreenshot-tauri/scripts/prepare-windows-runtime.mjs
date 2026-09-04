import { createWriteStream, existsSync, mkdirSync, renameSync, statSync, unlinkSync, copyFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import https from 'node:https'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(scriptDir, '..')
const targetPath = resolve(projectRoot, 'src-tauri', 'resources', 'vc_redist.x64.exe')
const tempPath = `${targetPath}.tmp`
const sourceUrl = process.env.VC_REDIST_X64_URL ?? 'https://aka.ms/vc14/vc_redist.x64.exe'
const localSource = process.env.VC_REDIST_X64_PATH
const minimumBytes = 5 * 1024 * 1024

function assertUsableFile(path) {
  const { size } = statSync(path)
  if (size < minimumBytes) {
    throw new Error(`VC++ runtime installer is unexpectedly small: ${path} (${size} bytes)`)
  }
}

function ensureTargetDir() {
  mkdirSync(dirname(targetPath), { recursive: true })
}

function download(url, destination, redirectCount = 0) {
  if (redirectCount > 5) {
    return Promise.reject(new Error(`Too many redirects while downloading ${url}`))
  }

  return new Promise((resolvePromise, reject) => {
    const request = https.get(url, (response) => {
      const status = response.statusCode ?? 0
      const location = response.headers.location

      if ([301, 302, 303, 307, 308].includes(status) && location) {
        response.resume()
        const redirected = new URL(location, url).toString()
        download(redirected, destination, redirectCount + 1).then(resolvePromise, reject)
        return
      }

      if (status < 200 || status >= 300) {
        response.resume()
        reject(new Error(`Download failed with HTTP ${status}: ${url}`))
        return
      }

      const file = createWriteStream(destination)
      response.pipe(file)
      file.on('finish', () => {
        file.close(resolvePromise)
      })
      file.on('error', reject)
    })

    request.on('error', reject)
  })
}

async function main() {
  ensureTargetDir()

  if (existsSync(targetPath)) {
    assertUsableFile(targetPath)
    console.log(`VC++ runtime installer already prepared: ${targetPath}`)
    return
  }

  if (localSource) {
    const resolvedSource = resolve(localSource)
    assertUsableFile(resolvedSource)
    copyFileSync(resolvedSource, targetPath)
    console.log(`Copied VC++ runtime installer from ${resolvedSource}`)
    return
  }

  try {
    if (existsSync(tempPath)) unlinkSync(tempPath)
    console.log(`Downloading VC++ runtime installer from ${sourceUrl}`)
    await download(sourceUrl, tempPath)
    assertUsableFile(tempPath)
    renameSync(tempPath, targetPath)
    console.log(`Prepared VC++ runtime installer: ${targetPath}`)
  } catch (error) {
    if (existsSync(tempPath)) unlinkSync(tempPath)
    throw new Error(
      `Unable to prepare vc_redist.x64.exe. Set VC_REDIST_X64_PATH to a local installer or retry with network access. ${error instanceof Error ? error.message : String(error)}`,
    )
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error))
  process.exit(1)
})
