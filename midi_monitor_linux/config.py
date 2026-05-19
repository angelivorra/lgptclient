"""
Configuración global - MIDI Monitor Linux/Kirigami
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(BASE_DIR)
IMAGES_DIR = os.path.join(WORKSPACE_DIR, "ayuda_imagenes")
BATERIA_CONFIG_FILE = os.path.join(BASE_DIR, "bateria_config.json")

APP_NAME = "MIDI Monitor"

FILTERED_MESSAGES = {'clock', 'songpos', 'active_sensing', 'start', 'stop', 'continue'}

QUEUE_UPDATE_INTERVAL = 10
PAD_LIGHT_DURATION = 150
