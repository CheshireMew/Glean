[CmdletBinding()]
param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$python = if (Test-Path -LiteralPath 'D:\Tools\Python310\python.exe') {
    'D:\Tools\Python310\python.exe'
} else {
    (Get-Command python -ErrorAction Stop).Source
}
$launcherArgs = @((Join-Path $PSScriptRoot 'launcher.py'), '--frontend-only', '--no-browser')
if ($CheckOnly) { $launcherArgs += '--check-only' }
& $python @launcherArgs
exit $LASTEXITCODE
