@echo off
rem ASCII only: cmd reads .bat files using the system ANSI codepage (GBK on
rem Chinese Windows), so non-ASCII text here can turn into garbage commands.
rem The real launcher is start.ps1 (UTF-8 / Chinese paths handled by PowerShell).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
if errorlevel 1 pause
