#!/bin/bash
# Instala robotracker2 en la Odin 2 (ROCKNIX).
#
#   ./install.sh [usuario@]host                 (p.ej. root@192.168.0.30)
#   ./install.sh [usuario@]host --with-samples  (además sincroniza samples/,
#                                                18 GB — solo por cable/lento)
#
# Copia el código a /storage/robotracker2, el .gptk, y el launcher del port a
# /storage/roms/ports/. Reutiliza el venv de robotracker (/storage/robotracker-
# venv) y su sinte (/storage/sinte), que ya deben estar en el dispositivo.
# También siembra /storage/samples (samples de las canciones) y sincroniza
# /storage/images entero (eventos de pantalla del canal de robotas, ~25 MB).
set -euo pipefail

HOST="${1:?uso: install.sh [usuario@]host}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"      # carpeta robotracker2/
REPO="$(cd "$SRC/.." && pwd)"                # raíz del repo (lgptclient)

echo ">> Comprobando dependencias en $HOST (venv y sinte de robotracker)..."
ssh "$HOST" '
  test -x /storage/robotracker-venv/bin/python3 || {
    echo "FALTA /storage/robotracker-venv (instala robotracker primero)"; exit 1; }
  test -d /storage/sinte || {
    echo "FALTA /storage/sinte (lo usa robotracker)"; exit 1; }
  mkdir -p /storage/robotracker2 /storage/roms/ports /storage/samples /storage/images
'

# Siembra /storage/samples con los samples de las canciones ya presentes
# (copia local en el dispositivo, rápida; no sobreescribe).
echo ">> Sembrando /storage/samples con los samples de las canciones..."
ssh "$HOST" '
  shopt -s nullglob
  for f in /storage/sinte/songs/*/samples/*.[wW][aA][vV]; do
    cp -n "$f" /storage/samples/ 2>/dev/null || true
  done
  echo "   /storage/samples: $(ls /storage/samples | wc -l) wav"
'

# images/ (eventos de pantalla del canal de robotas): pequeña (~25 MB), se
# sincroniza entera siempre, sin flag.
if [ -d "$REPO/images" ]; then
    echo ">> Sincronizando images/ (eventos de pantalla)..."
    rsync -a --delete "$REPO/images/" "$HOST:/storage/images/"
fi

echo ">> Sincronizando código a /storage/robotracker2 ..."
rsync -a --delete \
  --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude 'odin' \
  "$SRC/" "$HOST:/storage/robotracker2/"

echo ">> Copiando gptk y launcher del port ..."
scp "$SRC/odin/robotracker2.gptk" "$HOST:/storage/robotracker2/robotracker2.gptk"
scp "$SRC/odin/Robotracker2.sh"   "$HOST:/storage/roms/ports/Robotracker2.sh"
ssh "$HOST" 'chmod +x /storage/roms/ports/Robotracker2.sh'

# Sincronización opcional de la biblioteca completa de samples (18 GB).
if [ "${2:-}" = "--with-samples" ] && [ -d "$REPO/samples" ]; then
    echo ">> Sincronizando biblioteca samples/ (18 GB, puede tardar)..."
    rsync -a --info=progress2 "$REPO/samples/" "$HOST:/storage/samples/"
fi

echo ">> Hecho. Reinicia EmulationStation (o refresca Ports) y abre ROBOTRACKER2."
