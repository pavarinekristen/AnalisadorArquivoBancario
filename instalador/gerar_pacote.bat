@echo off
rem Roda na maquina de build (com internet). Gera instalador\pacote\ pronto para o Inno Setup:
rem   - wheels\  : todas as dependencias (instalacao sem internet no cliente)
rem   - python\  : Python embutido (o cliente nao precisa ter Python)
cd /d "%~dp0\.."
set VERSAO_PY=3.12.10

if exist instalador\pacote rmdir /s /q instalador\pacote
mkdir instalador\pacote\wheels

.venv\Scripts\python -m pip download -r requirements.txt -d instalador\pacote\wheels --only-binary=:all: --platform win_amd64 --python-version 3.12 || goto erro

powershell -NoProfile -Command "Invoke-WebRequest https://www.python.org/ftp/python/%VERSAO_PY%/python-%VERSAO_PY%-embed-amd64.zip -OutFile instalador\pacote\python.zip" || goto erro
powershell -NoProfile -Command "Expand-Archive instalador\pacote\python.zip instalador\pacote\python; Remove-Item instalador\pacote\python.zip" || goto erro
rem O Python embutido vem sem site-packages: libera o import site e instala o pip.
powershell -NoProfile -Command "(Get-Content instalador\pacote\python\python312._pth) -replace '#import site','import site' | Set-Content instalador\pacote\python\python312._pth"
powershell -NoProfile -Command "Invoke-WebRequest https://bootstrap.pypa.io/get-pip.py -OutFile instalador\pacote\get-pip.py" || goto erro

echo Pacote pronto em instalador\pacote. Agora compile instalador\setup.iss no Inno Setup.
exit /b 0

:erro
echo Falha ao gerar o pacote.
exit /b 1
