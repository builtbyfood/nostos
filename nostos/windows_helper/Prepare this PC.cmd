@echo off
rem Nostos 0.2.4 - Prepare this PC.cmd
rem Double-click this on the OLD Windows PC. To undo by hand later:
rem   "Prepare this PC.cmd" -Undo
title Nostos helper
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Prepare-Windows.ps1" %*
if errorlevel 1 pause
