#!/usr/bin/env bash
# Ejecuta TCP Monitor con el entorno virtual activo.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -d "venv" ]; then
    echo "Creando entorno virtual..."
    python3 -m venv venv
fi

echo "Instalando/actualizando dependencias..."
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q -r requirements.txt

source venv/bin/activate
exec python3 main.py "$@"
