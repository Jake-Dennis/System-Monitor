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
    if errorlevel 1 (
        echo [!] Failed to create virtual env. Is Python 3.13 installed?
        pause
        exit /b 1
    )
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

REM --- Record that dependencies are installed (with requirements hash) ---
".venv\Scripts\python.exe" -c "import hashlib; print(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())" > ".venv\.deps_hash"
if errorlevel 1 (
    echo [!] Could not write dependency marker. Run.bat may reinstall next time.
) else (
    echo [ok] Dependency marker written.
)

echo.
echo Install complete. Launch the app with run.bat.
echo.
echo GPU stats use built-in Windows Performance Counters
echo (no external software required). All GPUs work out of the box.
echo.
echo NOTE: For CPU temperature, run LibreHardwareMonitor (as Admin) with
echo the Remote Web Server enabled, or launch run.bat as Administrator.
pause
endlocal
