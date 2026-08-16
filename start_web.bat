@echo off
setlocal EnableExtensions

title Viewledge Web UI
cd /d "%~dp0"

if not defined VIEWLEDGE_UI_MODE set "VIEWLEDGE_UI_MODE=product"
if not defined SHOW_TECH_DETAILS set "SHOW_TECH_DETAILS=0"
if not defined SHOW_RAW_PROCESS_LOGS set "SHOW_RAW_PROCESS_LOGS=0"
if not defined VIEWLEDGE_OUTPUT_ROOT set "VIEWLEDGE_OUTPUT_ROOT=%LOCALAPPDATA%\Viewledge\knowledge"
if not defined VIEWLEDGE_STATE_ROOT set "VIEWLEDGE_STATE_ROOT=%LOCALAPPDATA%\Viewledge\state"
set "VIEWLEDGE_VERSION_CHECK=%TEMP%\viewledge-python-version-%RANDOM%.txt"

echo.
echo ==========================================
echo   Viewledge
echo ==========================================
echo.

if not exist "src\web.py" goto project_missing
if not exist "requirements.txt" goto project_missing

if exist ".venv\Scripts\python.exe" goto validate_existing_venv

echo [1/4] Checking Python...

where py >nul 2>&1
if not errorlevel 1 goto try_py312

where python >nul 2>&1
if not errorlevel 1 goto use_python

goto python_missing

:try_py312
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 goto use_py312

where python >nul 2>&1
if not errorlevel 1 goto use_python

goto python_missing

:use_py312
echo [2/4] Creating Python 3.12 virtual environment...
py -3.12 -m venv ".venv"
goto check_venv

:use_python
python --version >"%VIEWLEDGE_VERSION_CHECK%" 2>&1
set /p VIEWLEDGE_PYTHON_VERSION=<"%VIEWLEDGE_VERSION_CHECK%"
del /q "%VIEWLEDGE_VERSION_CHECK%" >nul 2>&1
if not "%VIEWLEDGE_PYTHON_VERSION:~0,11%"=="Python 3.12" goto python_version_error

echo [2/4] Creating Python virtual environment...
python -m venv ".venv"
goto check_venv

:check_venv
if errorlevel 1 goto venv_failed
if not exist ".venv\Scripts\python.exe" goto venv_failed

:validate_existing_venv
".venv\Scripts\python.exe" --version >"%VIEWLEDGE_VERSION_CHECK%" 2>&1
set /p VIEWLEDGE_PYTHON_VERSION=<"%VIEWLEDGE_VERSION_CHECK%"
del /q "%VIEWLEDGE_VERSION_CHECK%" >nul 2>&1
if not "%VIEWLEDGE_PYTHON_VERSION:~0,11%"=="Python 3.12" goto venv_version_error

:install_dependencies
echo [3/4] Checking project dependencies...
echo First run may take a few minutes. Keep the network available.
echo.

if exist "requirements.lock.txt" goto install_locked
goto install_regular

:install_locked
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "requirements.lock.txt"
goto dependencies_checked

:install_regular
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "requirements.txt"
goto dependencies_checked

:dependencies_checked
if errorlevel 1 goto dependencies_failed

echo.
if exist "tools\ffmpeg\bin\ffmpeg.exe" goto check_data_dir
where ffmpeg >nul 2>&1
if not errorlevel 1 goto check_data_dir

echo [NOTICE] FFmpeg was not detected.
echo Videos with platform subtitles may still work. Media extraction may be unavailable.
echo.

:check_data_dir
if not exist "%VIEWLEDGE_OUTPUT_ROOT%" mkdir "%VIEWLEDGE_OUTPUT_ROOT%" >nul 2>&1
if errorlevel 1 goto data_dir_failed
>"%VIEWLEDGE_OUTPUT_ROOT%\.viewledge-write-test.tmp" echo ok
if errorlevel 1 goto data_dir_failed
del /q "%VIEWLEDGE_OUTPUT_ROOT%\.viewledge-write-test.tmp" >nul 2>&1

:launch_web
netstat -ano | findstr /R /C:":5188 .*LISTENING" >nul 2>&1
if not errorlevel 1 goto port_in_use

echo [4/4] Starting Web UI...
echo.
echo Browser: http://127.0.0.1:5188
echo Keep this window open. Press Ctrl+C to stop Viewledge.
echo.

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:5188"

".venv\Scripts\python.exe" -m src.web

if errorlevel 1 goto web_failed

endlocal
exit /b 0

:project_missing
echo [ERROR] Project files are incomplete.
echo Make sure the ZIP is fully extracted and contains:
echo.
echo   src\web.py
echo   requirements.txt
echo.
pause
exit /b 1

:python_missing
echo [ERROR] Python was not detected.
echo Install Python 3.12 and enable Add Python to PATH.
echo.
pause
exit /b 1

:python_version_error
echo [ERROR] Python 3.12 is required.
echo Install Python 3.12 and enable Add Python to PATH.
echo.
pause
exit /b 1

:venv_failed
echo [ERROR] Failed to create the Python virtual environment.
echo Delete the .venv folder in this project and try again.
echo.
pause
exit /b 1

:dependencies_failed
echo [ERROR] Failed to install project dependencies.
echo Check network, proxy settings, and requirements files.
echo.
pause
exit /b 1

:venv_version_error
echo [ERROR] Existing .venv is not Python 3.12.
echo Delete the .venv folder in this project, then run start_web.bat again.
echo.
pause
exit /b 1

:data_dir_failed
echo [ERROR] Viewledge data directory is not writable.
echo Set VIEWLEDGE_OUTPUT_ROOT to a writable folder and try again.
echo.
pause
exit /b 1

:port_in_use
echo [ERROR] Port 5188 is already in use.
echo Close the old Viewledge window or the program using this port, then try again.
echo.
pause
exit /b 1

:web_failed
echo.
echo [ERROR] Web UI failed to start.
echo Keep the error output above for troubleshooting.
echo.
pause
exit /b 1
