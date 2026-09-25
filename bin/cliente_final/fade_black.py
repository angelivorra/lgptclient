"""Fundido a negro de la imagen 01.

Ocho filas de Robotracker: una fila son 15/BPM segundos. A 180 BPM
duran 2/3 s. El campo no es negro puro: el composite del live se come
el lum≤6, así que el final es gris 18,18,18.
"""
from __future__ import annotations

import threading
import time

import numpy as np

from ribbon import HEIGHT, WIDTH
from scenes import rgb888_to_rgb565

FADE_CC = 1
FADE_VALUE = 1
FADE_ROWS = 8
TICKS_PER_ROW = 15
# Gris que sobrevive a _composite_rgb565 (lum=8, no azul-dominante).
_OFF = (18, 18, 18)


def fade_seconds(bpm: float) -> float:
    tempo = bpm if bpm and bpm > 0 else 180.0
    return FADE_ROWS * TICKS_PER_ROW / tempo


def fade_frame(alpha: float) -> bytes:
    """Pantalla del fundido. alpha 0 = vacío, 1 = negro opaco."""
    a = max(0.0, min(1.0, float(alpha)))
    rgb = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    rgb[:, :] = tuple(int(round(c * a)) for c in _OFF)
    return rgb888_to_rgb565(rgb)


class FadeBlack:
    """Un fundido. El siguiente lo reinicia."""

    def __init__(self):
        self._lock = threading.Lock()
        self._born = 0.0
        self._dur = 0.0
        self._on = False

    def clear(self) -> None:
        with self._lock:
            self._on = False

    def start(self, bpm: float, now: float | None = None) -> float:
        dur = fade_seconds(bpm)
        with self._lock:
            self._born = time.monotonic() if now is None else now
            self._dur = dur
            self._on = True
        return dur

    def pending(self, now: float | None = None) -> bool:
        return self.alpha(now) > 0.0

    def alpha(self, now: float | None = None) -> float:
        with self._lock:
            if not self._on or self._dur <= 0:
                return 0.0
            now = time.monotonic() if now is None else now
            t = (now - self._born) / self._dur
            if t >= 1.0:
                self._on = False
                return 0.0
            if t <= 0.0:
                return 0.0
            return t

    def blit_rgb565(self, frame: bytes, now: float | None = None) -> bytes:
        a = self.alpha(now)
        if a <= 0.0 or len(frame) != WIDTH * HEIGHT * 2:
            return frame
        arr = np.frombuffer(bytearray(frame), dtype="<u2").astype(np.uint16)
        r = ((arr >> 11) & 31).astype(np.float32)
        g = ((arr >> 5) & 63).astype(np.float32)
        b = (arr & 31).astype(np.float32)
        r *= (1.0 - a)
        g *= (1.0 - a)
        b *= (1.0 - a)
        # Al final, el campo opaco para que no se coma el composite.
        r += (_OFF[0] * (31.0 / 255.0)) * a
        g += (_OFF[1] * (63.0 / 255.0)) * a
        b += (_OFF[2] * (31.0 / 255.0)) * a
        out = (
            (r.astype(np.uint16) << 11)
            | (g.astype(np.uint16) << 5)
            | b.astype(np.uint16)
        )
        return out.astype("<u2").tobytes()
