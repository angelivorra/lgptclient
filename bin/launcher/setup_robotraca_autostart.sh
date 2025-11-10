#!/bin/bash
# Script para configurar auto-arranque de Robotraca en tty1

set -e

echo "=== Configurando Auto-arranque de Robotraca ==="

# Crear/actualizar .bash_profile
echo "Configurando .bash_profile..."
cat << 'EOF' > /home/angel/.bash_profile
# Auto-arrancar Robotraca en tty1
if [ "$(tty)" = "/dev/tty1" ]; then
    echo "Iniciando Robotraca..."
    cd /home/angel/lgptclient/bin/launcher
    sudo /home/angel/lgptclient/venv/bin/python run-lgpt.py
    
    # Si Robotraca se cierra, reiniciar
    while true; do
        echo ""
        echo "Robotraca cerrado. ¿Reiniciar? (S/n)"
        read -t 10 -n 1 respuesta || respuesta="s"
        echo ""
        if [ "$respuesta" = "n" ] || [ "$respuesta" = "N" ]; then
            break
        fi
        sudo /home/angel/lgptclient/venv/bin/python run-lgpt.py
    done
fi
EOF

# Deshabilitar el servicio systemd (ya no lo necesitamos para la UI)
echo "Deshabilitando servicio systemd lgpt.service..."
sudo systemctl disable lgpt.service 2>/dev/null || true
sudo systemctl stop lgpt.service 2>/dev/null || true

echo ""
echo "=== Configuración completada ==="
echo ""
echo "Robotraca se iniciará automáticamente en tty1 después del login."
echo ""
echo "Para probarlo ahora:"
echo "  1. Sal de la sesión actual (logout)"
echo "  2. O cambia a tty1: sudo chvt 1"
echo "  3. O reinicia: sudo reboot"
echo ""
