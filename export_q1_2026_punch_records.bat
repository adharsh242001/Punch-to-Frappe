@echo off
cd /d "%~dp0"
python export_punch_records.py --start 2026-01-01 --end 2026-03-31 --output data\punch_records_2026-01-01_to_2026-03-31.csv
pause
