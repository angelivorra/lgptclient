#!/bin/bash
# Sesión de tuning del vocoder completa desde el PC de control:
#   1. Crea una copia con timestamp de template01.carxp en la Pi (sessions/)
#   2. Arranca loop_signal.py como modulador (sustituye el micro)
#   3. Abre la GUI de Carla por SSH -X: añade/quita plugins, mueve knobs
#   4. Al cerrar Carla, ofrece promover la sesión a producción
#   5. Para el loop y reanuda pivocoder-flask.service
#
# Uso (en este PC):
#   ./tune.sh
#   ./tune.sh --wav recordings/voz1.wav --bpm 90
#   ./tune.sh --notes 60,64,67 --vel 80
#
# Todos los args adicionales se pasan a loop_signal.py.
set -euo pipefail

HOST=patch@192.168.0.10
REMOTE_BASE=/home/patch/pivocoder/tuning

if ssh "$HOST" "[ -f /tmp/vocoder-tune-loop.pid ] && kill -0 \"\$(cat /tmp/vocoder-tune-loop.pid)\" 2>/dev/null"; then
  echo ">> Hay una sesión de tuning activa — parándola primero..."
  ssh "$HOST" "cd $REMOTE_BASE && ./stop-tuning.sh"
fi

echo ">> Iniciando sesión de tuning en la Pi..."
ssh "$HOST" "cd $REMOTE_BASE && ./start-tuning.sh $*"

SESSION_CARXP=$(ssh "$HOST" "cat /tmp/vocoder-tune-session")
echo ">> Sesión: $(basename "$SESSION_CARXP")"
echo ""
echo ">> Abriendo Carla GUI..."
if command -v xpra &>/dev/null && ssh "$HOST" "command -v xpra" &>/dev/null; then
  echo "   (vía xpra)"
  xpra start "ssh://$HOST/" \
    --start-child="carla '$SESSION_CARXP'" \
    --exit-with-children=yes \
    --attach=yes \
    --speaker=disabled \
    --microphone=disabled
else
  echo "   (vía ssh -Y — instala xpra en el PC para mejor rendimiento)"
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
