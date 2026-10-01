@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto instalar
if not exist "models\qwen2.5-0.5b-instruct-q4_k_m.gguf" goto instalar
goto verificar
:instalar
echo Preparando o modelo local pela primeira vez. Isso pode levar alguns minutos.
call "%~dp0INSTALAR.bat" AUTO
if errorlevel 1 (
  echo Nao foi possivel concluir a preparacao. Veja a mensagem acima.
  pause
  exit /b 1
)
:verificar
echo Verificando o modelo local...
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8081/health -TimeoutSec 1).StatusCode -eq 200 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
  echo Iniciando o modelo CPU automaticamente...
  start "Universo IA - Modelo local" /min cmd /c call "%~dp0INICIAR_MODELO.bat"
  set "UNIVERSO_READY="
  for /L %%I in (1,1,25) do (
    powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8081/health -TimeoutSec 1).StatusCode -eq 200 } catch { exit 1 }" >nul 2>&1
    if not errorlevel 1 set "UNIVERSO_READY=1"
    if defined UNIVERSO_READY goto modelo_pronto
    timeout /t 1 /nobreak >nul
  )
  echo O modelo demorou mais que o esperado para iniciar. Veja a janela minimizada do modelo.
)
:modelo_pronto
echo Abra http://127.0.0.1:8765 no navegador. Mantenha esta janela aberta.
start "" "http://127.0.0.1:8765"
".venv\Scripts\python.exe" server.py
pause
