@echo off
setlocal
cd /d "%~dp0"
echo PREPARACAO PRIVADA PARA A VPS - GRAND CHASE SEASON 2
echo.
echo Antes de continuar, encerra o jogo e os componentes pelo GCAdmin.
echo Mantem o SQL Server ligado e fecha o cliente GCAdmin durante a copia.
echo Executa este BAT como administrador.
echo.
pause
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Preparar-Migracao-VPS.ps1"
set "resultado=%errorlevel%"
echo.
if not "%resultado%"=="0" echo A preparacao falhou. Nao transfiras um pacote incompleto.
pause
exit /b %resultado%
