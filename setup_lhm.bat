@echo off
REM Download and launch LibreHardwareMonitor for full GPU stats
REM (AMD/Intel utilization, power, fan, and CPU package power).
REM LHM must run as Administrator to access hardware sensors.
REM Run this script once — it will persist across reboots and
REM auto-start LHM on login if you place it in the Startup folder.

setlocal
cd /d "%~dp0"

set LHM_DIR=librehardwaremonitor
set LHM_ZIP=%LHM_DIR%.zip
set LHM_EXE=%LHM_DIR%\LibreHardwareMonitor.exe

REM --- Check if already installed ---
if exist "%LHM_EXE%" (
    echo [lhm] LibreHardwareMonitor found. Starting...
    goto :start
)

REM --- Download ---
echo [lhm] Downloading LibreHardwareMonitor...
echo [lhm] This is ~50 MB. Please wait...

REM Use the latest stable release URL
set LHM_URL=https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/latest/download/LibreHardwareMonitor-net48.zip

where powershell >nul 2>&1
if errorlevel 1 (
    echo [lhm] PowerShell required for download. Install it and retry.
    pause
    exit /b 1
)

powershell -Command "
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri '%LHM_URL%' -OutFile '%LHM_ZIP%'
"
if not exist "%LHM_ZIP%" (
    echo [lhm] Download failed. Check your internet connection.
    pause
    exit /b 1
)

REM --- Extract ---
echo [lhm] Extracting...
powershell -Command "
    Expand-Archive -Path '%LHM_ZIP%' -DestinationPath '%LHM_DIR%' -Force
"
del "%LHM_ZIP%" 2>nul

if not exist "%LHM_EXE%" (
    echo [lhm] Extraction failed.
    pause
    exit /b 1
)

echo [lhm] Installed to %LHM_DIR%\

REM --- Prompt for admin rights ---
:start
echo [lhm] Launching LibreHardwareMonitor (may prompt for Admin rights)...
start "" "%LHM_EXE%"

echo [lhm] Done. LHM is now running on http://localhost:8085/data.json
echo [lhm] Leave it running in the background for GPU stats to appear.
echo.
echo NOTE: For auto-start on login, place a shortcut to
echo   "%LHM_EXE%"
echo in your Startup folder (shell:startup) and set it to
echo "Run as administrator" in Properties ^> Advanced.
endlocal
