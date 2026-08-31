@echo off
REM Launches System Monitor WITHOUT Administrator elevation.
REM Use this if you don't want the UAC prompt. Note: CPU temperature
REM will NOT be available (requires admin); GPU temp still works via NVML.

setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [run-noadmin.bat] .venv not found. Running setup.bat first...
    call setup.bat
    if errorlevel 1 (
        echo [run-noadmin.bat] Setup failed. See output above.
        pause
        exit /b 1
    )
)

start "" ".venv\Scripts\pythonw.exe" run.py %*
endlocal
