[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$python = if (Test-Path -LiteralPath 'D:\Tools\Python310\python.exe') {
    'D:\Tools\Python310\python.exe'
} else {
    (Get-Command python -ErrorAction Stop).Source
}
$launcherArgs = @((Join-Path $PSScriptRoot 'launcher.py'))
if ($CheckOnly) { $launcherArgs += '--check-only' }
if ($NoBrowser) { $launcherArgs += '--no-browser' }
& $python @launcherArgs
exit $LASTEXITCODE
