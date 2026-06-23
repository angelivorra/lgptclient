"""
Grabador de subtítulos .srt para el banco de textos 002.

Modelo de uso (controlado desde app_backend a partir de eventos MIDI):
    - MIDI 'start'  -> start()   : fija el tiempo 0 y vacía el buffer.
    - CC nº 2       -> add_text(): registra el texto (línea del fichero 'textos')
                                    junto al instante relativo al inicio.
    - MIDI 'stop'   -> stop()    : vuelca el .srt y devuelve la ruta.

Cada subtítulo dura como mucho MAX_SUBTITLE_SECONDS; si el siguiente texto llega
antes, se acorta para no solaparse.
"""

import os
import time
from datetime import datetime

from config import WORKSPACE_DIR

# Fichero con una línea de texto por cada valor del banco 002 (valor 0 = línea 1).
TEXTOS_FILE = os.path.join(WORKSPACE_DIR, "images", "002", "textos")
# Carpeta de salida para los .srt generados.
SUBTITULOS_DIR = os.path.join(WORKSPACE_DIR, "subtitulos")

# Número de CC del banco de textos (banco "002").
TEXT_CC = 2
# Duración máxima de un subtítulo, en segundos. Si el siguiente texto llega antes,
# el subtítulo se acorta hasta ese instante.
MAX_SUBTITLE_SECONDS = 1.0
# Duración mínima de un subtítulo para evitar entradas de 0 ms, en segundos.
MIN_SUBTITLE_SECONDS = 0.3


class SrtRecorder:
    """Acumula los textos del banco 002 con marcas de tiempo y los escribe en .srt."""

    def __init__(self):
        self._lines = self._load_textos()
        self._recording = False
        self._t0 = 0.0
        self._events = []  # lista de (segundos_relativos, texto)

    @staticmethod
    def _load_textos():
        try:
            with open(TEXTOS_FILE, "r", encoding="utf-8") as f:
                return [line.rstrip("\n") for line in f]
        except Exception as e:
            print(f"Error cargando textos ({TEXTOS_FILE}): {e}")
            return []

    @property
    def recording(self) -> bool:
        return self._recording

    # ------------------------------------------------------------------ control

    def start(self) -> None:
        """Inicia una nueva grabación: tiempo 0 = ahora, buffer vacío."""
        self._recording = True
        self._t0 = time.monotonic()
        self._events = []

    def add_text(self, value: int):
        """Registra el texto correspondiente al valor recibido. Devuelve el texto o None."""
        if not self._recording:
            return None
        if 0 <= value < len(self._lines):
            text = self._lines[value]
        else:
            text = ""
        # Ignorar valores sin texto asociado (mantiene el subtítulo previo en pantalla).
        if not text.strip():
            return None
        elapsed = time.monotonic() - self._t0
        self._events.append((elapsed, text))
        return text

    def stop(self):
        """Finaliza la grabación y vuelca el .srt. Devuelve la ruta o None si no hubo textos."""
        if not self._recording:
            return None
        self._recording = False
        if not self._events:
            return None
        path = self._write_srt()
        self._events = []
        return path

    # ------------------------------------------------------------------ escritura

    def _write_srt(self) -> str:
        os.makedirs(SUBTITULOS_DIR, exist_ok=True)
        name = datetime.now().strftime("subtitulos_%Y-%m-%d_%H-%M-%S.srt")
        path = os.path.join(SUBTITULOS_DIR, name)

        with open(path, "w", encoding="utf-8") as f:
            total = len(self._events)
            for i, (start, text) in enumerate(self._events):
                # Como mucho 1 segundo; si el siguiente texto llega antes, acortar.
                end = start + MAX_SUBTITLE_SECONDS
                if i + 1 < total:
                    end = min(end, self._events[i + 1][0])
                if end - start < MIN_SUBTITLE_SECONDS:
                    end = start + MIN_SUBTITLE_SECONDS
                f.write(f"{i + 1}\n")
                f.write(f"{self._fmt(start)} --> {self._fmt(end)}\n")
                f.write(f"{text}\n\n")
        return path

    @staticmethod
    def _fmt(seconds: float) -> str:
        """Formatea segundos al formato SRT: HH:MM:SS,mmm."""
        if seconds < 0:
            seconds = 0
        ms = int(round(seconds * 1000))
        h, ms = divmod(ms, 3_600_000)
        m, ms = divmod(ms, 60_000)
        s, ms = divmod(ms, 1_000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
