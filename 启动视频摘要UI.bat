@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "REPO=E:\AGT\git\video-summary-skill"
set "EXPECTED_BRANCH=feat/v1.4-processing-pipeline"
set "WEB_HOST=127.0.0.1"
set "WEB_PORT=5191"

title Video Summary Skill Web UI

if not exist "%REPO%\.git" (
    echo [错误] 未找到 Git 仓库：
    echo %REPO%
    pause
    exit /b 2
)

if not exist "%REPO%\.venv\Scripts\python.exe" (
    echo [错误] 未找到项目虚拟环境：
    echo %REPO%\.venv\Scripts\python.exe
    pause
    exit /b 2
)

pushd "%REPO%" >nul
if errorlevel 1 (
    echo [错误] 无法进入项目目录：%REPO%
    pause
    exit /b 2
)

set "CURRENT_BRANCH="
for /f "delims=" %%B in ('git branch --show-current 2^>nul') do set "CURRENT_BRANCH=%%B"

if not defined CURRENT_BRANCH (
    echo [错误] 无法读取当前 Git 分支。
    popd
    pause
    exit /b 3
)

if /i not "%CURRENT_BRANCH%"=="%EXPECTED_BRANCH%" (
    echo [错误] 当前分支不是 Web 最新开发分支。
    echo 当前分支：%CURRENT_BRANCH%
    echo 目标分支：%EXPECTED_BRANCH%
    echo.
    echo 批处理不会自动切换分支，请先在 GitHub Desktop 中确认分支。
    popd
    pause
    exit /b 3
)

echo 仓库：%REPO%
echo 分支：%CURRENT_BRANCH%
echo 地址：http://%WEB_HOST%:%WEB_PORT%/

powershell.exe -NoProfile -Command "$client = New-Object Net.Sockets.TcpClient; try { $client.Connect('%WEB_HOST%', %WEB_PORT%); exit 1 } catch { exit 0 } finally { $client.Dispose() }"
if errorlevel 1 (
    echo.
    echo [错误] 端口 %WEB_PORT% 已被占用，可能已有视频摘要 Web 服务正在运行。
    echo 请先关闭旧服务，再重新双击此文件。
    popd
    pause
    exit /b 4
)

if /i "%~1"=="--check" (
    echo 启动检查通过。
    popd
    exit /b 0
)

echo.
echo 正在启动视频摘要 UI，关闭此窗口将停止 Web 服务。
echo.

".venv\Scripts\python.exe" -m src.web --host "%WEB_HOST%" --port "%WEB_PORT%" --open
set "WEB_EXIT_CODE=%ERRORLEVEL%"

popd

if not "%WEB_EXIT_CODE%"=="0" (
    echo.
    echo [错误] Web 服务启动失败，退出码：%WEB_EXIT_CODE%
    echo 如果提示端口被占用，请先关闭旧的视频摘要 Web 窗口。
    pause
)

exit /b %WEB_EXIT_CODE%
