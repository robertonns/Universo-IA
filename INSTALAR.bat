@echo off
cd /d "%~dp0"
if /I "%~1"=="AUTO" set "UNIVERSO_AUTO=1"
echo UNIVERSO LOCAL - instalacao inicial com internet
py -3 --version >nul 2>&1
if errorlevel 1 (
  echo Instale Python 3.11 ou 3.12 x64 em https://www.python.org/downloads/windows/
  echo Inclua o Python Launcher na instalacao. Depois execute este arquivo novamente.
  if not defined UNIVERSO_AUTO pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if errorlevel 1 goto falha
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto falha
echo Interface pronta. Para ver a demonstracao, execute INICIAR_APP.bat.
echo Baixando agora o modelo e o executor CPU oficiais. Aguarde.
".venv\Scripts\python.exe" preparar_modelo.py
if errorlevel 1 goto falha
if not defined UNIVERSO_AUTO pause
exit /b 0
:falha
echo A instalacao encontrou um erro. Leia a mensagem acima e consulte LEIA-ME.md.
if not defined UNIVERSO_AUTO pause
exit /b 1
