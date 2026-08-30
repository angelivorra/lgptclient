#!/usr/bin/env bash
# Ejecuta el sinte (reproductor standalone de canciones LGPT) con su entorno
# virtual. Crea sinte/.venv e instala las dependencias la primera vez.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -d ".venv" ]; then
    echo "Creando entorno virtual..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

exec .venv/bin/python lgpt_player.py --device default "$@"
