[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Wait-GleanService {
    param([string]$Name, [string]$Url)

    Write-Host "等待 $Name 就绪..." -ForegroundColor Cyan
    $deadline = (Get-Date).AddSeconds(60)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    } while ((Get-Date) -lt $deadline)
    throw "$Name 在 60 秒内未就绪，请查看对应服务窗口的报错。已打开的窗口保留，可按 Ctrl+C 停止服务。"
}

function Start-GleanWindow {
    param([string]$Script)

    $scriptPath = Join-Path $PSScriptRoot $Script
    # These consoles are interactive: the user reads logs and stops each service with Ctrl+C.
    $powershellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    Start-Process -FilePath $powershellPath -WorkingDirectory $PSScriptRoot -WindowStyle Normal -ArgumentList @(
        '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit', '-File', "`"$scriptPath`""
    )
}

try {
    $python = if (Test-Path -LiteralPath 'D:\Tools\Python310\python.exe') {
        'D:\Tools\Python310\python.exe'
    } else {
        (Get-Command python -ErrorAction Stop).Source
    }
    if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        throw '未找到 Node.js 或 npm，请安装到 D:\Tools 并加入 PATH，再重新启动。'
    }
    if (-not (Test-Path -LiteralPath 'frontend\node_modules\vite\bin\vite.js')) {
        throw '前端依赖未安装。请在 frontend 目录执行 npm ci，完成后重新启动。'
    }
    & $python -c "import importlib.util, sys; modules = ['uvicorn', 'fastapi', 'playwright', 'bs4', 'lxml', 'openai', 'dotenv', 'httpx', 'jwt', 'multipart', 'tzdata']; missing = [name for name in modules if importlib.util.find_spec(name) is None]; print('Missing Python modules: ' + ', '.join(missing)) if missing else None; sys.exit(bool(missing))"
    if ($LASTEXITCODE -ne 0) {
        throw "后端依赖检查失败。请执行：& '$python' -m pip install -r requirements.lock"
    }
    foreach ($port in @(8000, 5173)) {
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
        if ($listeners.Count -gt 0) {
            $owners = ($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ', '
            throw "端口 $port 已被占用（PID: $owners）。请先停止对应服务，再启动 Glean。"
        }
    }
    $workerPattern = '(?i)(python(?:\.exe)?|py(?:\.exe)?)"?\s+-m\s+backend\.worker(?:\s|$)'
    $existing = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match $workerPattern })
    if ($existing.Count -gt 0) {
        $owners = ($existing | Select-Object -ExpandProperty ProcessId) -join ', '
        throw "Glean worker 已在运行（PID: $owners）。请先停止对应服务，再启动 Glean。"
    }
    if ($CheckOnly) {
        Write-Host '启动检查通过：依赖已安装，8000 和 5173 端口可用，没有重复 worker。' -ForegroundColor Green
        exit 0
    }

    Start-GleanWindow 'run_backend.ps1'
    Wait-GleanService '后端' 'http://127.0.0.1:8000/health/ready'
    Start-GleanWindow 'run_worker.ps1'
    Wait-GleanService '后台任务' 'http://127.0.0.1:8000/health/pipeline'
    Start-GleanWindow 'run_frontend.ps1'
    Wait-GleanService '前端' 'http://127.0.0.1:5173/'

    Write-Host 'Glean 已启动：http://localhost:5173/' -ForegroundColor Green
    Write-Host '三个服务窗口会保持打开；停止时在每个窗口按 Ctrl+C，再关闭窗口。'
    if (-not $NoBrowser) { Start-Process 'http://localhost:5173/' }
    exit 0
} catch {
    Write-Host "启动失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
