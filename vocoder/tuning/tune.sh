#!/bin/bash
# Sesión de tuning del vocoder completa desde el PC de control:
#   1. Crea una copia con timestamp de template01.carxp en la Pi (sessions/)
#   2. Arranca loop_signal.py como modulador (sustituye el micro)
#   3. Abre la GUI de Carla vía VNC (túnel SSH) o ssh -Y como fallback
#   4. Al cerrar Carla, ofrece promover la sesión a producción
#   5. Para el loop y reanuda pivocoder-flask.service
#
# Uso (en este PC):
#   ./tune.sh
#   ./tune.sh --wav recordings/voz1.wav --bpm 90
#   ./tune.sh --progression andaluza
#
# Todos los args adicionales se pasan a loop_signal.py.
set -euo pipefail

HOST=patch@192.168.0.10
REMOTE_BASE=/home/patch/pivocoder/tuning
VNC_DISPLAY=:1
VNC_PORT=5901

_cleanup_vnc() {
  kill "$TUNNEL_PID" 2>/dev/null || true
  ssh "$HOST" "vncserver -kill $VNC_DISPLAY 2>/dev/null || true" 2>/dev/null || true
}

if ssh "$HOST" "[ -f /tmp/vocoder-tune-loop.pid ] && kill -0 \"\$(cat /tmp/vocoder-tune-loop.pid)\" 2>/dev/null"; then
  echo ">> Hay una sesión de tuning activa — parándola primero..."
  ssh "$HOST" "cd $REMOTE_BASE && ./stop-tuning.sh"
fi

echo ">> Iniciando sesión de tuning en la Pi..."
ssh "$HOST" "cd $REMOTE_BASE && ./start-tuning.sh $*"

SESSION_CARXP=$(ssh "$HOST" "cat /tmp/vocoder-tune-session")
echo ">> Sesión: $(basename "$SESSION_CARXP")"
echo ""

if ssh "$HOST" "command -v vncserver" &>/dev/null && command -v vncviewer &>/dev/null; then
  echo ">> Abriendo Carla GUI (VNC)..."

  # Limpia servidor VNC previo si quedó colgado
  ssh "$HOST" "vncserver -kill $VNC_DISPLAY 2>/dev/null || true"
  sleep 1

  # Arranca VNC sin contraseña (el túnel SSH lo protege)
  ssh "$HOST" "vncserver $VNC_DISPLAY -geometry 1280x900 -depth 24 -SecurityTypes None 2>/dev/null"
  sleep 2

  # Arranca Carla en el display VNC
  ssh "$HOST" "DISPLAY=$VNC_DISPLAY nohup carla '$SESSION_CARXP' >/tmp/carla-tune.log 2>&1 &"

  # Túnel SSH local → VNC en la Pi
  TUNNEL_PID=""
  ssh -N -L ${VNC_PORT}:localhost:${VNC_PORT} "$HOST" &
  TUNNEL_PID=$!
  trap _cleanup_vnc EXIT
  sleep 1

  echo ">> Carla abierta en VNC. Cierra la ventana cuando termines."
  vncviewer localhost:${VNC_PORT} 2>/dev/null

  _cleanup_vnc
  trap - EXIT
else
  echo ">> Abriendo Carla GUI (ssh -Y)..."
  ssh -Y -C "$HOST" "carla '$SESSION_CARXP'"
fi

echo ""
read -rp ">> ¿Llevar esta sesión a producción? [s/N]: " resp
if [[ "${resp,,}" == "s" ]]; then
    LOCAL_PROD="$(cd "$(dirname "$0")/.." && pwd)/prod/template01.carxp"
    scp "$HOST:$SESSION_CARXP" "$LOCAL_PROD"
    echo ""
    echo ">> Copiado a vocoder/prod/template01.carxp. Antes de desplegar:"
    echo "     git diff -- vocoder/prod/template01.carxp"
    echo "     git add vocoder/prod/template01.carxp && git commit && git push"
    echo "     ansible-playbook ansible/actualiza-vocoder.yaml -i ansible/inventario"
fi

echo ""
echo ">> Parando tuning y reanudando producción..."
ssh "$HOST" "cd $REMOTE_BASE && ./stop-tuning.sh"
