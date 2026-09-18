#!/bin/bash
# Cierra la sesión de ajuste (para loop_signal.py) y reanuda la producción
# normal del vocoder (Carla headless vía flask). Ver start-tuning.sh.
set -euo pipefail

SERVICE=pivocoder-flask.service
LOOP_PIDFILE=/tmp/vocoder-tune-loop.pid

if [ -f "$LOOP_PIDFILE" ]; then
  PID=$(cat "$LOOP_PIDFILE")
  if kill -0 "$PID" 2>/dev/null; then
    echo ">> Parando señal de prueba (PID $PID)..."
    kill "$PID"
    for _ in $(seq 1 20); do
      kill -0 "$PID" 2>/dev/null || break
      sleep 0.2
    done
  fi
  rm -f "$LOOP_PIDFILE"
fi

if pgrep -f 'bin/carla .*/sessions/' >/dev/null 2>&1; then
  echo "AVISO: la GUI de Carla sigue abierta. Si no has guardado (Ctrl+S)," >&2
  echo "  ciérrala primero o perderás los cambios antes de parar." >&2
fi

echo ">> Reanudando producción ($SERVICE)..."
systemctl --user start "$SERVICE"
