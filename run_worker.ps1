$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$workerPattern = '(?i)(python(?:\.exe)?|py(?:\.exe)?)"?\s+-m\s+backend\.worker(?:\s|$)'
$existing = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match $workerPattern }

if ($existing) {
    $processIds = ($existing | Select-Object -ExpandProperty ProcessId) -join ', '
    Write-Error "AINEWS worker 已在运行（PID: $processIds）。本脚本不会强制结束现有 worker。"
    exit 1
}

$python = if (Test-Path -LiteralPath 'D:\Tools\Python310\python.exe') { 'D:\Tools\Python310\python.exe' } else { 'python' }
$env:AINEWS_ENV = 'development'
Write-Host "Starting AINEWS worker in development mode..." -ForegroundColor Cyan
& $python -m backend.worker
