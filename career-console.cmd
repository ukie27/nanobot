@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "CAREER_PYTHON=%PROJECT_ROOT%.venv\Scripts\python.exe"

if not exist "%CAREER_PYTHON%" (
  echo CareerConsole virtual environment was not found:
  echo %CAREER_PYTHON%
  exit /b 1
)

if "%~1"=="" (
  "%CAREER_PYTHON%" -m career_console start
) else (
  "%CAREER_PYTHON%" -m career_console %*
)
