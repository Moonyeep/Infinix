@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist bridge.py (
  echo Erro: extraia o ZIP inteiro antes de executar este arquivo.
  pause
  exit /b 1
)
set "ZS_AGENT_ENABLED=1"
set "ZS_ROBLOX_ENABLED=1"
set "ZS_AGENT_WORKSPACE=%~dp0"
set "ZS_BRIDGE_PORT=17613"
echo Infinix iniciado no modo opcional Roblox Studio.
echo Mantenha esta janela aberta.
where py >nul 2>nul && set "PY=py -3"
if not defined PY set "PY=python"
%PY% -c "import websockets" >nul 2>nul
if errorlevel 1 %PY% -m pip install --user websockets
%PY% bridge.py
pause
