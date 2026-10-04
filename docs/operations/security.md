# 安全修复与验证

更新：2026-10-04。当前工作区已经修复此次检查发现的代码及配置问题，完成 Windows 验证。可按专用普通账号、同源 HTTPS、静态前端和独立 worker 的方式准备单机部署。尚未连接实际服务器，目标服务器的 TLS、防火墙、Linux 权限和 Chromium 沙箱仍需验收，具体步骤见 [部署文档](deployment.md)。

## 修复内容

| 原问题 | 当前行为 |
| --- | --- |
| 已发送内容绕过频道公开开关 | 内容列表、日报、搜索、RSS、事件及实体关联事件都要求公开且启用频道的正式发布记录；内部投递不自动公开 |
| 公开实体返回内部扩展字段 | 使用固定公开字段，隐藏 metadata 和别名；没有公开事件的实体返回 404 |
| 登录表单解析缺少边界 | 升级 FastAPI/Starlette，解析前限制请求体；限制字段数量、重复字段及账号密码长度；限制请求频率、并发与接收时间 |
| 匿名页面可以创建采集任务 | 状态接口只读；刷新写接口需要管理员会话；自动采集改由 worker 按总开关及来源频率执行 |
| 浏览器保存可读取的登录 Token | 浏览器使用 HttpOnly Cookie，生产使用 Secure、SameSite=Strict、主机限定 Cookie；写操作校验 CSRF，刷新页面重新验证服务器会话；CLI 的 Bearer 接口继续可用 |
| 外部请求没有内网和响应大小限制 | 生产 HTTP 请求验证并固定解析后的公网 IP，重定向逐次验证；限制原始及解压后的响应大小为 4 MiB；模型和 Webhook 公网凭据要求 HTTPS |
| 邮件凭据可能明文发送 | 生产 SMTP 要求 TLS/SSL、校验证书；连接使用已验证 IP，证书仍校验原主机名 |
| 模型调用缺少总费用边界 | 翻译、审核、补写、连接测试、重试和备用端点共用数据库中的每日调用及费用预算；发送前预留，结果不明时保留预留费用 |
| 数据库、环境文件及备份权限过宽 | 已收紧本机 ACL；提供权限修复入口，生产初始化保护数据及备份；已知历史密码和签名密钥被拒绝使用 |
| 服务器默认权限和代理信任过大 | 提供普通服务账号的 systemd 配置，Chromium 沙箱开启，API 仅监听本机，只信任本机代理；Nginx 覆盖访客转发头并配置限速、TLS、CSP 和其他响应头 |
| 已知依赖公告 | 更新 Python 与前端锁定依赖；复查没有命中已知漏洞；Tailwind 升级后验证了页面样式和浏览器运行 |
| Windows 关闭启动窗口后残留服务 | 启动器使用 Windows Job 管理本次服务及子进程，正常停止或启动器退出都会回收；不会结束其他程序 |

Acquired 已按要求从现行采集和展示来源中移除，旧配置及历史内容保留。出现外站 404 时，代表订阅地址不可用，不代表本地端口冲突。

## 验证结果

在隔离数据库中执行测试，没有发送真实投递消息或调用付费模型。完整后台测试为 **235 passed、20 subtests passed**；请求边界的额外检查为 **11 passed**，包含无 Content-Length 的超限表单、全局限速、压缩响应大小及重定向到云实例元数据地址的拒绝验证。前端 **31 个测试文件、58 项测试通过**，ESLint、Ruff、构建及前台/登录/后台的构建边界检查通过，`pip check` 通过。

浏览器使用 Windows Edge/Chromium 沙箱、当前静态构建、隔离的真实 API 和生产 CSP 验证。登录、页面刷新恢复会话、带 CSRF 的退出、退出后后台拒绝访问、公开状态只读、Acquired 隐藏及页面样式均通过，没有 CSP 或页面脚本错误。这是应用验证，不代表实际 Nginx 已在服务器运行。

依赖检查结果为 npm 官方 registry audit **0**，Python 锁定的 **38** 个包在 OSV 检查中 **0** 命中。结果仅代表检查时数据库收录的已知公告，不是不存在所有漏洞的证明。Starlette 的测试客户端有迁移至 httpx2 的弃用提示，现有测试全部通过。

本机证据保存在 Git 忽略目录：

- [完整后台测试](../../data/logs/security-backend-tests-verified.txt)、[请求边界测试](../../data/logs/security-request-tests-final.txt)
- [前端测试](../../data/logs/security-frontend-tests.txt)、[前端检查](../../data/logs/security-frontend-lint.txt)、[构建边界](../../data/logs/security-frontend-architecture.txt)
- [npm 复查](../../data/logs/security-npm-after-fixes.json)、[Python OSV 复查](../../data/logs/security-python-after-fixes.json)
- [浏览器结果](../../archive/local/security/2026-10-04/browser-fix-results.json)、[浏览器验证脚本](../../archive/local/security/2026-10-04/browser_fix_checks.py)
- [修复前审查记录](../../archive/local/security/2026-10-04/security-review.md)

## 部署时仍需落实

生产模板位于 `scripts/server/`。使用目标域名的有效 HTTPS 证书，API 和前端保持同源；服务使用普通账号，公开端口仅为 80/443。验证浏览器沙箱、worker 心跳、敏感文件权限、备份和证书续期。自动采集需要管理员开启总开关并设置来源频率。

生产远程模型需要填写输入及输出价格，翻译还需填写对应环境变量，价格单位统一后设置每日费用上限。费用按配置价格和供应商报告的用量计算，实际账单以供应商为准。需要连接本机模型、SMTP 或 Webhook 时，逐个允许精确主机名；采集来源不能使用内网例外。

数据库中的集成凭据仍需要服务账号读取，未改为统一静态加密；其他普通账号已没有默认读取权限，管理员及服务账号仍应妥善管理。Git 历史保留原提交，已知历史密码和签名密钥已经禁用；服务器初始化使用新凭据。本次没有重写 Git 历史，没有打包或部署服务器。
