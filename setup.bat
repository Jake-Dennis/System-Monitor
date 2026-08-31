@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo  System Monitor - Install
echo ========================================

if exist ".venv\Scripts\python.exe" (
    echo [1/2] Virtual env already exists
) else (
    echo [1/2] Creating Python virtual env...
    py -3.13 -m venv .venv
)

echo [2/2] Installing Python packages (may take a minute)...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [!] pip install failed. Check your internet connection.
    pause
    exit /b 1
)
echo [2/2] Python packages installed.

echo.
echo Install complete. Launch the app with run.bat.
echo.
echo GPU stats use built-in Windows Performance Counters
echo (no external software required). All GPUs work out of the box.
pause
endlocal
