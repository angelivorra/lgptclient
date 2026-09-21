#!/bin/bash
# Graba el micro del vocoder (system:capture_1) a un WAV en la Pi.
# Lanzar desde el PC de control, con producción activa (Carla/JACK corriendo).
# El WAV resultante se usará automáticamente en la próxima sesión de tune.sh.
#
# Uso:
#   ./record.sh                        # 20s, nombre por timestamp
#   ./record.sh --seconds 30
#   ./record.sh --seconds 15 --out recordings/voz_nueva.wav
#
# Todos los args se pasan a record_input.py.
set -euo pipefail

HOST=patch@192.168.0.10
REMOTE_BASE=/home/patch/pivocoder/tuning

echo ">> Grabando en la Pi (producción debe estar activa — Carla/JACK corriendo)..."
ssh -t "$HOST" "cd $REMOTE_BASE && /home/patch/venv/bin/python3 record_input.py $*"
echo ""
echo ">> Grabación guardada en $HOST:$REMOTE_BASE/recordings/"
echo ">> Se usará automáticamente la próxima vez que lances tune.sh sin --wav."
