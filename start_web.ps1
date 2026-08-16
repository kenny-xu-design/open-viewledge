Set-Location $PSScriptRoot
if (-not $env:VIEWLEDGE_OUTPUT_ROOT) { $env:VIEWLEDGE_OUTPUT_ROOT = Join-Path $env:LOCALAPPDATA "Viewledge\knowledge" }
if (-not $env:VIEWLEDGE_STATE_ROOT) { $env:VIEWLEDGE_STATE_ROOT = Join-Path $env:LOCALAPPDATA "Viewledge\state" }
& .\.venv\Scripts\python.exe -m src.web --host 127.0.0.1 --port 5188
