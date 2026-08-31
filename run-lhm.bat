@echo off
REM Launches the System Monitor app only (no LibreHardwareMonitor).
REM
REM For CPU temperature to show, LibreHardwareMonitor must already be
REM running with its Remote Web Server enabled:
REM   - Start LibreHardwareMonitor as Administrator (e.g. the exe in
REM     tools\LibreHardwareMonitor\LibreHardwareMonitor.exe)
REM   - In LHM, enable Options > Remote Web Server > Run (one time - the
REM     setting is remembered)
REM Then launch this script. The monitor reads CPU temp from LHM over
REM localhost (no admin needed for the monitor itself).
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

REM --- Launch the monitor only ---
start "" ".venv\Scripts\pythonw.exe" run.py %*
endlocal
