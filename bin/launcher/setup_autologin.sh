#!/bin/bash
# Script para configurar auto-login y arranque automático de Robotraca

set -e

echo "=== Configurando Auto-login para Robotraca ==="

# 1. Configurar getty para auto-login
echo "1. Configurando getty autologin..."
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d/
cat << 'EOF' | sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin angel --noclear %I $TERM
EOF

# 2. Crear script de arranque en el perfil del usuario
echo "2. Configurando .bash_profile..."
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

# 3. Dar permisos sudo sin password para el script
echo "3. Configurando sudo sin password para el script..."
cat << 'EOF' | sudo tee /etc/sudoers.d/robotraca
angel ALL=(ALL) NOPASSWD: /home/angel/lgptclient/venv/bin/python /home/angel/lgptclient/bin/launcher/run-lgpt.py
EOF
sudo chmod 0440 /etc/sudoers.d/robotraca

# 4. Deshabilitar el servicio systemd (ya no lo necesitamos)
echo "4. Deshabilitando servicio systemd..."
sudo systemctl disable lgpt.service || true
sudo systemctl stop lgpt.service || true

echo ""
echo "=== Configuración completada ==="
echo ""
echo "Para activar los cambios:"
echo "  sudo systemctl daemon-reload"
echo "  sudo reboot"
echo ""
echo "Después del reinicio, el sistema arrancará directamente en Robotraca."
echo ""
