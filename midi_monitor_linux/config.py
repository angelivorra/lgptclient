"""
Configuración global - MIDI Monitor Linux/Kirigami
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(BASE_DIR)
IMAGES_DIR = os.path.join(WORKSPACE_DIR, "ayuda_imagenes")
BATERIA_CONFIG_FILE = os.path.join(BASE_DIR, "bateria_config.json")

APP_NAME = "MIDI Monitor"

# 'start'/'stop' NO se filtran: marcan inicio/fin de canción para grabar subtítulos (.srt).
FILTERED_MESSAGES = {'clock', 'songpos', 'active_sensing', 'continue'}

QUEUE_UPDATE_INTERVAL = 10
PAD_LIGHT_DURATION = 150

# Roboguitarra (main.cpp): 3 cuerdas, UNA POR CANAL. La cuerda c emite en
# GUITARRA_STRING_CHANNELS[c] con nota al aire GUITARRA_OPEN_NOTES[c]; traste N
# = nota_aire + N. El joystick manda pitch bend y CC 91 (reverb) / 93 (chorus),
# globales (se reemiten a los 3 canales).
# (Estos valores se replican en qml/GuitarraPage.qml; manténlos sincronizados.)
GUITARRA_OPEN_NOTES = [64, 59, 55]        # 1ª=Mi4, 2ª=Si3, 3ª=Sol3 (índice = cuerda)
GUITARRA_STRING_CHANNELS = [0, 1, 2]      # CANALES en main.cpp: cuerda c -> canal c
GUITARRA_NUM_FRETS = 17
GUITARRA_CC_REVERB = 91
GUITARRA_CC_CHORUS = 93
