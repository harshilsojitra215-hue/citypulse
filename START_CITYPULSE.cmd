@echo off
REM Starts and warms everything CityPulse needs, hidden in the background (about 1 to 2 minutes).
REM Website http://127.0.0.1:8790/   Analyst console http://127.0.0.1:3000/emerging
cd /d "%~dp0"
python -I -X utf8 live\engine_bridge\launcher.py start
start "" http://127.0.0.1:8790/
pause
