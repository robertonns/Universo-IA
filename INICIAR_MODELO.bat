@echo off
cd /d "%~dp0"
set "UNIVERSO_EXE="
for /r "runtime" %%F in (llama-server.exe) do if exist "%%F" set "UNIVERSO_EXE=%%F"
if not defined UNIVERSO_EXE (
  echo Execute INSTALAR.bat primeiro. Nao foi encontrado llama-server.exe em runtime.
  pause
  exit /b 1
)
if not exist "models\qwen2.5-0.5b-instruct-q4_k_m.gguf" (
  echo Modelo ausente. Execute INSTALAR.bat novamente.
  pause
  exit /b 1
)
echo Modelo CPU - mantenha esta janela aberta. Ctrl+C para encerrar.
"%UNIVERSO_EXE%" -m "models\qwen2.5-0.5b-instruct-q4_k_m.gguf" --host 127.0.0.1 --port 8081 -ngl 0 -t 2 -c 2048 -np 1
pause
