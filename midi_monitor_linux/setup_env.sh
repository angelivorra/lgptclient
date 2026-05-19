#!/usr/bin/env bash
# Crea el entorno virtual e instala las dependencias Python.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "=== MIDI Monitor Linux/Kirigami — setup ==="

# Verificar dependencias del sistema para compilar python-rtmidi
if ! dpkg -l libasound2-dev &>/dev/null 2>&1; then
    echo "AVISO: libasound2-dev no encontrado."
    echo "  sudo apt install libasound2-dev libjack-dev"
    echo "Abortando."
    exit 1
fi

# Verificar Python 3.10+
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 no encontrado."
    exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python: $PY_VER"

# Crear entorno virtual si no existe
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Entorno virtual creado en ./venv"
fi

# Activar e instalar
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt

echo ""
echo "=== Dependencias Python instaladas ==="
echo ""
echo "IMPORTANTE: Kirigami es una librería del sistema (no está en PyPI)."
echo "Instálala con el gestor de paquetes de tu distribución:"
echo ""
echo "  Ubuntu/Debian 24.04+:  sudo apt install qml6-module-org-kde-kirigami"
echo "  Arch Linux:            sudo pacman -S kirigami"
echo "  Fedora:                sudo dnf install kf6-kirigami"
echo "  openSUSE:              sudo zypper install kirigami2"
echo ""
echo "Para ejecutar la aplicación:"
echo "  ./run.sh"
