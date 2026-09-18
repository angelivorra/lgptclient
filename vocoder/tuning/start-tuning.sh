#!/bin/bash
# Arranca una sesión de ajuste del vocoder: para la producción (Carla headless
# gestionada por flask), copia template01.carxp a sessions/<timestamp>.carxp y
# deja sonando loop_signal.py (WAV en bucle + patrón MIDI) como modulador.
#
# Normalmente lo invoca tune.sh desde el PC (flujo completo con Carla GUI).
# También se puede lanzar directamente en la Pi para luego abrir Carla a mano:
#   ./start-tuning.sh [args de loop_signal.py]
#   p.ej.: ./start-tuning.sh --wav recordings/voz1.wav --bpm 90
#
# Para parar: ./stop-tuning.sh
set -euo pipefail
cd "$(dirname "$0")"

SERVICE=pivocoder-flask.service
LOOP_PIDFILE=/tmp/vocoder-tune-loop.pid
LOOP_LOG=/tmp/vocoder-tune-loop.log
PROD_CARXP=/home/patch/pivocoder/prod/template01.carxp
SESSION_DIR="$(pwd)/sessions"
SESSION_REF=/tmp/vocoder-tune-session

if [ -f "$LOOP_PIDFILE" ] && kill -0 "$(cat "$LOOP_PIDFILE")" 2>/dev/null; then
  echo "Ya hay una sesión de tuning corriendo (PID $(cat "$LOOP_PIDFILE"))." >&2
  exit 1
fi

mkdir -p "$SESSION_DIR"
SESSION_CARXP="$SESSION_DIR/$(date +%Y%m%d_%H%M%S).carxp"

echo ">> Creando sesión: $(basename "$SESSION_CARXP")..."
cp "$PROD_CARXP" "$SESSION_CARXP"
echo "$SESSION_CARXP" > "$SESSION_REF"

echo ">> Parando producción ($SERVICE)..."
systemctl --user stop "$SERVICE"

# Si no se pasa --wav, usa el recording más reciente; si no hay ninguno,
# cae al WAV de prueba incluido con la instalación.
EXTRA_ARGS=()
if [[ ! " $* " =~ " --wav " ]]; then
  LATEST_REC=$(ls -t "$(pwd)/recordings/"*.wav 2>/dev/null | head -1 || true)
  if [ -n "$LATEST_REC" ]; then
    echo ">> Usando recording: $(basename "$LATEST_REC")"
    EXTRA_ARGS=(--wav "$LATEST_REC")
  fi
fi

echo ">> Arrancando señal de prueba en bucle (sustituye el micro)..."
nohup /home/patch/venv/bin/python3 "$(pwd)/loop_signal.py" \
  "${EXTRA_ARGS[@]}" "$@" \
  > "$LOOP_LOG" 2>&1 &
echo $! > "$LOOP_PIDFILE"
sleep 1
if ! kill -0 "$(cat "$LOOP_PIDFILE")" 2>/dev/null; then
  echo "El loop no arrancó — mira $LOOP_LOG" >&2
  exit 1
fi

echo ""
echo ">> Listo. Sesión: $SESSION_CARXP"
echo ">> Para abrir Carla GUI desde el PC:"
echo "     ssh -X patch@192.168.0.10 carla $SESSION_CARXP"
echo ">> Para parar: ./stop-tuning.sh"
