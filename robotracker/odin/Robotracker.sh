#!/bin/bash
# ROBOTRACKER - editor/reproductor tactil de canciones LGPT (Kivy/SDL2).
# Se instala como "port" de EmulationStation en la Odin 2 (ROCKNIX).
source /etc/profile

set_kill set "robotracker.py"

GAMEDIR=/storage/robotracker
VENV=/storage/robotracker-venv

# Gamepad -> teclas (mapeo en robotracker.gptk)
/usr/bin/gptokeyb -c "$GAMEDIR/robotracker.gptk" &
GPTK_PID=$!
trap "kill $GPTK_PID 2>/dev/null" EXIT INT TERM

# La pantalla de la Odin es 1920x1080 pero de 7": forzamos densidad x2
# (toda la UI usa dp, así que escala entera: ~4 pistas visibles).
export KIVY_METRICS_DENSITY=2

# La app abre ventana X11 (XWayland) titulada ROBOTRACKER: fullscreen en Sway
sway_fullscreen "ROBOTRACKER" title &

cd "$GAMEDIR"
"$VENV/bin/python3" "$GAMEDIR/robotracker.py"
