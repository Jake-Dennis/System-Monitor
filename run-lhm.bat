@echo off
REM Launches System Monitor WITH CPU temperature support.
REM Starts LibreHardwareMonitor (as Administrator) so it can read CPU
REM temperature, then launches the System Monitor app which reads from
REM LHM over localhost (no admin needed for the monitor itself).
REM
REM First time: after LHM opens, enable Options > Remote Web Server > Run
REM (one time - the setting is remembered). Then the monitor shows CPU temp.
REM
REM If you don't want CPU temperature, use run.bat or run-noadmin.bat.

setlocal enabledelayedexpansion
cd /d "%~dp0"

REM --- Ensure dependencies are installed ---
if not exist ".venv\Scripts\python.exe" (
    echo [run-lhm.bat] .venv not found. Running setup.bat first...
    call setup.bat
    if errorlevel 1 (
        echo [run-lhm.bat] Setup failed. See output above.
        pause
        exit /b 1
    )
) else (
    set NEED_SETUP=0
    if not exist ".venv\.deps_hash" set NEED_SETUP=1
    if "!NEED_SETUP!"=="0" (
        ".venv\Scripts\python.exe" -c "import hashlib; print(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())" > ".venv\.deps_hash.tmp"
        fc /b ".venv\.deps_hash" ".venv\.deps_hash.tmp" >nul 2>&1
        if errorlevel 1 set NEED_SETUP=1
        del ".venv\.deps_hash.tmp" >nul 2>&1
    )
    if "!NEED_SETUP!"=="1" (
        echo [run-lhm.bat] Dependencies missing or out of date. Running setup.bat...
        call setup.bat
        if errorlevel 1 (
            echo [run-lhm.bat] Setup failed. See output above.
            pause
            exit /b 1
        )
    )
)

REM --- Check LHM is installed ---
if not exist "tools\LibreHardwareMonitor\LibreHardwareMonitor.exe" (
    echo [run-lhm.bat] LibreHardwareMonitor not found. Running setup.bat...
    call setup.bat
    if errorlevel 1 (
        echo [run-lhm.bat] Setup failed. See output above.
        pause
        exit /b 1
    )
)

REM --- Launch LibreHardwareMonitor as Administrator (UAC prompt) ---
echo [run-lhm.bat] Starting LibreHardwareMonitor as Administrator...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Start-Process -FilePath '%~dp0tools\LibreHardwareMonitor\LibreHardwareMonitor.exe' -Verb RunAs"

REM --- Give LHM a moment to start its web server ---
echo [run-lhm.bat] Waiting for LibreHardwareMonitor web server...
timeout /t 3 /nobreak >nul

REM --- Launch the monitor ---
start "" ".venv\Scripts\pythonw.exe" run.py %*
endlocal
