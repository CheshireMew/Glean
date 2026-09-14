# Glean 前端

这个目录包含公开内容站和管理后台，使用 React、Vite、Ant Design 与 Axios。公开站位于 `/`，登录页位于 `/login`，后台位于 `/admin`。API 地址由 `.env.development` 或 `.env.production` 中的 `VITE_API_BASE_URL` 决定。

要求 Node.js 22。安装与启动：

```powershell
npm ci
npm run dev
```

提交前执行：

```powershell
npm run lint
npm test
node --input-type=module -e "import { build } from 'vite'; await build({ build: { write: false } });"
```

测试使用 Vitest、jsdom 与 Testing Library。内存构建不会写入 `dist`；只有明确准备部署产物时才运行 `npm run build`。
