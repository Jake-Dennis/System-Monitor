@echo off
REM Launches System Monitor using the project's local virtualenv.
REM Double-click in Explorer, or run from any shell.
REM Uses pythonw.exe so no terminal window sticks around.

setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [run.bat] .venv not found. Creating it now...
    py -3.13 -m venv .venv
    if errorlevel 1 (
        echo [run.bat] Failed to create venv. Make sure "py -3.13" is available.
        pause
        exit /b 1
    )
    echo [run.bat] Installing requirements...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [run.bat] pip install failed. See output above.
        pause
        exit /b 1
    )
)

start "" ".venv\Scripts\pythonw.exe" run.py %*
endlocal
