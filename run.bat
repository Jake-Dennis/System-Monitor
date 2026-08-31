@echo off
REM Single launcher for System Monitor.
REM - Self-elevates via UAC (needed for CPU temperature).
REM - Installs/updates dependencies and LibreHardwareMonitor.
REM - Starts LibreHardwareMonitor silently (minimized to tray) so CPU
REM   temperature works without you managing LHM.
REM - Waits for LHM's web server, then launches the monitor.

setlocal enabledelayedexpansion
cd /d "%~dp0"

REM --- Self-elevate to Administrator (UAC prompt) if not already ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [run.bat] Requesting Administrator privileges for CPU temperature...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

REM --- Ensure dependencies are installed ---
if not exist ".venv\Scripts\python.exe" (
    echo [run.bat] .venv not found. Running setup.bat first...
    call setup.bat
    if errorlevel 1 (
        echo [run.bat] Setup failed. See output above.
        pause
        exit /b 1
    )
) else (
    REM --- Ensure dependencies are installed and up to date ---
    REM Re-run setup if the marker is missing or requirements.txt changed.
    set NEED_SETUP=0
    if not exist ".venv\.deps_hash" set NEED_SETUP=1
    if "!NEED_SETUP!"=="0" (
        ".venv\Scripts\python.exe" -c "import hashlib; print(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())" > ".venv\.deps_hash.tmp"
        fc /b ".venv\.deps_hash" ".venv\.deps_hash.tmp" >nul 2>&1
        if errorlevel 1 set NEED_SETUP=1
        del ".venv\.deps_hash.tmp" >nul 2>&1
    )
    if "!NEED_SETUP!"=="1" (
        echo [run.bat] Dependencies missing or out of date. Running setup.bat...
        call setup.bat
        if errorlevel 1 (
            echo [run.bat] Setup failed. See output above.
            pause
            exit /b 1
        )
    )
)

REM --- Ensure LibreHardwareMonitor is installed ---
if not exist "tools\LibreHardwareMonitor\LibreHardwareMonitor.exe" (
    echo [run.bat] Installing LibreHardwareMonitor...
    call setup.bat
    if errorlevel 1 (
        echo [run.bat] Setup failed. See output above.
        pause
        exit /b 1
    )
)

REM --- Start LibreHardwareMonitor silently (minimized to tray) ---
echo [run.bat] Starting LibreHardwareMonitor (for CPU temperature)...
start "" /min "tools\LibreHardwareMonitor\LibreHardwareMonitor.exe"

REM --- Wait for LHM's Remote Web Server to come up (max ~20s) ---
echo [run.bat] Waiting for LibreHardwareMonitor web server...
set /a WAIT=0
:waitloop
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://localhost:8085/data.json' -UseBasicParsing -TimeoutSec 1).StatusCode } catch { 0 }" > "%TEMP%\lhm_probe.txt" 2>nul
set /p PROBE=<"%TEMP%\lhm_probe.txt"
if "%PROBE%"=="200" goto serverup
set /a WAIT+=1
if %WAIT% GEQ 20 (
    echo [run.bat] LHM web server did not respond. CPU temperature may not show.
    goto launch
)
timeout /t 1 /nobreak >nul
goto waitloop
:serverup
echo [run.bat] LibreHardwareMonitor web server is up.
:launch

REM --- Launch the monitor ---
start "" ".venv\Scripts\pythonw.exe" run.py %*
endlocal
