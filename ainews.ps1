# Compatibility entry point for existing scripts. Use glean.ps1 for new integrations.
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'glean.ps1') @args
exit $LASTEXITCODE
