#!/bin/bash
# Arranca una sesión de ajuste del vocoder: para la producción (Carla
# headless gestionada por flask), deja sonando en bucle una señal de prueba
# (loop_signal.py) y te dice cómo abrir la GUI de Carla por SSH -X.
#
# Uso (en la Pi del vocoder, o por ssh): ./start-tuning.sh [args de loop_signal.py]
#   p.ej.: ./start-tuning.sh --wav /home/patch/pivocoder/test.wav --bpm 90
#
# Para volver a producción: ./stop-tuning.sh
set -euo pipefail
cd "$(dirname "$0")"

SERVICE=pivocoder-flask.service
LOOP_PIDFILE=/tmp/vocoder-tune-loop.pid
LOOP_LOG=/tmp/vocoder-tune-loop.log

if [ -f "$LOOP_PIDFILE" ] && kill -0 "$(cat "$LOOP_PIDFILE")" 2>/dev/null; then
  echo "Ya hay una sesión de ajuste corriendo (PID $(cat "$LOOP_PIDFILE"))." >&2
  exit 1
fi

echo ">> Parando producción ($SERVICE)..."
systemctl --user stop "$SERVICE"

echo ">> Arrancando señal de prueba en bucle (sustituye el micro)..."
nohup /home/patch/venv/bin/python3 "$(dirname "$0")/loop_signal.py" "$@" \
  > "$LOOP_LOG" 2>&1 &
echo $! > "$LOOP_PIDFILE"
sleep 1
if ! kill -0 "$(cat "$LOOP_PIDFILE")" 2>/dev/null; then
  echo "El loop no arrancó, mira $LOOP_LOG" >&2
  exit 1
fi

cat <<EOF

>> Listo. Desde tu PC, abre la GUI de Carla con el mismo proyecto:
     ssh -X patch@192.168.0.10 carla /home/patch/pivocoder/prod/template01.carxp

>> Guarda con Ctrl+S en Carla antes de cerrarla si quieres conservar los cambios
   (es el mismo template01.carxp que usa producción).

>> Cuando termines: ./stop-tuning.sh
EOF
