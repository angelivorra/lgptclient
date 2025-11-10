#!/bin/bash
# Wrapper para arrancar Robotraca en el terminal actual

cd /home/angel/lgptclient/bin/launcher

# Verificar que estamos en un terminal real
if [ ! -t 0 ]; then
    echo "Error: Este script debe ejecutarse en un terminal interactivo"
    exit 1
fi

# Ejecutar con sudo si no somos root
if [ "$EUID" -ne 0 ]; then
    exec sudo /home/angel/lgptclient/venv/bin/python run-lgpt.py
else
    exec /home/angel/lgptclient/venv/bin/python run-lgpt.py
fi
