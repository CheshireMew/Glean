@echo off
setlocal
title Glean Launcher
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
set "glean_exit_code=%errorlevel%"
if not "%glean_exit_code%"=="0" pause
exit /b %glean_exit_code%
