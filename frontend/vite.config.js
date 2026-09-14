import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const rootDir = path.dirname(fileURLToPath(import.meta.url))
const appVersion = readFileSync(path.resolve(rootDir, '../VERSION'), 'utf8').trim()

function versionMetaPlugin() {
  return {
    name: 'glean-version-meta',
    transformIndexHtml() {
      return [{
        tag: 'meta',
        attrs: { name: 'glean-version', content: appVersion },
        injectTo: 'head',
      }]
    },
  }
}

function chunkByNodeModulePackage(id) {
  const normalized = id.split('\\').join('/')
  const marker = '/node_modules/'
  const index = normalized.lastIndexOf(marker)
  if (index === -1) {
    return null
  }
  const modulePath = normalized.slice(index + marker.length)
  const segments = modulePath.split('/')
  if (segments[0].startsWith('@')) {
    return `${segments[0].slice(1)}-${segments[1]}`
  }
  return segments[0]
}

export default defineConfig({
  plugins: [react(), versionMetaPlugin()],
  resolve: {
    alias: {
      '@shared-content-contract': path.resolve(rootDir, '../shared/content_contract.json'),
    },
  },
  server: {
    fs: {
      allow: [path.resolve(rootDir, '..')],
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('commonjsHelpers')) {
            return 'react-vendor'
          }
          const pkg = chunkByNodeModulePackage(id)
          if (!pkg) {
            return
          }
          if (['react', 'react-dom', 'react-router', 'react-router-dom', 'scheduler'].includes(pkg)) {
            return 'react-vendor'
          }
          if (['axios', 'dayjs'].includes(pkg)) {
            return 'utility-vendor'
          }
        },
      },
    },
  },
})
