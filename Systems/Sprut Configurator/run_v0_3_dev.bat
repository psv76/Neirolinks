@echo off
setlocal
cd /d "%~dp0"

where python.exe >nul 2>nul
if %errorlevel%==0 (
    python.exe sprut_configurator_dev.py
    goto :done
)

where py.exe >nul 2>nul
if %errorlevel%==0 (
    py.exe sprut_configurator_dev.py
    goto :done
)

echo.
echo Python not found.
echo Install Python and dependencies from reference\v0.2.2\requirements.txt.
pause
exit /b 1

:done
if errorlevel 1 (
    echo.
    echo Sprut Configurator v0.3.0-dev exited with an error.
    pause
)
