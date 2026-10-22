@echo off
where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found in PATH.
    echo Please install Python 3.11+ from python.org, then run this installer again.
    start "" "https://www.python.org/downloads/"
    exit /b 1
)

cd /d "%~dp0"
python install.py
