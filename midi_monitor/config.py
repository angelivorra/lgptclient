"""
Configuración global de la aplicación
"""

import os

# Rutas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(BASE_DIR)
IMAGES_DIR = os.path.join(WORKSPACE_DIR, "ayuda_imagenes")
BATERIA_CONFIG_FILE = os.path.join(BASE_DIR, "bateria_config.json")

# Nombre de la aplicación
APP_NAME = "MIDI Monitor"

# Tamaño de ventana
WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 750
WINDOW_MIN_WIDTH = 800
WINDOW_MIN_HEIGHT = 600

# Tipos de mensajes MIDI a filtrar (no mostrar)
FILTERED_MESSAGES = {'clock', 'songpos', 'active_sensing', 'start', 'stop', 'continue'}

# Intervalo de actualización de la cola (ms)
QUEUE_UPDATE_INTERVAL = 10

# Tiempo que permanece iluminado un pad de batería (ms)
PAD_LIGHT_DURATION = 150

# Tamaño de imagen en visuales
VISUAL_IMAGE_SIZE = (400, 400)

# Colores para el log
LOG_COLORS = {
    "info": "#4fc3f7",
    "success": "#81c784",
    "error": "#e57373",
    "warning": "#ffb74d",
    "midi_note": "#ba68c8",
    "midi_cc": "#4db6ac",
    "midi_other": "#aaaaaa",
}

# Estilo del log
LOG_BG_COLOR = "#1e1e1e"
LOG_FG_COLOR = "#ffffff"
LOG_FONT = ("Consolas", 10)
