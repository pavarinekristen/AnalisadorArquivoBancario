@echo off
cd /d "%~dp0"
echo Instalando... (so precisa rodar uma vez)

python -c "import sys; sys.exit(sys.version_info < (3, 11))" 2>nul
if errorlevel 1 (
  echo Precisa do Python 3.11 ou mais novo. Instale em https://www.python.org/downloads/ marcando "Add to PATH".
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe python -m venv .venv || (echo Nao consegui criar o ambiente .venv & pause & exit /b 1)

rem Com a pasta wheels (instalador offline) nao precisa de internet.
if exist wheels\ (
  .venv\Scripts\python -m pip install --no-index --find-links wheels -r requirements.txt || goto erro
) else (
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt || goto erro
)

if not exist config\cliente.yaml (
  copy config\cliente.exemplo.yaml config\cliente.yaml >nul
  echo Criei config\cliente.yaml a partir do exemplo: preencha as pastas do cliente.
)

echo.
echo Pronto. Agora e so abrir o Conferir.bat
pause
exit /b 0

:erro
echo Falha ao instalar as dependencias.
pause
exit /b 1
