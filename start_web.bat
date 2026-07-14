@echo off
cd /d "%~dp0"
.\.venv\Scripts\python.exe -m src.web --host 127.0.0.1 --port 5188
