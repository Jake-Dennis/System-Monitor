@echo off
REM One-time setup: creates venv, installs Python deps, downloads
REM LibreHardwareMonitor for full GPU stats (AMD/Intel/NVIDIA).
REM Run this once in the project root, then use run.bat to launch.

setlocal
cd /d "%~dp0"

echo ========================================
echo  System Monitor — Full Install
echo ========================================

REM --- Step 1: Python virtual environment ---
if exist ".venv\Scripts\python.exe" (
    echo [1/4] Virtual env already exists — skipping.
) else (
    echo [1/4] Creating Python virtual env...
    py -3.13 -m venv .venv
    if errorlevel 1 (
        echo [!] Failed to create venv. Make sure "py -3.13" is available.
        pause
        exit /b 1
    )
)

REM --- Step 2: Pip packages ---
echo [2/4] Installing Python packages (may take a minute)...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [!] pip install failed. Check your internet connection.
    pause
    exit /b 1
)
echo [2/4] Python packages installed.

REM --- Step 3: LibreHardwareMonitor ---
set LHM_DIR=librehardwaremonitor
set LHM_EXE=%LHM_DIR%\LibreHardwareMonitor.exe
if exist "%LHM_EXE%" (
    echo [3/4] LibreHardwareMonitor already installed — skipping.
) else (
    echo [3/4] Downloading LibreHardwareMonitor (~50 MB)...
    set LHM_ZIP=%LHM_DIR%.zip
    set LHM_URL=https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/latest/download/LibreHardwareMonitor-net48.zip
    where powershell >nul 2>&1
    if errorlevel 1 (
        echo [!] PowerShell required for download. Install it and retry.
        pause
        exit /b 1
    )
    powershell -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%LHM_URL%' -OutFile '%LHM_ZIP%'"
    if not exist "%LHM_ZIP%" (
        echo [!] Download failed. Check your internet connection.
        pause
        exit /b 1
    )
    powershell -Command "Expand-Archive -Path '%LHM_ZIP%' -DestinationPath '%LHM_DIR%' -Force"
    del "%LHM_ZIP%" 2>nul
    if not exist "%LHM_EXE%" (
        echo [!] Extraction failed.
        pause
        exit /b 1
    )
    echo [3/4] LibreHardwareMonitor downloaded to %LHM_DIR%\
)

REM --- Step 4: Launch LHM (needs admin for sensor access) ---
echo [4/4] Launching LibreHardwareMonitor...
echo  This may prompt for Administrator access — click Yes.
powershell -Command "Start-Process -FilePath '%LHM_EXE%' -Verb RunAs"
echo [4/4] LHM started. It runs in the background and tray.
echo.
echo Done! The app is ready. Launch it with run.bat.
echo.
echo NOTE: For GPU usage to appear, LHM must be running as Admin.
echo run.bat starts it automatically if installed.
pause
endlocal
