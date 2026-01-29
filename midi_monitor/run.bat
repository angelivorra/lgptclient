@echo off
REM Script para ejecutar la aplicación en Windows

cd /d "%~dp0"

if not exist venv (
    echo El entorno virtual no existe. Ejecuta setup_env.bat primero.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python main.py
