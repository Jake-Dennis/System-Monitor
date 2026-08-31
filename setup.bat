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

REM --- Install LibreHardwareMonitor (optional, for CPU temperature) ---
echo.
echo [3/3] LibreHardwareMonitor (for CPU temperature)...
if exist "tools\LibreHardwareMonitor\LibreHardwareMonitor.exe" (
    echo [3/3] LibreHardwareMonitor already installed.
) else (
    echo [3/3] Downloading LibreHardwareMonitor v0.9.6...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $u='https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.6/LibreHardwareMonitor.zip'; $z=Join-Path $PWD 'tools\lhm.zip'; New-Item -ItemType Directory -Force -Path 'tools' | Out-Null; Invoke-WebRequest -Uri $u -OutFile $z -UseBasicParsing; Expand-Archive -Path $z -DestinationPath 'tools\LibreHardwareMonitor' -Force; Remove-Item $z -Force"
    if errorlevel 1 (
        echo [!] LibreHardwareMonitor download failed. CPU temperature will be
        echo     unavailable, but all other features still work.
    ) else (
        echo [3/3] LibreHardwareMonitor installed to tools\LibreHardwareMonitor.
        echo       Run run-lhm.bat to launch it with the monitor.
    )
)

echo.
echo Install complete. Launch the app with run.bat.
echo.
echo GPU stats use built-in Windows Performance Counters
echo (no external software required). All GPUs work out of the box.
echo.
echo For CPU temperature:
echo   - Run run-lhm.bat (launches LibreHardwareMonitor as Admin + the monitor)
echo   - In LibreHardwareMonitor, enable Options ^> Remote Web Server ^> Run
echo     (one time - the setting is remembered).
pause
endlocal
