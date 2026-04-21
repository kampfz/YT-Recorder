@echo off
title YT Downloader - Debug Log
cd /d "%~dp0"
echo Starting YT Downloader with logging...
echo ========================================
python main.py 2>&1
echo.
echo ========================================
echo App exited. Press any key to close.
pause >nul
