@echo off
REM Launches System Monitor using the project's local virtualenv.
REM Uses pythonw.exe so no terminal window sticks around.
REM Run setup.bat first if .venv doesn't exist yet.

setlocal
cd /d "%~dp0"

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
