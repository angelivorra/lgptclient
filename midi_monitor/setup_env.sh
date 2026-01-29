#!/bin/bash
# Script para configurar el entorno virtual en Linux

echo "========================================"
echo " MIDI Monitor - Configuración Linux"
echo "========================================"
echo

# Verificar si Python está instalado
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 no está instalado"
    echo "Instala Python con: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

# Verificar dependencias del sistema para rtmidi
echo "[0/4] Verificando dependencias del sistema..."
if command -v apt &> /dev/null; then
    # Debian/Ubuntu
    if ! dpkg -l | grep -q libasound2-dev; then
        echo "     Instalando libasound2-dev (necesario para rtmidi)..."
        sudo apt install -y libasound2-dev libjack-jackd2-dev
    fi
elif command -v dnf &> /dev/null; then
    # Fedora
    sudo dnf install -y alsa-lib-devel jack-audio-connection-kit-devel
elif command -v pacman &> /dev/null; then
    # Arch
    sudo pacman -S --noconfirm alsa-lib jack
fi

echo "[1/4] Creando entorno virtual..."
if [ -d "venv" ]; then
    echo "     El entorno virtual ya existe, saltando..."
else
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "ERROR: No se pudo crear el entorno virtual"
        echo "Instala venv con: sudo apt install python3-venv"
        exit 1
    fi
fi

echo "[2/4] Activando entorno virtual..."
source venv/bin/activate

echo "[3/4] Actualizando pip..."
pip install --upgrade pip

echo "[4/4] Instalando dependencias..."
pip install -r requirements.txt

echo
echo "========================================"
echo " Configuración completada!"
echo "========================================"
echo
echo "Para ejecutar la aplicación:"
echo "  1. Activa el entorno: source venv/bin/activate"
echo "  2. Ejecuta: python main.py"
echo
echo "El puerto MIDI virtual se creará automáticamente en Linux (ALSA)"
echo
