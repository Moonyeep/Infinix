@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
if not exist bridge.py (
  echo Erro: extraia o ZIP inteiro antes de executar este arquivo.
  pause
  exit /b 1
)
set "ZS_AGENT_ENABLED=1"
set "ZS_ROBLOX_ENABLED=0"
set "ZS_AGENT_WORKSPACE=%~dp0"
set "ZS_AGENT_WORKSPACE_ROOTS=%~dp0;%USERPROFILE%\Downloads;%USERPROFILE%\Desktop;%USERPROFILE%\Documents"
set "ZS_BRIDGE_PORT=17613"
echo Infinix Agent iniciado.
echo Mantenha esta janela aberta.
set "PYTHON_EXE="
set "PYTHON_ARGS="

rem Use an explicitly configured interpreter first, then common Windows commands.
if defined ZS_PYTHON call :try_python "%ZS_PYTHON%"
if not defined PYTHON_EXE call :try_python py -3
if not defined PYTHON_EXE call :try_python python
if not defined PYTHON_EXE call :try_python python3

rem Also check standard per-user and machine-wide Python install folders.
if not defined PYTHON_EXE for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%~fD\python.exe" if not defined PYTHON_EXE call :try_python "%%~fD\python.exe"
if not defined PYTHON_EXE for /d %%D in ("%ProgramFiles%\Python3*") do if exist "%%~fD\python.exe" if not defined PYTHON_EXE call :try_python "%%~fD\python.exe"
if not defined PYTHON_EXE for /d %%D in ("%ProgramFiles(x86)%\Python3*") do if exist "%%~fD\python.exe" if not defined PYTHON_EXE call :try_python "%%~fD\python.exe"

if not defined PYTHON_EXE goto offer_python_install

goto verify_python_version

:offer_python_install
echo.
echo Python 3.9 ou mais recente nao foi encontrado.
where winget >nul 2>nul
if errorlevel 1 goto manual_python_install
echo O winget esta disponivel para instalar Python 3.13 apenas para este usuario.
choice /C SN /M "Deseja instalar Python agora? (S/N)"
if errorlevel 2 goto manual_python_install
winget install --id Python.Python.3.13 --exact --scope user --accept-source-agreements --accept-package-agreements
if errorlevel 1 goto manual_python_install
if not defined PYTHON_EXE call :try_python py -3
if not defined PYTHON_EXE call :try_python "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PYTHON_EXE goto manual_python_install

goto verify_python_version

:verify_python_version
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if errorlevel 1 goto python_too_old
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import websockets" >nul 2>nul
if errorlevel 1 (
  echo Instalando a dependencia websockets...
  "%PYTHON_EXE%" %PYTHON_ARGS% -m pip --version >nul 2>nul
  if errorlevel 1 "%PYTHON_EXE%" %PYTHON_ARGS% -m ensurepip --user >nul 2>nul
  "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install --user --disable-pip-version-check websockets
  if errorlevel 1 goto dependency_install_failed
)
echo Usando Python:
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import sys; print(sys.executable)"
echo.
:run_bridge
set "BRIDGE_RESTARTS=0"
set "BRIDGE_DELAY=2"
:bridge_attempt
echo Iniciando bridge...
"%PYTHON_EXE%" %PYTHON_ARGS% bridge.py
set "BRIDGE_EXIT=%ERRORLEVEL%"
if "%BRIDGE_EXIT%"=="0" goto bridge_stopped
set /a BRIDGE_RESTARTS+=1
if %BRIDGE_RESTARTS% GEQ 8 goto bridge_restart_failed
echo.
echo O bridge encerrou com codigo %BRIDGE_EXIT%. Nova tentativa %BRIDGE_RESTARTS% de 8 em %BRIDGE_DELAY% segundos...
timeout /t %BRIDGE_DELAY% >nul
set /a BRIDGE_DELAY*=2
if %BRIDGE_DELAY% GTR 30 set "BRIDGE_DELAY=30"
goto bridge_attempt

:bridge_stopped
echo.
echo Bridge encerrado normalmente.
pause
exit /b 0

:bridge_restart_failed
echo.
echo O bridge falhou 8 vezes; o reinicio automatico foi interrompido para evitar um loop infinito.
echo Consulte logs\bridge_debug.log e corrija a causa antes de iniciar novamente.
pause
exit /b %BRIDGE_EXIT%

:try_python
set "TEST_EXE=%~1"
set "TEST_ARGS=%~2"
if not defined TEST_EXE exit /b 0
if /i "%TEST_EXE%"=="py" (
  where py >nul 2>nul
  if errorlevel 1 exit /b 0
)
"%TEST_EXE%" %TEST_ARGS% -c "import sys" >nul 2>nul
if errorlevel 1 exit /b 0
set "PYTHON_EXE=%TEST_EXE%"
set "PYTHON_ARGS=%TEST_ARGS%"
exit /b 0

:python_too_old
echo Erro: foi encontrado Python, mas a versao e anterior a 3.9.
echo Instale Python 3.9 ou mais recente e execute este launcher novamente.
pause
exit /b 1

:dependency_install_failed
echo Erro: nao foi possivel instalar a dependencia websockets.
echo Tente manualmente: "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install --user websockets
pause
exit /b 1

:manual_python_install
echo.
echo Python nao esta disponivel. Instale Python 3.9 ou mais recente em:
echo https://www.python.org/downloads/windows/
echo Durante a instalacao, marque Add python.exe to PATH. Depois execute este arquivo novamente.
pause
exit /b 1
