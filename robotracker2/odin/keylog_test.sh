#!/bin/bash
# keylog_test.sh — depura el mando en la Odin: para robotracker2, lanza
# gptokeyb con el mapeo real y un keylogger que registra TODO lo que llega.
#
#   keylog_test.sh
#
# El keylogger escribe en /storage/robotracker2/keylog.txt; después:
#   ./keylog_test.sh stop    -> para gptokeyb y el keylogger
source /etc/profile

GAMEDIR=/storage/robotracker2
LOG=/storage/robotracker2/keylog.txt
VENV_PY=/storage/robotracker-venv/bin/python3

case "${1:-run}" in
  stop)
    pkill -9 -f "keylog.py" 2>/dev/null
    pkill -9 gptokeyb 2>/dev/null
    echo "Parado."
    exit 0
    ;;
esac

# para robotracker2/gptokeyb/keylog previos
pkill -9 -f "robotracker2.py" 2>/dev/null
pkill -9 -f "keylog.py" 2>/dev/null
pkill -9 gptokeyb 2>/dev/null
sleep 1
rm -f "$LOG"

# gptokeyb con el mapeo real de robotracker2 (L2=leftctrl, R2=rightctrl...)
# Desacoplado con setsid: el wrapper sale al lanzar y no debe matarlo.
export SDL_GAMECONTROLLERCONFIG_FILE="$GAMEDIR/gamecontrollerdb.txt"
setsid /usr/bin/gptokeyb -c "$GAMEDIR/robotracker2.gptk" >/dev/null 2>&1 &

export KIVY_METRICS_DENSITY=2
cd "$GAMEDIR"

setsid "$VENV_PY" "$GAMEDIR/keylog.py" --fullscreen \
    > /tmp/keylog_app.log 2>&1 &
APP_PID=$!

# fullscreen del keylogger en Sway (como hace Robotracker2.sh)
(
    for _ in $(seq 1 40); do
        swaymsg '[title="KEYLOG"] fullscreen enable' >/dev/null 2>&1 && break
        sleep 1
    done
) &

echo "Keylog lanzado (app PID $APP_PID, gptokeyb lanzado con setsid)."
echo "Pulsa L2 / R2 / dpad / A / B / Start. Log: $LOG"
