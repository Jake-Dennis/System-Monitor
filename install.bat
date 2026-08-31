@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo  System Monitor - Full Install
echo ========================================

if exist ".venv\Scripts\python.exe" (
    echo [1/2] Virtual env exists
) else (
    echo [1/2] Creating venv...
    py -3.13 -m venv .venv
)

echo [2/2] Installing Python packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo [2/2] Done

echo.
echo Install complete. Run run.bat to launch the app.
echo GPU stats come from built-in Windows Performance Counters
echo (no external software required). For fan/power on Intel/AMD,
echo run setup_lhm.bat once to download LibreHardwareMonitor.
pause
endlocal
