@echo off
chcp 65001 >nul
setlocal EnableExtensions

title Video Summary Skill Web UI

rem ==================================================
rem 以 start_web.bat 所在目录作为项目根目录
rem 不依赖 Git、.git、固定盘符或开发者本地路径
rem ==================================================

pushd "%~dp0"

set "PROJECT_ROOT=%CD%"
set "VENV_DIR=%PROJECT_ROOT%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "REQUIREMENTS=%PROJECT_ROOT%\requirements.txt"
set "INSTALL_MARK=%VENV_DIR%\.dependencies_installed"

echo.
echo ==========================================
echo   Video Summary Skill Web UI
echo ==========================================
echo 项目目录：%PROJECT_ROOT%
echo.

rem ==================================================
rem 检查项目文件
rem ==================================================

if not exist "%PROJECT_ROOT%\src\web.py" (
    echo [错误] 项目文件不完整。
    echo 未找到：src\web.py
    echo.
    echo 请完整解压 ZIP 后，再运行 start_web.bat。
    echo 不要直接在压缩包预览窗口中运行。
    echo.
    pause
    popd
    exit /b 1
)

if not exist "%REQUIREMENTS%" (
    echo [错误] 项目文件不完整。
    echo 未找到：requirements.txt
    echo.
    echo 请重新下载并完整解压 ZIP。
    echo.
    pause
    popd
    exit /b 1
)

rem ==================================================
rem 查找 Python
rem ==================================================

if not exist "%VENV_PYTHON%" (
    echo [1/4] 正在检测 Python...

    set "PYTHON_CMD="

    where py >nul 2>&1
    if not errorlevel 1 (
        py -3.12 -c "import sys" >nul 2>&1
        if not errorlevel 1 (
            set "PYTHON_CMD=py -3.12"
        )
    )

    if not defined PYTHON_CMD (
        where py >nul 2>&1
        if not errorlevel 1 (
            py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
            if not errorlevel 1 (
                set "PYTHON_CMD=py -3"
            )
        )
    )

    if not defined PYTHON_CMD (
        where python >nul 2>&1
        if not errorlevel 1 (
            python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
            if not errorlevel 1 (
                set "PYTHON_CMD=python"
            )
        )
    )

    if not defined PYTHON_CMD (
        echo.
        echo [错误] 未检测到可用的 Python。
        echo.
        echo 请安装 Python 3.12：
        echo https://www.python.org/downloads/
        echo.
        echo 安装时请勾选：
        echo Add Python to PATH
        echo.
        echo 安装完成后，重新双击 start_web.bat。
        echo.
        pause
        popd
        exit /b 1
    )

    echo [2/4] 正在创建项目运行环境...
    call %PYTHON_CMD% -m venv "%VENV_DIR%"

    if errorlevel 1 (
        echo.
        echo [错误] Python 虚拟环境创建失败。
        echo 请确认 Python 安装完整，并重新运行。
        echo.
        pause
        popd
        exit /b 1
    )
)

rem ==================================================
rem 安装依赖
rem ==================================================

if not exist "%INSTALL_MARK%" (
    echo [3/4] 首次运行，正在安装项目依赖...
    echo 这可能需要几分钟，请保持网络连接。
    echo.

    "%VENV_PYTHON%" -m pip install ^
        --disable-pip-version-check ^
        --upgrade pip

    if errorlevel 1 (
        echo.
        echo [错误] pip 更新失败。
        echo 请检查网络、代理或防火墙设置。
        echo.
        pause
        popd
        exit /b 1
    )

    "%VENV_PYTHON%" -m pip install ^
        --disable-pip-version-check ^
        -r "%REQUIREMENTS%"

    if errorlevel 1 (
        echo.
        echo [错误] 项目依赖安装失败。
        echo 请保留上方错误信息并反馈。
        echo.
        pause
        popd
        exit /b 1
    )

    >"%INSTALL_MARK%" echo installed
)

rem ==================================================
rem 检测 FFmpeg
rem ==================================================

where ffmpeg >nul 2>&1

if errorlevel 1 (
    if exist "%PROJECT_ROOT%\ffmpeg\bin\ffmpeg.exe" (
        set "PATH=%PROJECT_ROOT%\ffmpeg\bin;%PATH%"
    ) else if exist "%PROJECT_ROOT%\tools\ffmpeg\bin\ffmpeg.exe" (
        set "PATH=%PROJECT_ROOT%\tools\ffmpeg\bin;%PATH%"
    ) else (
        echo.
        echo [提示] 当前没有检测到 FFmpeg。
        echo.
        echo 带平台字幕的视频仍可能正常使用，
        echo 本地视频或无字幕视频可能无法处理。
        echo.
        echo 可通过以下命令安装：
        echo winget install Gyan.FFmpeg
        echo.
    )
)

rem ==================================================
rem 启动 Web UI
rem ==================================================

echo [4/4] 正在启动 Web UI...
echo.
echo 浏览器地址：
echo http://127.0.0.1:5188
echo.
echo 请不要关闭此窗口。
echo 结束程序时，请按 Ctrl+C。
echo.

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem 延迟打开浏览器
start "" powershell.exe -NoProfile -WindowStyle Hidden -Command ^
    "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:5188'"

"%VENV_PYTHON%" -m src.web

set "EXIT_CODE=%ERRORLEVEL%"

echo.

if not "%EXIT_CODE%"=="0" (
    echo [错误] Web UI 启动失败。
    echo 退出代码：%EXIT_CODE%
    echo.
    echo 请保留上方错误信息用于反馈。
    echo.
    pause
)

popd
endlocal
exit /b %EXIT_CODE%
