@echo off
chcp 65001 >nul
setlocal EnableExtensions

title Video Summary Skill Web UI
cd /d "%~dp0"

if not defined VIEWLEDGE_UI_MODE set "VIEWLEDGE_UI_MODE=product"
if not defined SHOW_TECH_DETAILS set "SHOW_TECH_DETAILS=0"
if not defined SHOW_RAW_PROCESS_LOGS set "SHOW_RAW_PROCESS_LOGS=0"
if not defined VIEWLEDGE_OUTPUT_ROOT set "VIEWLEDGE_OUTPUT_ROOT=%LOCALAPPDATA%\Viewledge\knowledge"

echo.
echo ==========================================
echo   Viewledge
echo ==========================================
echo.

if not exist "src\web.py" goto project_missing
if not exist "requirements.txt" goto project_missing

if exist ".venv\Scripts\python.exe" goto validate_existing_venv

echo [1/4] 正在检测 Python...

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
echo [2/4] 正在创建 Python 3.12 虚拟环境...
py -3.12 -m venv ".venv"
goto check_venv

:use_python
python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,12) else 1)" >nul 2>&1
if errorlevel 1 goto python_version_error

echo [2/4] 正在创建 Python 虚拟环境...
python -m venv ".venv"
goto check_venv

:check_venv
if errorlevel 1 goto venv_failed
if not exist ".venv\Scripts\python.exe" goto venv_failed

:validate_existing_venv
".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,12) else 1)" >nul 2>&1
if errorlevel 1 goto venv_version_error

:install_dependencies
echo [3/4] 正在检查项目依赖...
echo 首次运行可能需要几分钟，请保持网络连接。
echo.

if exist "requirements.lock.txt" (
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "requirements.lock.txt"
) else (
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "requirements.txt"
)

if errorlevel 1 goto dependencies_failed

echo.
if exist "tools\ffmpeg\bin\ffmpeg.exe" goto check_data_dir
where ffmpeg >nul 2>&1
if not errorlevel 1 goto check_data_dir

echo [提示] 未检测到 FFmpeg。
echo 已有平台字幕的视频仍可处理，其他媒体功能可能不可用。
echo.

:check_data_dir
if not exist "%VIEWLEDGE_OUTPUT_ROOT%" mkdir "%VIEWLEDGE_OUTPUT_ROOT%" >nul 2>&1
if errorlevel 1 goto data_dir_failed
(
    >"%VIEWLEDGE_OUTPUT_ROOT%\.viewledge-write-test.tmp" echo ok
) 2>nul
if errorlevel 1 goto data_dir_failed
del /q "%VIEWLEDGE_OUTPUT_ROOT%\.viewledge-write-test.tmp" >nul 2>&1

:launch_web
netstat -ano | findstr /R /C:":5188 .*LISTENING" >nul 2>&1
if not errorlevel 1 goto port_in_use

echo [4/4] 正在启动 Web UI...
echo.
echo 浏览器地址：http://127.0.0.1:5188
echo 请勿关闭此窗口，结束程序请按 Ctrl+C。
echo.

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:5188"

".venv\Scripts\python.exe" -m src.web

if errorlevel 1 goto web_failed

endlocal
exit /b 0

:project_missing
echo [错误] 项目文件不完整。
echo 请确认已完整解压 ZIP，并且当前目录包含：
echo.
echo   src\web.py
echo   requirements.txt
echo.
pause
exit /b 1

:python_missing
echo [错误] 未检测到 Python。
echo.
echo 请安装 Python 3.12，并勾选：
echo Add Python to PATH
echo.
pause
exit /b 1

:python_version_error
echo [错误] Python 版本过低。
echo 请安装 Python 3.12。
echo.
pause
exit /b 1

:venv_failed
echo [错误] Python 虚拟环境创建失败。
echo.
echo 请删除项目目录中的 .venv 文件夹后重试。
echo 若仍然失败，请在终端运行：
echo python -m venv .venv
echo.
pause
exit /b 1

:dependencies_failed
echo [错误] 项目依赖安装失败。
echo 请检查网络、代理和 requirements.txt。
echo.
pause
exit /b 1

:venv_version_error
echo [错误] 现有 .venv 不是 Python 3.12 环境。
echo 请删除项目目录中的 .venv 文件夹，然后重新双击 start_web.bat。
echo.
pause
exit /b 1

:data_dir_failed
echo [错误] Viewledge 数据目录不可写。
echo 请确认当前 Windows 用户有权创建和写入个人数据目录，
echo 或设置 VIEWLEDGE_OUTPUT_ROOT 为可写目录后重试。
echo.
pause
exit /b 1

:port_in_use
echo [错误] 端口 5188 已被占用。
echo 请关闭旧的 Viewledge 窗口或占用该端口的程序后重试。
echo.
pause
exit /b 1

:web_failed
echo.
echo [错误] Web UI 启动失败。
echo 请保留上方错误信息用于反馈。
echo.
pause
exit /b 1
