@echo off
REM Uninstalls System Monitor — removes venv, startup shortcut, and optionally config.
REM Run from the project directory.

setlocal
cd /d "%~dp0"

echo.
echo ============================================
echo   System Monitor - Uninstall
echo ============================================
echo.

:: Remove .venv
if exist ".venv\" (
    echo [uninstall] Removing virtual environment...
    rmdir /s /q ".venv"
    if errorlevel 1 (
        echo [uninstall] WARNING: Could not fully remove .venv. You may need to close
        echo           programs using Python in this folder and try again.
    ) else (
        echo [uninstall] Virtual environment removed.
    )
) else (
    echo [uninstall] No virtual environment found.
)

:: Remove startup shortcut
set STARTUP_LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\System Monitor.lnk
if exist "%STARTUP_LNK%" (
    echo [uninstall] Removing startup shortcut...
    del "%STARTUP_LNK%"
    echo [uninstall] Startup shortcut removed.
) else (
    echo [uninstall] No startup shortcut found.
)

:: Ask about config
echo.
echo [uninstall] The config file at %%APPDATA%%\SystemMonitor\config.json was not removed.
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
echo [uninstall] Done. The source files in %~dp0 are still present
echo           in case you want to reinstall. Delete the folder manually
echo           to remove them completely.
echo.
pause
endlocal
