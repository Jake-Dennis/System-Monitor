@echo off
REM Uninstalls System Monitor - removes venv, startup shortcut, and
REM optionally the saved config. Source files are left in place.
REM Run from the project directory.

setlocal
cd /d "%~dp0"

echo.
echo ============================================
echo   System Monitor - Uninstall
echo ============================================
echo.

REM --- Remove virtual environment ---
if exist ".venv\" (
    echo [uninstall] Removing virtual environment...
    rmdir /s /q ".venv"
    if errorlevel 1 (
        echo [uninstall] WARNING: Could not fully remove .venv. Close any
        echo           programs using Python in this folder and try again.
    ) else (
        echo [uninstall] Virtual environment removed.
    )
) else (
    echo [uninstall] No virtual environment found.
)

REM --- Remove startup shortcut ---
set STARTUP_LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\System Monitor.lnk
if exist "%STARTUP_LNK%" (
    echo [uninstall] Removing startup shortcut...
    del "%STARTUP_LNK%"
    echo [uninstall] Startup shortcut removed.
) else (
    echo [uninstall] No startup shortcut found.
)

REM --- Remove LibreHardwareMonitor (optional temp tool) ---
if exist "tools\LibreHardwareMonitor\" (
    echo [uninstall] Removing LibreHardwareMonitor...
    rmdir /s /q "tools\LibreHardwareMonitor"
    echo [uninstall] LibreHardwareMonitor removed.
) else (
    echo [uninstall] No LibreHardwareMonitor found.
)

REM --- Optionally remove config ---
echo.
echo [uninstall] Config file at %APPDATA%\SystemMonitor\config.json
echo           will NOT be removed automatically.
echo.
setlocal enabledelayedexpansion
set /p REMOVE_CONFIG=Remove saved settings and config? (y/N): 
if /i "!REMOVE_CONFIG!"=="y" (
    if exist "%APPDATA%\SystemMonitor\" (
        rmdir /s /q "%APPDATA%\SystemMonitor"
        echo [uninstall] Config and settings removed.
    ) else (
        echo [uninstall] No config found.
    )
)
endlocal

echo.
echo [uninstall] Done. Source files in %~dp0 are still present
echo           in case you want to reinstall. Delete the folder
echo           manually to remove them completely.
echo.
pause
endlocal
