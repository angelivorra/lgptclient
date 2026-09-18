#!/bin/bash
# Trae la sesión de tuning más reciente al repo como candidato a nueva producción.
# Si hay una sesión activa usa esa; si no, la última de sessions/ por fecha.
# Ejecutar desde el PC de control (no desde la Pi).
set -euo pipefail

HOST=patch@192.168.0.10
LOCAL="$(cd "$(dirname "$0")/.." && pwd)/prod/template01.carxp"

REMOTE=$(ssh "$HOST" \
  "cat /tmp/vocoder-tune-session 2>/dev/null \
   || ls -t /home/patch/pivocoder/tuning/sessions/*.carxp 2>/dev/null | head -1" \
  || true)

if [ -z "$REMOTE" ]; then
  echo "No hay sesión activa ni sesiones anteriores en la Pi." >&2
  exit 1
fi

echo ">> Trayendo $(basename "$REMOTE")..."
scp "$HOST:$REMOTE" "$LOCAL"

cat <<EOF

>> Copiado a $LOCAL. Revisa antes de comitear:
     git diff -- vocoder/prod/template01.carxp
>> Si te convence:
     git add vocoder/prod/template01.carxp && git commit && git push
     ansible-playbook ansible/actualiza-vocoder.yaml -i ansible/inventario
EOF
