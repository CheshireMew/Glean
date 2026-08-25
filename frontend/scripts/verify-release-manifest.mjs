import { readFile } from 'node:fs/promises'

import { manifestPath, releaseFiles, sourceVersion } from './release-manifest-lib.mjs'

const manifest = JSON.parse(await readFile(manifestPath, 'utf8'))
const version = await sourceVersion()
if (manifest.app_version !== version) {
  throw new Error(`发布清单版本 ${manifest.app_version} 与源码版本 ${version} 不一致`)
}

const actualFiles = await releaseFiles()
if (JSON.stringify(manifest.files) !== JSON.stringify(actualFiles)) {
  throw new Error('dist 文件集合或哈希与 release-manifest.json 不一致，禁止部署')
}

process.stdout.write(`release ${version} verified: ${actualFiles.length} files\n`)
