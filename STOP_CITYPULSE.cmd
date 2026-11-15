@echo off
REM Stops what START_CITYPULSE.cmd started (Ollama keeps running if it was already running before).
cd /d "%~dp0"
python -I -X utf8 live\engine_bridge\launcher.py stop
pause
