@echo off
rem Double-click: radar scan, labels for new strong items (Sonnet 5.5), "what changed" report.
rem Keys come from live\.env. Report: live\out\update\latest.md
cd /d "%~dp0.."
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1
python -I -X utf8 live\update_now.py %*
echo.
echo Report: live\out\update\latest.md
pause
