# Glean 服务器部署

本机验收平台是 Windows。以下 Ubuntu/Debian 配置供服务器部署使用；仓库已提供生产配置，但没有在你的实际服务器上完成运行验收。

## 部署前提

浏览器与 API 使用同一个 HTTPS 域名，例如 `https://new.blacknico.com`。只向公网开放 80/443，API 的 8000 端口绑定 `127.0.0.1`。API 与 worker 都使用普通账号 `glean`，不能用 root 运行服务。不要将 Windows 启动器或 Vite 开发服务用于公网部署。

前端使用 Node.js 22，后端使用 Python 3.10 以上版本。依赖分别按 `frontend/package-lock.json` 和 `requirements.lock` 安装。发布时需要构建当前版本的前端，不能沿用旧 `dist`。

## 准备账号、代码和目录

服务器上安装 Python、venv、Nginx、Git 和 Certbot。示例目录为 `/var/www/glean`；将代码克隆到这里，代码和虚拟环境由部署账号维护，服务账号只读。私有仓库使用 SSH 或凭据管理器，不把访问 Token 写入 URL。

```bash
sudo useradd --system --user-group --home-dir /var/lib/glean --shell /usr/sbin/nologin glean
sudo install -d -o glean -g glean -m 700 /var/lib/glean
sudo install -d -o root -g glean -m 750 /etc/glean
cd /var/www/glean
python3 -m venv venv
venv/bin/pip install -r requirements.lock
sudo venv/bin/playwright install-deps chromium
sudo install -d -o glean -g glean -m 700 /var/www/glean/data
sudo -u glean env PLAYWRIGHT_BROWSERS_PATH=/var/lib/glean/browsers venv/bin/playwright install chromium
sudo install -o root -g glean -m 640 scripts/server/production.env.example /etc/glean/production.env
```

已有 `data/` 时先保留备份，再把该目录及备份的所有者交给 `glean`。代码、虚拟环境和静态前端不能由服务账号写入。不要上传本机环境文件、数据库或日志到前端目录。

## 初始化生产配置

编辑 `/etc/glean/production.env`，填写实际域名及同源的 `ALLOWED_ORIGINS`。管理员账号、初始化密码和签名密钥可以保持空值：交互设置账号，签名密钥由应用生成并保存在受保护的数据库中。

环境文件使用不含空格的 `KEY=value` 形式，便于 systemd 和下面的初始化命令共同读取。以服务账号加载同一份配置并初始化：

```bash
sudo -u glean bash -c 'set -a; source /etc/glean/production.env; set +a; cd /var/www/glean; venv/bin/python -m backend.security_setup; venv/bin/python -m backend.reset_admin --username your-admin-name'
```

`reset_admin` 会交互询问密码，不把密码放进命令行。使用全新且至少 12 位的密码。应用拒绝已知进入仓库历史的密码和签名密钥；Git 历史仍保留原提交，不可再使用其中的值。源码仓库、环境文件和备份不能由 Nginx 提供下载。

生产环境数据库、备份和环境文件需要限制为服务账号及必要管理员可读。Linux 目录为 0700，敏感文件为 0600；环境文件由 root 管理时可用 root:glean、0640。Windows 本机已由 `backend.security_setup` 收紧 ACL。

## 构建前端

修改 `frontend/.env.production` 的 API 地址为实际 HTTPS 域名，前端与 API 必须同源。使用锁定依赖执行：

```bash
cd /var/www/glean/frontend
npm ci
npm run lint
npm test
npm run build:release
npm run verify:release
```

升级时使用全新的构建目录，保留旧目录供回退，避免新旧资源混合。普通开发检查使用 `npm run build`，不会生成安装包。

## 启动 API 与 worker

直接安装仓库中完整的服务配置，避免遗漏环境文件、沙箱目录或写权限限制：

```bash
cd /var/www/glean
sudo install -m 644 scripts/server/glean-backend.service /etc/systemd/system/glean-backend.service
sudo install -m 644 scripts/server/glean-worker.service /etc/systemd/system/glean-worker.service
sudo systemctl daemon-reload
sudo systemctl enable --now glean-backend glean-worker
sudo systemctl status glean-backend glean-worker
curl -f http://127.0.0.1:8000/health/live
curl -f http://127.0.0.1:8000/health/ready
curl -f http://127.0.0.1:8000/health/pipeline
```

