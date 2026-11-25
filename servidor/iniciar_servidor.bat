@echo off
cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 goto usar_python
set "PYTHON_CMD=py"
goto python_encontrado

:usar_python
set "PYTHON_CMD=python"

:python_encontrado
if not exist .env (
  copy .env.example .env >nul
  echo O arquivo .env foi criado.
  echo Coloque token, CHAT_ID, nome e senha do Wi-Fi; depois salve e feche.
  start /wait notepad .env
)

echo Instalando ou conferindo os componentes do servidor...
%PYTHON_CMD% -m pip install -r requirements.txt

if errorlevel 1 (
  echo.
  echo Nao foi possivel preparar o Python.
  echo Instale o Python pelo site python.org e marque Add Python to PATH.
  pause
  exit /b 1
)

echo.
echo Gerando as credenciais do Arduino a partir do .env...
%PYTHON_CMD% preparar_arduino.py

if errorlevel 1 (
  echo Abra o .env e preencha todos os campos solicitados.
  start /wait notepad .env
  %PYTHON_CMD% preparar_arduino.py
)

if errorlevel 1 (
  echo Nao foi possivel gerar Credenciais.h.
  pause
  exit /b 1
)

echo.
echo Iniciando o servidor...
%PYTHON_CMD% servidor.py

echo.
echo O servidor foi encerrado.
pause
