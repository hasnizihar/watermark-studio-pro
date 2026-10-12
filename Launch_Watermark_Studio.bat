@echo off
setlocal enabledelayedexpansion
title Watermark Studio Pro V2

echo =====================================================================
echo                   WATERMARK STUDIO PRO V2 (64-bit)
echo =====================================================================
echo.

:: 1. Navigate to script directory
cd /d "%~dp0"
set "APP_DIR=%~dp0WatermarkStudio"

:: 2. Check for Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found on your system PATH!
    echo Please install Python 3.10+ from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: 3. Check Python version
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
echo [OK] Detected Python %PY_VER%

:: 4. Verify required packages
python -c "import flask, PIL" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [INFO] Installing required libraries from requirements.txt...
    python -m pip install -r "%APP_DIR%\requirements.txt"
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to install required libraries.
        pause
        exit /b 1
    )
)
echo [OK] Dependencies verified (Flask, Pillow).

:: 5. Launch Application
cd /d "%APP_DIR%"
echo.
echo [STARTING] Launching Watermark Studio Pro at http://127.0.0.1:5000 ...
echo [INFO] Press Ctrl+C in this window when you want to stop the server.
echo =====================================================================
echo.

python app.py
pause
