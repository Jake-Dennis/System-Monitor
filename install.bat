@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo  System Monitor - Full Install
echo ========================================

if exist ".venv\Scripts\python.exe" (
    echo [1/3] Virtual env exists
) else (
    echo [1/3] Creating venv...
    py -3.13 -m venv .venv
)

echo [2/3] Installing Python packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo [2/3] Done

set LHM_DIR=librehardwaremonitor
set LHM_EXE=%LHM_DIR%\LibreHardwareMonitor.exe

if exist "%LHM_EXE%" (
    echo [3/3] LHM already installed
) else (
    echo [3/3] Downloading LibreHardwareMonitor...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.6/LibreHardwareMonitor.zip' -OutFile librehardwaremonitor.zip -UseBasicParsing"
    if exist librehardwaremonitor.zip (
        powershell -Command "Expand-Archive -Path librehardwaremonitor.zip -DestinationPath librehardwaremonitor -Force"
        del librehardwaremonitor.zip
        echo [3/3] LHM downloaded
    ) else (
        echo [!] Download failed
    )
)

if exist "%LHM_EXE%" (
    start "" "%LHM_EXE%"
)

echo Done.
pause
endlocal
