@echo off
REM Installs Python dependencies for System Monitor into a local .venv.
REM Idempotent — safe to re-run to update to the latest requirements.
REM Run from this directory, or call from any shell. After this, run run.bat.

setlocal
cd /d "%~dp0"

if not exist "requirements.txt" (
    echo [install.bat] requirements.txt not found in %CD%.
    exit /b 1
)

if not defined PYTHON and not exist ".venv\Scripts\python.exe" (
    set PYTHON=py -3.13
)

if not exist ".venv\Scripts\python.exe" (
    echo [install.bat] No .venv found. Creating it with %PYTHON%...
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo [install.bat] Failed to create venv. Make sure Python 3.13 is available via "py -3.13" or set PYTHON=python.exe.
        exit /b 1
    )
) else (
    echo [install.bat] Reusing existing .venv.
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [install.bat] Failed to activate .venv.
    exit /b 1
)

echo [install.bat] Upgrading pip...
python -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo [install.bat] pip upgrade failed.
    exit /b 1
)

echo [install.bat] Installing requirements...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [install.bat] pip install failed. See output above.
    exit /b 1
)

echo.
echo [install.bat] Done. To launch the app, run run.bat
endlocal
