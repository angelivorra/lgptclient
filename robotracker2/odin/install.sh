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
# /storage/images y /storage/ayuda_imagenes enteros (eventos de pantalla del
# canal de robotas + sus miniaturas ya renderizadas, ~35 MB en total).
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
  mkdir -p /storage/robotracker2 /storage/roms/ports /storage/samples \
           /storage/images /storage/ayuda_imagenes
'

# midi_control.py (control MIDI del reproductor, compartido con sinte): es
# nuevo, va a /storage/sinte sin tocar nada de lo que robotracker usa.
echo ">> Copiando sinte/midi_control.py a /storage/sinte ..."
scp "$REPO/sinte/midi_control.py" "$HOST:/storage/sinte/midi_control.py"

# El control MIDI usa atributos del engine (fx_presence, pad_volume_map...,
# los mismos que mixer/sinte): avisar si el sinte de la Odin es más antiguo.
ssh "$HOST" '
  if ! grep -q "fx_presence" /storage/sinte/lgpt_engine.py \
     || ! grep -q "pad_volume_map" /storage/sinte/lgpt_engine.py; then
    echo "AVISO: /storage/sinte/lgpt_engine.py es antiguo (sin fx_presence"
    echo "       o pad_volume_map). robotracker2 arrancará, pero el control"
    echo "       MIDI (robotraca.json) fallará al cargar canciones."
  fi
  if ! grep -q "load_pad_bank" /storage/sinte/lgpt_engine.py; then
    echo "AVISO: /storage/sinte/lgpt_engine.py no tiene load_pad_bank."
    echo "       La pantalla PADS guardará (robotraca.json), pero los pads"
    echo "       por canción no sonarán hasta actualizar el sinte de"
    echo "       robotracker."
  fi
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

# images/ (eventos de pantalla del canal de robotas) y ayuda_imagenes/ (sus
# miniaturas ya renderizadas, para la vista previa del editor): pequeñas,
# se sincronizan enteras siempre, sin flag.
if [ -d "$REPO/images" ]; then
    echo ">> Sincronizando images/ (eventos de pantalla)..."
    rsync -a --delete "$REPO/images/" "$HOST:/storage/images/"
fi
if [ -d "$REPO/ayuda_imagenes" ]; then
    echo ">> Sincronizando ayuda_imagenes/ (miniaturas de vista previa)..."
    rsync -a --delete "$REPO/ayuda_imagenes/" "$HOST:/storage/ayuda_imagenes/"
fi
# Biblioteca de samples de los pads (clave "pads" del robotraca.json de cada
# canción, resuelta contra /storage/pads): pequeña, entera siempre.
if [ -d "$REPO/pads" ]; then
    echo ">> Sincronizando pads/ (biblioteca de samples de los pads)..."
    rsync -a --delete "$REPO/pads/" "$HOST:/storage/pads/"
fi

echo ">> Sincronizando código a /storage/robotracker2 ..."
rsync -a --delete \
  --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude 'odin' \
  "$SRC/" "$HOST:/storage/robotracker2/"

echo ">> Copiando gptk, gamecontrollerdb, keylog y launcher del port ..."
scp "$SRC/odin/robotracker2.gptk"   "$HOST:/storage/robotracker2/robotracker2.gptk"
scp "$SRC/odin/gamecontrollerdb.txt" "$HOST:/storage/robotracker2/gamecontrollerdb.txt"
scp "$SRC/odin/keylog.py"       "$HOST:/storage/robotracker2/keylog.py"
scp "$SRC/odin/keylog_test.sh"  "$HOST:/storage/robotracker2/keylog_test.sh"
scp "$SRC/odin/Robotracker2.sh"      "$HOST:/storage/roms/ports/Robotracker2.sh"
ssh "$HOST" 'chmod +x /storage/roms/ports/Robotracker2.sh \
                       /storage/robotracker2/keylog_test.sh'

# Sincronización opcional de la biblioteca completa de samples (18 GB).
if [ "${2:-}" = "--with-samples" ] && [ -d "$REPO/samples" ]; then
    echo ">> Sincronizando biblioteca samples/ (18 GB, puede tardar)..."
    rsync -a --info=progress2 "$REPO/samples/" "$HOST:/storage/samples/"
fi

echo ">> Hecho. Reinicia EmulationStation (o refresca Ports) y abre ROBOTRACKER2."
