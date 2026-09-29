@echo off
setlocal
cd /d "%~dp0"

where python.exe >nul 2>nul
if %errorlevel%==0 (
    python.exe sprut_configurator.py
    goto :done
)

where py.exe >nul 2>nul
if %errorlevel%==0 (
    py.exe sprut_configurator.py
    goto :done
)

echo.
echo Python not found.
echo Run setup.bat after installing Python.
pause
exit /b 1

:done
if errorlevel 1 (
    echo.
    echo Sprut Configurator exited with an error.
    pause
)
