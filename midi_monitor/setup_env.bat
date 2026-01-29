@echo off
REM Script para configurar el entorno virtual en Windows

echo ========================================
echo  MIDI Monitor - Configuracion Windows
echo ========================================
echo.

REM Verificar si Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no esta instalado o no esta en el PATH
    echo Descarga Python desde https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] Creando entorno virtual...
if exist venv (
    echo      El entorno virtual ya existe, saltando...
) else (
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: No se pudo crear el entorno virtual
        pause
        exit /b 1
    )
)

echo [2/4] Activando entorno virtual...
call venv\Scripts\activate.bat

echo [3/4] Actualizando pip...
python -m pip install --upgrade pip

echo [4/4] Instalando dependencias...
pip install -r requirements.txt

echo.
echo ========================================
echo  Configuracion completada!
echo ========================================
echo.
echo Para ejecutar la aplicacion:
echo   1. Activa el entorno: venv\Scripts\activate.bat
echo   2. Ejecuta: python main.py
echo.
echo NOTA: Para crear puertos MIDI virtuales en Windows,
echo       necesitas instalar loopMIDI:
echo       https://www.tobias-erichsen.de/software/loopmidi.html
echo.
pause
