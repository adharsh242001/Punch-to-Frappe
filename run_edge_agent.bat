@echo off
cd /d "%~dp0"
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" attendance_sync\edge_agent.py
) else (
    python attendance_sync\edge_agent.py
)
pause
