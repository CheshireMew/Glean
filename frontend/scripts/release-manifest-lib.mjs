import { createHash } from 'node:crypto'
import { readFile, readdir } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
export const projectRoot = path.resolve(frontendRoot, '..')
export const distRoot = path.resolve(frontendRoot, 'dist')
export const manifestPath = path.resolve(distRoot, 'release-manifest.json')

export async function sourceVersion() {
  return (await readFile(path.resolve(projectRoot, 'VERSION'), 'utf8')).trim()
}

export async function listFiles(root, relative = '') {
  const directory = path.resolve(root, relative)
  const entries = await readdir(directory, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const child = path.posix.join(relative.split(path.sep).join('/'), entry.name)
    if (entry.isDirectory()) files.push(...await listFiles(root, child))
    else files.push(child)
  }
  return files.sort()
}

export async function sha256(filePath) {
  return createHash('sha256').update(await readFile(filePath)).digest('hex')
}

export async function releaseFiles() {
  const files = (await listFiles(distRoot)).filter((file) => file !== 'release-manifest.json')
  return Promise.all(files.map(async (file) => ({
    path: file,
    sha256: await sha256(path.resolve(distRoot, file)),
  })))
}
