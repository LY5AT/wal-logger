@echo off
cd /d "%~dp0"
where python >nul 2>nul || (echo Python nerastas - paleisk install.bat & pause & exit /b 1)
rem first-run: auto-install deps if missing
python -c "import cryptography" >nul 2>nul || (echo Diegiu priklausomybes pirma karta... & python -m pip install -r requirements.txt)
echo Starting WAL Contest Logger...
python wal_logger.py
pause
