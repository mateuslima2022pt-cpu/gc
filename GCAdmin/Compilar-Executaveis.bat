@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Executa Instalar.bat primeiro.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto erro
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed --name GCAdmin --add-data "web;web" --collect-all webview client_main.py
if errorlevel 1 goto erro
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --console --name GCAdmin-Agent agent_main.py
if errorlevel 1 goto erro
echo.
echo Pastas criadas em dist\GCAdmin e dist\GCAdmin-Agent.
echo Distribui a pasta inteira de cada programa, nao apenas o EXE.
pause
exit /b 0
:erro
echo Compilacao falhou. Consulta as mensagens acima.
pause
exit /b 1
