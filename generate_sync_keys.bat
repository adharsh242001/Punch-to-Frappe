@echo off
cd /d "%~dp0"
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" generate_sync_keys.py
) else (
    python generate_sync_keys.py
)
pause
