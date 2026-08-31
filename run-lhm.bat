@echo off
REM Launches LibreHardwareMonitor (silently, for CPU temperature) and then
REM the System Monitor app.
REM
REM First time only:
REM   - A UAC prompt appears to run LHM as Administrator (needed to read
REM     CPU sensors). Tick "remember" so it won't ask again.
REM   - In LHM, enable Options > Remote Web Server > Run (one time - the
REM     setting is remembered).
REM   - Optional: enable Options > Start Minimized so LHM stays in the tray
REM     instead of showing its window.
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

REM --- Ensure LHM is installed ---
if not exist "tools\LibreHardwareMonitor\LibreHardwareMonitor.exe" (
    echo [run-lhm.bat] LibreHardwareMonitor not found. Running setup.bat...
    call setup.bat
    if errorlevel 1 (
        echo [run-lhm.bat] Setup failed. See output above.
        pause
        exit /b 1
    )
)

REM --- Start LibreHardwareMonitor as Administrator, minimized to tray ---
echo [run-lhm.bat] Starting LibreHardwareMonitor (as Administrator)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Start-Process -FilePath '%~dp0tools\LibreHardwareMonitor\LibreHardwareMonitor.exe' -Verb RunAs -WindowStyle Minimized"

REM --- Wait for LHM's Remote Web Server to come up (max ~20s) ---
echo [run-lhm.bat] Waiting for LibreHardwareMonitor web server...
set /a WAIT=0
:waitloop
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://localhost:8085/data.json' -UseBasicParsing -TimeoutSec 1).StatusCode } catch { 0 }" > "%TEMP%\lhm_probe.txt" 2>nul
set /p PROBE=<"%TEMP%\lhm_probe.txt"
if "%PROBE%"=="200" goto serverup
set /a WAIT+=1
if %WAIT% GEQ 20 (
    echo [run-lhm.bat] LHM web server did not respond. CPU temperature may not show.
    goto launch
)
timeout /t 1 /nobreak >nul
goto waitloop
:serverup
echo [run-lhm.bat] LibreHardwareMonitor web server is up.
:launch

REM --- Launch the monitor ---
start "" ".venv\Scripts\pythonw.exe" run.py %*
endlocal
