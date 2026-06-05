@echo off
cd /d "%~dp0"
echo Starting WAL Contest Logger...
python wal_logger.py
pause
