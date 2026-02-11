@echo off
SET PowerShellScriptPath=%~dp0package_addon.ps1
pwsh -NoProfile -ExecutionPolicy Bypass -File "%PowerShellScriptPath%"
pause
