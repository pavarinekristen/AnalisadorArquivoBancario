@echo off
cd /d "%~dp0"
echo Instalando... (so precisa rodar uma vez)
python -m venv .venv || (echo Python nao encontrado. Instale em https://www.python.org/downloads/ marcando "Add to PATH". & pause & exit /b 1)
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
echo.
echo Pronto. Agora e so abrir o Conferir.bat
pause
