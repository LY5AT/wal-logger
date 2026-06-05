@echo off
cd /d "%~dp0"
title WAL Logger - diegimas
echo ============================================
echo   WAL Logger - priklausomybiu diegimas
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [!] Python nerastas.
  echo.
  echo     Idiek Python 3 is:  https://www.python.org/downloads/
  echo     SVARBU: diegiant pazymek  "Add Python to PATH"
  echo     arba paleisk:  winget install Python.Python.3.12
  echo.
  echo     Po idiegimo - paleisk si install.bat is naujo.
  echo.
  pause
  exit /b 1
)

python --version
echo.
echo Diegiu Python paketus ^(cryptography, aprslib^)...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo [!] Nepavyko idiegti paketu. Patikrink interneta ir bandyk dar karta.
  pause
  exit /b 1
)

echo.
echo [OK] Viskas idiegta.
echo     Loggeris:    "Start WAL Logger.bat"
echo     APRS zemelapis: "Start APRS Map.bat"
echo.
pause
