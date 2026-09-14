import { readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'

import { distRoot, frontendRoot, manifestPath, releaseFiles, sourceVersion } from './release-manifest-lib.mjs'

const version = await sourceVersion()
const packageMetadata = JSON.parse(await readFile(path.resolve(frontendRoot, 'package.json'), 'utf8'))
if (!version || version === 'unreleased') throw new Error('VERSION 必须是明确的发布版本')
if (packageMetadata.version !== version) throw new Error(`package.json 版本 ${packageMetadata.version} 与 VERSION ${version} 不一致`)

const indexHtml = await readFile(path.resolve(distRoot, 'index.html'), 'utf8')
if (!indexHtml.includes(`name="glean-version" content="${version}"`)) {
  throw new Error('index.html 未嵌入与 VERSION 一致的 glean-version')
}

const manifest = {
  app_version: version,
  generated_at_utc: new Date().toISOString(),
  files: await releaseFiles(),
}
await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
