#!/usr/bin/env bash
# Ejecuta MIDI Monitor con el entorno virtual activo.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -d "venv" ]; then
    echo "Entorno virtual no encontrado. Ejecuta primero:"
    echo "  ./setup_env.sh"
    exit 1
fi

# shellcheck disable=SC1091
source venv/bin/activate
exec python3 main.py "$@"
