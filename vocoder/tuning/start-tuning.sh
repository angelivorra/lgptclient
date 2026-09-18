#!/bin/bash
# Arranca una sesión de ajuste del vocoder: para la producción (Carla
# headless gestionada por flask), deja sonando en bucle una señal de prueba
# (loop_signal.py) y te dice cómo abrir la GUI de Carla por SSH -X sobre una
# COPIA del proyecto (sandbox.carxp) — template01.carxp NUNCA se toca aquí,
# sigue siendo el que usa producción.
#
# Uso (en la Pi del vocoder, o por ssh):
#   ./start-tuning.sh [--reset] [args de loop_signal.py]
#   --reset      vuelve a partir de template01.carxp (descarta el sandbox
#                previo; si no, se reutiliza el sandbox de la última sesión)
#   p.ej.: ./start-tuning.sh --wav recordings/1234.wav --bpm 90
#
# Para volver a producción: ./stop-tuning.sh
# Para llevar el sandbox a producción: pull-tuning.sh (se ejecuta en el PC).
set -euo pipefail
cd "$(dirname "$0")"

SERVICE=pivocoder-flask.service
LOOP_PIDFILE=/tmp/vocoder-tune-loop.pid
LOOP_LOG=/tmp/vocoder-tune-loop.log
PROD_CARXP=/home/patch/pivocoder/prod/template01.carxp
SANDBOX_CARXP="$(pwd)/sandbox.carxp"

RESET=0
if [ "${1:-}" = "--reset" ]; then
  RESET=1
  shift
fi

if [ -f "$LOOP_PIDFILE" ] && kill -0 "$(cat "$LOOP_PIDFILE")" 2>/dev/null; then
  echo "Ya hay una sesión de ajuste corriendo (PID $(cat "$LOOP_PIDFILE"))." >&2
  exit 1
fi

if [ "$RESET" = "1" ] || [ ! -f "$SANDBOX_CARXP" ]; then
  echo ">> Copiando template01.carxp -> sandbox.carxp (punto de partida)..."
  cp "$PROD_CARXP" "$SANDBOX_CARXP"
else
  echo ">> Reutilizando sandbox.carxp de una sesión anterior (usa --reset para partir de cero)."
fi

echo ">> Parando producción ($SERVICE)..."
systemctl --user stop "$SERVICE"

echo ">> Arrancando señal de prueba en bucle (sustituye el micro)..."
nohup /home/patch/venv/bin/python3 "$(pwd)/loop_signal.py" "$@" \
  > "$LOOP_LOG" 2>&1 &
echo $! > "$LOOP_PIDFILE"
sleep 1
if ! kill -0 "$(cat "$LOOP_PIDFILE")" 2>/dev/null; then
  echo "El loop no arrancó, mira $LOOP_LOG" >&2
  exit 1
fi

cat <<EOF

>> Listo. Desde tu PC, abre la GUI de Carla sobre la COPIA de pruebas
   (template01.carxp de producción no se toca):
     ssh -X patch@192.168.0.10 carla $SANDBOX_CARXP

>> Guarda con Ctrl+S cuando quieras, es sandbox.carxp.
>> Para llevar estos cambios a producción: pull-tuning.sh desde tu PC (revisa
   el diff antes de comitear vocoder/prod/template01.carxp).

>> Cuando termines: ./stop-tuning.sh
EOF
