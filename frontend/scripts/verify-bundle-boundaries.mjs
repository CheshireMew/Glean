import { gzipSync } from 'node:zlib';
import { build } from 'vite';

const result = await build({
  mode: 'production',
  logLevel: 'silent',
  build: { write: false },
});
const outputs = (Array.isArray(result) ? result : [result]).flatMap((entry) => entry.output || []);
const chunks = new Map(outputs.filter((entry) => entry.type === 'chunk').map((chunk) => [chunk.fileName, chunk]));
function findEntry(suffix) {
  const entry = [...chunks.values()].find((chunk) => (
    chunk.facadeModuleId?.replaceAll('\\', '/').endsWith(suffix)
    || Object.keys(chunk.modules || {}).some((moduleId) => moduleId.replaceAll('\\', '/').endsWith(suffix))
  ));
  if (!entry) throw new Error(`Unable to locate route chunk ${suffix}`);
  return entry;
}

function visitClosure(entry) {
  const visited = new Set();
  const visit = (fileName) => {
    if (visited.has(fileName)) return;
    visited.add(fileName);
    for (const imported of chunks.get(fileName)?.imports || []) visit(imported);
  };
  visit(entry.fileName);
  return [...visited].map((fileName) => chunks.get(fileName)).filter(Boolean);
}

function assertAcyclic() {
  const visiting = new Set();
  const visited = new Set();
  const visit = (fileName, path = []) => {
    if (visiting.has(fileName)) throw new Error(`Bundle chunk cycle: ${[...path, fileName].join(' -> ')}`);
    if (visited.has(fileName)) return;
    visiting.add(fileName);
    for (const imported of chunks.get(fileName)?.imports || []) visit(imported, [...path, fileName]);
    visiting.delete(fileName);
    visited.add(fileName);
  };
  for (const fileName of chunks.keys()) visit(fileName);
}

assertAcyclic();
const routes = [
  { name: 'public', suffix: '/src/pages/NewsFeed.jsx', budgetKiB: 220, forbidAdminUi: true },
  { name: 'login', suffix: '/src/pages/Login.jsx', budgetKiB: 160, forbidAdminUi: true },
  { name: 'admin', suffix: '/src/pages/Dashboard.jsx', budgetKiB: 450, forbidAdminUi: false },
];
for (const route of routes) {
  const closure = visitClosure(findEntry(route.suffix));
  if (route.forbidAdminUi) {
    const forbiddenModules = closure.flatMap((chunk) => Object.keys(chunk.modules || {})).filter((moduleId) => {
      const normalized = moduleId.replaceAll('\\', '/');
      return normalized.includes('/node_modules/antd/') || normalized.includes('/node_modules/@ant-design/icons/');
    });
    if (forbiddenModules.length) {
      throw new Error(`${route.name} route imports admin UI modules:\n${forbiddenModules.join('\n')}`);
    }
  }
  const gzipBytes = closure.reduce((total, chunk) => total + gzipSync(chunk.code).byteLength, 0);
  const budgetBytes = route.budgetKiB * 1024;
  if (gzipBytes > budgetBytes) {
    throw new Error(`${route.name} route JS closure is ${gzipBytes} bytes gzip; budget is ${budgetBytes}`);
  }
  console.log(`${route.name} route boundary verified: ${closure.length} chunks, ${gzipBytes} bytes gzip`);
}
