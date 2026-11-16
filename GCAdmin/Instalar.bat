@echo off
setlocal
cd /d "%~dp0"
echo GCAdmin - Instalacao local com Python 3.12
py -3.12 -m venv .venv
if errorlevel 1 goto erro
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto erro
echo.
echo Instalacao concluida. Abre Iniciar-GCAdmin.bat.
pause
exit /b 0
:erro
echo.
echo Falha. Instala Python 3.12 x64 com o Python Launcher e tenta novamente.
pause
exit /b 1
