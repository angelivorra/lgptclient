#!/bin/bash
# ROBOTRACKER2 — clon de la interfaz LGPT (Kivy/SDL2).
# Se instala como "port" de EmulationStation en la Odin 2 (ROCKNIX).
source /etc/profile

set_kill set "robotracker2.py"

GAMEDIR=/storage/robotracker2
# Reutiliza el venv de robotracker (mismas dependencias: kivy/numpy/sound*).
VENV=/storage/robotracker-venv

# Entrada: en ROCKNIX, InputPlumber (gestor de entrada del sistema) agarra el
# mando AYN integrado y lo oculta a SDL, así que el joystick nativo de Kivy
# no ve nada. Toda la entrada (cruceta, sticks, botones, gatillos) llega
# traducida en un DualSense VIRTUAL (uhid) que InputPlumber expone; con el
# perfil por defecto su teclado virtual no emite nada.
#
# ROBOTRACKER2_EVDEV_GAMEPAD=1 hace que la app lea ese DualSense virtual por
# evdev crudo (evdev_triggers.py: hat=cruceta, ejes=stick/gatillos,
# BTN_*=botones) y desactive el joystick nativo (con el mando oculto no hay
# nada que ver y, si algún día SDL viera el DualSense virtual, duplicaría la
# entrada). Sin gptokeyb: con el mando oculto a SDL no reconocería ningún
# gamecontroller (depende de la db de mapeos).
export ROBOTRACKER2_EVDEV_GAMEPAD=1

# Pantalla 1920x1080 de 7": densidad x2 (toda la UI usa dp).
export KIVY_METRICS_DENSITY=2

# La app abre ventana X11 (XWayland) titulada ROBOTRACKER2: fullscreen en Sway.
# El helper del sistema (sway_fullscreen, en /etc/profile.d/001-functions)
# solo reintenta 5 veces a 1s cada una (5s) antes de rendirse — insuficiente
# aquí: Kivy usa GL vía zink/Vulkan (Turnip) en este hardware y tarda más de
# 5s en crear la ventana, así que se queda sin pantalla completa (ventana
# 1280x720 detrás de EmulationStation, parece que "no hace nada"). Se lanza
# igual por compatibilidad, más un reintento propio de respaldo, mucho más
# paciente (hasta 40s), que sigue intentándolo si el del sistema ya se rindió.
sway_fullscreen "ROBOTRACKER2" title &
(
    for _ in $(seq 1 40); do
        swaymsg '[title="ROBOTRACKER2"] fullscreen enable' >/dev/null 2>&1 && break
        sleep 1
    done
) &

cd "$GAMEDIR"
# Biblioteca de samples, images/ (eventos de pantalla) y sus miniaturas ya
# renderizadas (ayuda_imagenes/) de la Odin.
"$VENV/bin/python3" "$GAMEDIR/robotracker2.py" --fullscreen \
    --samples /storage/samples --images /storage/images \
    --ayuda /storage/ayuda_imagenes
