@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Executa Instalar.bat primeiro.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" client_main.py --browser
if errorlevel 1 pause
