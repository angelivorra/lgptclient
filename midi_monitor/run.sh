#!/bin/bash
# Script para ejecutar la aplicación en Linux

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "El entorno virtual no existe. Ejecuta setup_env.sh primero."
    exit 1
fi

source venv/bin/activate
python main.py
