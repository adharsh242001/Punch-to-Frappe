@echo off
cd /d "%~dp0"
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" attendance_sync\server.py
) else (
    python attendance_sync\server.py
)
pause
