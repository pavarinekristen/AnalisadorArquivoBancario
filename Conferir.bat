@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\streamlit.exe (
  echo Rode primeiro o instalar.bat
  pause
  exit /b 1
)
.venv\Scripts\streamlit run app.py --server.headless false --browser.gatherUsageStats false
