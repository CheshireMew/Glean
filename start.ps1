# Public Windows entry point; service scripts live under scripts/windows.
[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'scripts/windows/start-services.ps1') @PSBoundParameters
exit $LASTEXITCODE
