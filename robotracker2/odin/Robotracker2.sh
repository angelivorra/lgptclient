#!/bin/bash
# ROBOTRACKER2 — clon de la interfaz LGPT (Kivy/SDL2).
# Se instala como "port" de EmulationStation en la Odin 2 (ROCKNIX).
source /etc/profile

set_kill set "robotracker2.py"

GAMEDIR=/storage/robotracker2
# Reutiliza el venv de robotracker (mismas dependencias: kivy/numpy/sound*).
VENV=/storage/robotracker-venv

# Gamepad -> teclas (mapeo en robotracker2.gptk)
/usr/bin/gptokeyb -c "$GAMEDIR/robotracker2.gptk" &
GPTK_PID=$!
trap "kill $GPTK_PID 2>/dev/null" EXIT INT TERM

# Pantalla 1920x1080 de 7": densidad x2 (toda la UI usa dp).
export KIVY_METRICS_DENSITY=2

# La app abre ventana X11 (XWayland) titulada ROBOTRACKER2: fullscreen en Sway.
sway_fullscreen "ROBOTRACKER2" title &

cd "$GAMEDIR"
# Biblioteca de samples e images/ (eventos de pantalla) de la Odin.
"$VENV/bin/python3" "$GAMEDIR/robotracker2.py" --fullscreen \
    --samples /storage/samples --images /storage/images
