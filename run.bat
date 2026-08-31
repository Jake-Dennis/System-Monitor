@echo off
REM Launches System Monitor using the project's local virtualenv.
REM Uses pythonw.exe so no terminal window sticks around.
REM Run setup.bat first if .venv doesn't exist yet.
REM Self-elevates via UAC so CPU temperature (MSAcpi_ThermalZoneTemperature)
REM can be read. If you don't want elevation, use run-noadmin.bat.

setlocal
cd /d "%~dp0"

REM --- Self-elevate to Administrator (UAC prompt) if not already ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [run.bat] Requesting Administrator privileges for CPU temperature...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

if not exist ".venv\Scripts\python.exe" (
    echo [run.bat] .venv not found. Running setup.bat first...
    call setup.bat
    if errorlevel 1 (
        echo [run.bat] Setup failed. See output above.
        pause
        exit /b 1
    )
)

start "" ".venv\Scripts\pythonw.exe" run.py %*
endlocal
