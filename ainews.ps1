$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$python = if (Test-Path -LiteralPath 'D:\Tools\Python310\python.exe') {
    'D:\Tools\Python310\python.exe'
} else {
    'python'
}

& $python -m backend.cli @args
exit $LASTEXITCODE