API 不执行定时任务；worker 必须单独运行。worker 使用数据库租约避免重复实例。生产浏览器启用 Chromium 沙箱，必须验证目标服务器支持沙箱；不能为解决启动错误而关闭沙箱或改用 root。

首次迁移旧数据库时，应用会在数据库同级 `backups/` 保存快照。快照包含敏感配置，权限与数据库一致。部署前另做服务器备份，并确认剩余磁盘空间。

## HTTPS 和 Nginx

使用 `scripts/server/nginx.conf` 的完整配置。它包含 HTTPS、Cookie 同源要求、登录与 API 请求限速、请求体限制、页面安全响应头、CSP 和静态资源缓存。用 `$remote_addr` 覆盖访客传入的转发头，API 只信任 `127.0.0.1` 的 Nginx。

首次签发证书时，先启用配置中的 80 端口部分，准备 `/var/www/letsencrypt/.well-known/acme-challenge/`，使用 Certbot webroot 模式签发证书，再启用 443 部分。不要在证书文件尚不存在时直接启用 TLS 配置。

```bash
sudo install -d -m 755 /var/www/letsencrypt/.well-known/acme-challenge
sudo certbot certonly --webroot -w /var/www/letsencrypt -d new.blacknico.com
sudo install -m 644 /var/www/glean/scripts/server/nginx.conf /etc/nginx/sites-available/new.blacknico.com
sudo ln -s /etc/nginx/sites-available/new.blacknico.com /etc/nginx/sites-enabled/new.blacknico.com
sudo nginx -t
sudo systemctl reload nginx
```

将示例域名和证书路径替换为实际值，配置放在 Nginx 的 `http` 上下文。如果使用 CDN，需要配置明确的 CDN 可信地址，不能把 API 的代理信任范围改成 `*`。防火墙不开放 8000、5173 和数据库端口；健康检查只在服务器本机访问。

## 采集、发布和费用

公开页面只读取更新状态。自动更新由 worker 按管理员配置的频率执行，需要开启自动化总开关；来源设为“仅手动”时不参与定时采集。Acquired 已从现行来源中移除。

内部投递不会自动公开内容。网站展示要求有公开且启用频道的正式发布记录；关闭公开权限后，列表、搜索、RSS 和事件详情同步隐藏。实体的内部 metadata 与别名不会通过公开接口返回。

生产采集只允许访问公网，重定向逐次检查，目标 IP 固定后才发请求，阻止本机、内网、云实例元数据地址和 DNS 重新解析绕过。外部响应限制为 4 MiB，并检查解压后的大小。公网模型、Webhook 等凭据请求必须使用 HTTPS，SMTP 必须使用证书校验的 TLS/SSL。确需连接本机模型、SMTP 或 Webhook 时，用 `GLEAN_PRIVATE_ENDPOINT_HOSTS` 逐个允许精确主机名；采集来源不能使用这些例外。服务器防火墙也应限制服务访问其他内网资源。

翻译、审核、补写、连接测试、重试和备用模型共用每日额度。`GLEAN_AI_DAILY_MAX_CALLS` 默认 1000，`GLEAN_AI_DAILY_MAX_COST` 默认 5；金额单位必须与所有端点每百万 Token 的价格一致。远程端点需填写输入和输出价格，翻译价格通过 `GLEAN_TRANSLATION_INPUT_PRICE`、`GLEAN_TRANSLATION_OUTPUT_PRICE` 配置。未填写价格时拒绝生产调用。发送前预留预算，结果不明时保留预留费用，额度按 UTC 日期重置。实际服务账单仍以供应商为准。

## 上线验证

在目标预发布服务器验证 HTTPS、普通账号的文件权限、Chromium 沙箱、worker 心跳和证书自动续期。确认首页、登录、页面刷新、退出登录及后台写操作正常；匿名请求不能触发采集或访问后台，私有内容不能从列表、搜索、RSS、事件或实体详情读到。

核对页面的版本与本机健康检查版本一致，并确认达到采集或 AI 额度限制时行为符合设置。本项目的 Windows 自动测试不能代替这些目标服务器检查。
