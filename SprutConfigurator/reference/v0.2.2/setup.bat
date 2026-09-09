@echo off
setlocal
cd /d "%~dp0"

where python.exe >nul 2>nul
if %errorlevel%==0 (
    set "PY=python.exe"
    goto :install
)

where py.exe >nul 2>nul
if %errorlevel%==0 (
    set "PY=py.exe"
    goto :install
)

echo.
echo Python not found.
echo Install Python 3.11+ and run setup.bat again.
pause
exit /b 1

:install
echo Using: %PY%
%PY% -m pip install --upgrade pip
if errorlevel 1 goto :fail

%PY% -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo Setup completed.
pause
exit /b 0

:fail
echo.
echo Setup failed.
pause
exit /b 1
