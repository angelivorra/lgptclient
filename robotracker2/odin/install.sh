#!/bin/bash
# Instala robotracker2 en la Odin 2 (ROCKNIX).
#
#   ./install.sh [usuario@]host                 (p.ej. root@192.168.0.101)
#
# Copia el código a /storage/robotracker2, el .gptk, y el launcher del port a
# /storage/roms/ports/. Reutiliza el venv de robotracker (/storage/robotracker-
# venv) y su sinte (/storage/sinte), que ya deben estar en el dispositivo.
# Sincroniza la biblioteca de samples (samples/ con subcarpetas), pads/,
# /storage/images, /storage/ayuda_imagenes y las canciones con sus samples.
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

# Módulos de sinte que importa robotracker2 (parser/engine/chords/filtro/
# writer/MIDI). El resto de /storage/sinte (player, songs, venv) no se toca.
echo ">> Copiando módulos de sinte que usa robotracker2..."
for f in lgpt_parser.py lgpt_engine.py lgpt_writer.py midi_control.py \
         chords.py filter_ui.py ladspa_fx.py play_stats.py master_eq.py; do
  scp "$REPO/sinte/$f" "$HOST:/storage/sinte/$f"
done

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
# Biblioteca de samples del navegador (organizada: drums/bass/synth/...).
if [ -d "$REPO/samples" ]; then
    echo ">> Sincronizando samples/ (biblioteca del navegador)..."
    rsync -a --delete "$REPO/samples/" "$HOST:/storage/samples/"
    echo "   /storage/samples: $(ssh "$HOST" 'find /storage/samples -iname "*.wav" | wc -l') wav"
fi
# Biblioteca de samples de los pads (clave "pads" del robotraca.json de cada
# canción, resuelta contra /storage/pads): pequeña, entera siempre.
if [ -d "$REPO/pads" ]; then
    echo ">> Sincronizando pads/ (biblioteca de samples de los pads)..."
    rsync -a --delete "$REPO/pads/" "$HOST:/storage/pads/"
fi
# Canciones: lgptsav.dat, robotraca.json, textos y samples/ (lo que suena).
# Sin --delete: no borra canciones que solo existan en la Odin.
if [ -d "$REPO/sinte/songs" ]; then
    echo ">> Sincronizando canciones (lgptsav / robotraca / samples)..."
    rsync -a \
      --exclude '*.bak' --exclude '*.dat.bak' --exclude '__pycache__' \
      --exclude 'play_stats.txt' --exclude 'play_stats.txt.tmp' \
      "$REPO/sinte/songs/" "$HOST:/storage/sinte/songs/"
    echo "   canciones: $(ssh "$HOST" 'ls -d /storage/sinte/songs/lgpt_* 2>/dev/null | wc -l')"
    echo "   samples de canción: $(ssh "$HOST" 'find /storage/sinte/songs -path "*/samples/*.wav" | wc -l') wav"
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

echo ">> Hecho. Reinicia EmulationStation (o refresca Ports) y abre ROBOTRACKER2."
