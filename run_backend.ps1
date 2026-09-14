$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$port = 8000
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
    $owners = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($ownerPid in $owners) {
        $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $ownerPid" -ErrorAction SilentlyContinue
        Write-Error "端口 $port 已被进程 $ownerPid 占用：$($owner.CommandLine)。请先明确停止该进程，本脚本不会强制结束它。"
    }
    exit 1
}

$python = if (Test-Path -LiteralPath 'D:\Tools\Python310\python.exe') { 'D:\Tools\Python310\python.exe' } else { 'python' }
$env:GLEAN_ENV = 'development'
Write-Host "Starting Glean backend in development mode..." -ForegroundColor Cyan
& $python -m uvicorn backend.main:app --host 127.0.0.1 --port $port --reload
