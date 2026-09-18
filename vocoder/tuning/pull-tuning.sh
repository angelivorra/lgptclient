#!/bin/bash
# Trae sandbox.carxp (ajustado en la Pi durante una sesión de tuning, ver
# start-tuning.sh) al repo como CANDIDATO a nueva producción. No comitea ni
# sube nada solo: revisa el diff y decide tú.
#
# Ejecutar desde el PC de control (no desde la Pi).
set -euo pipefail

HOST=patch@192.168.0.10
REMOTE=/home/patch/pivocoder/tuning/sandbox.carxp
LOCAL="$(cd "$(dirname "$0")/.." && pwd)/prod/template01.carxp"

scp "$HOST:$REMOTE" "$LOCAL"

cat <<EOF

>> Copiado a $LOCAL. Revisa antes de comitear:
     git diff -- vocoder/prod/template01.carxp

>> Si te convence:
     git add vocoder/prod/template01.carxp && git commit && git push
     ansible-playbook ansible/actualiza-vocoder.yaml -i ansible/inventario
EOF
