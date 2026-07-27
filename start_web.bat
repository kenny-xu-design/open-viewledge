@echo off
chcp 65001 >nul
setlocal EnableExtensions

title Video Summary Skill Web UI
cd /d "%~dp0"

echo.
echo ==========================================
echo   Video Summary Skill Web UI
echo ==========================================
echo 项目目录：%CD%
echo.

if not exist "src\web.py" goto project_missing
if not exist "requirements.txt" goto project_missing

if exist ".venv\Scripts\python.exe" goto install_dependencies

echo [1/4] 正在检测 Python...

where py >nul 2>&1
if not errorlevel 1 goto try_py312

where python >nul 2>&1
if not errorlevel 1 goto use_python

goto python_missing

:try_py312
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 goto use_py312

py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 goto use_py3

where python >nul 2>&1
if not errorlevel 1 goto use_python

goto python_missing

:use_py312
echo [2/4] 正在创建 Python 3.12 虚拟环境...
py -3.12 -m venv ".venv"
goto check_venv

:use_py3
echo [2/4] 正在创建 Python 虚拟环境...
py -3 -m venv ".venv"
goto check_venv

:use_python
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 goto python_version_error

echo [2/4] 正在创建 Python 虚拟环境...
python -m venv ".venv"
goto check_venv

:check_venv
if errorlevel 1 goto venv_failed
if not exist ".venv\Scripts\python.exe" goto venv_failed

:install_dependencies
echo [3/4] 正在检查项目依赖...
echo 首次运行可能需要几分钟，请保持网络连接。
echo.

".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "requirements.txt"

if errorlevel 1 goto dependencies_failed

echo.
where ffmpeg >nul 2>&1
if not errorlevel 1 goto launch_web

if exist "ffmpeg\bin\ffmpeg.exe" (
    set "PATH=%CD%\ffmpeg\bin;%PATH%"
    goto launch_web
)

if exist "tools\ffmpeg\bin\ffmpeg.exe" (
    set "PATH=%CD%\tools\ffmpeg\bin;%PATH%"
    goto launch_web
)

echo [提示] 未检测到 FFmpeg。
echo 本地视频、无字幕视频和关键帧功能可能无法使用。
echo 可运行：winget install Gyan.FFmpeg
echo.

:launch_web
set "VENV_SITE_PACKAGES=%CD%\.venv\Lib\site-packages"

if exist "%VENV_SITE_PACKAGES%\nvidia\cublas\bin\cublas64_12.dll" (
    set "PATH=%VENV_SITE_PACKAGES%\nvidia\cublas\bin;%PATH%"
)

if exist "%VENV_SITE_PACKAGES%\nvidia\cudnn\bin\cudnn64_9.dll" (
    set "PATH=%VENV_SITE_PACKAGES%\nvidia\cudnn\bin;%PATH%"
)

if exist "%VENV_SITE_PACKAGES%\ctranslate2" (
    set "PATH=%VENV_SITE_PACKAGES%\ctranslate2;%PATH%"
)

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

:web_failed
echo.
echo [错误] Web UI 启动失败。
echo 请保留上方错误信息用于反馈。
echo.
pause
exit /b 1
