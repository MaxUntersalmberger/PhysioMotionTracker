@echo off
setlocal

set "SCRIPT_DIR=%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%Start-Calibratie.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Starten mislukt met foutcode %EXIT_CODE%.
    echo Controleer de melding hierboven en probeer opnieuw.
    pause
)

exit /b %EXIT_CODE%
