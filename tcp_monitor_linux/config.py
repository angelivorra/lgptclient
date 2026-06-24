"""
Configuración global — TCP Monitor
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

APP_NAME = "TCP Monitor"

TCP_HOST = "192.168.0.2"
TCP_PORT = 8888
RECONNECT_DELAY_S = 3.0

# Alerta si un mensaje llega con más de este retraso respecto al timestamp del servidor
LATE_THRESHOLD_MS = 100

# Intervalo del QTimer para procesar la cola de mensajes TCP
QUEUE_UPDATE_INTERVAL_MS = 10

# Ventana de latencia para calcular media/máximo
LATENCY_WINDOW = 50  # últimas N muestras
