@echo off
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0auto_publish_updates.ps1" -PollSeconds 10
