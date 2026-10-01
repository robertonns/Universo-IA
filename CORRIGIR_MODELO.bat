@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute INSTALAR.bat primeiro.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" preparar_modelo.py
if errorlevel 1 (
  echo Falha. Envie a mensagem exibida acima.
  pause
  exit /b 1
)
pause
