$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $PSScriptRoot 'frontend')

$port = 5173
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
    $owners = ($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ', '
    throw "端口 $port 已被占用（PID: $owners）。请先停止对应服务，再启动前端。"
}
if (-not (Test-Path -LiteralPath 'node_modules\vite\bin\vite.js')) {
    throw '前端依赖未安装，请在 frontend 目录执行 npm ci。'
}

$Host.UI.RawUI.WindowTitle = 'Glean Frontend'
Write-Host 'Starting Glean frontend at http://localhost:5173/ ...' -ForegroundColor Cyan
& npm.cmd run dev -- --host 127.0.0.1 --port $port --strictPort
