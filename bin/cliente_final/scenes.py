"""Escena procedural para el framebuffer (800×480 RGB565).

Al START de una canción el cliente la arranca solo: no hay que poner MDCC
en la partitura ni cambiar el tracker. El GPIO no se entera.

Mientras no hay golpe, una variación suave al BPM. Cada bombo/caja/crash
encola un impulso (mismo reloj ts+1s que el audio); el render solo lee.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np

WIDTH = 800
HEIGHT = 480
FRAME_BYTES = WIDTH * HEIGHT * 2

_HALF_LIFE = {
    "kick": 0.12,
    "snare": 0.09,
    "crash": 0.22,
}


def rgb888_to_rgb565(rgb: np.ndarray) -> bytes:
    """uint8 HxWx3 → RGB565 little-endian (768000 bytes)."""
    r = rgb[:, :, 0].astype(np.uint16)
    g = rgb[:, :, 1].astype(np.uint16)
    b = rgb[:, :, 2].astype(np.uint16)
    packed = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    return packed.astype("<u2").tobytes()


class SceneEngine:
    """Una sola escena 'live'. pulse()/set_bpm() son thread-safe."""

    def __init__(self, invert: bool = False):
        self.invert = invert
        self.name: Optional[str] = None
        self._lock = threading.Lock()
        self.bpm = 120.0
        self.kick = 0.0
        self.snare = 0.0
        self.crash = 0.0
        self._t0 = time.monotonic()
        self._last = self._t0
        y = np.linspace(0, 1, HEIGHT, dtype=np.float32)[:, None]
        x = np.linspace(0, 1, WIDTH, dtype=np.float32)[None, :]
        self._kick_w = 0.35 + 0.65 * y          # bombo: más abajo
        self._snare_w = np.clip(np.minimum(x, 1 - x) * 2.2, 0, 1)  # caja: lados
        self._ceil_w = 1.0 - 0.35 * y           # un poco más de cielo
        self._rgb = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

    def set_scene(self, name: Optional[str]):
        self.name = name if name == "live" else None
        self._t0 = time.monotonic()
        self._last = self._t0

    def set_bpm(self, bpm: float):
        if bpm > 0:
            self.bpm = float(bpm)

    def pulse(self, kind: str, velocity: int = 127):
        """Impulso 0-1 según velocity. Se suma y satura a 1."""
        v = max(0.25, min(1.0, velocity / 127.0))
        with self._lock:
            if kind == "kick":
                self.kick = min(1.0, self.kick + v)
            elif kind == "snare":
                self.snare = min(1.0, self.snare + v)
            elif kind == "crash":
                self.crash = min(1.0, self.crash + v)

    def _decay(self, dt: float):
        with self._lock:
            for attr, hl in _HALF_LIFE.items():
                cur = getattr(self, attr)
                setattr(self, attr, cur * (0.5 ** (dt / hl)) if cur > 1e-4 else 0.0)
            kick, snare, crash = self.kick, self.snare, self.crash
        return kick, snare, crash

    def render(self) -> Optional[bytes]:
        if self.name != "live":
            return None
        now = time.monotonic()
        dt = min(0.08, max(0.0, now - self._last))
        self._last = now
        t = now - self._t0
        kick, snare, crash = self._decay(dt)
        rgb = self._render_live(t, kick, snare, crash)
        if self.invert:
            rgb = rgb[::-1, ::-1]
        return rgb888_to_rgb565(rgb)

    def _render_live(self, t: float, kick: float, snare: float, crash: float) -> np.ndarray:
        """Cama suave al BPM + flashes de bombo/caja/crash."""
        beat = 0.5 + 0.5 * np.sin(2 * np.pi * (self.bpm / 60.0) * t)
        # Variación pequeña si no hay golpe (no un plasma entero).
        ambient = 12.0 + 14.0 * beat
        rgb = self._rgb
        r = ambient + 210 * kick + 30 * snare + 200 * crash
        g = ambient * 0.85 + 35 * kick + 190 * snare + 200 * crash
        b = ambient * 1.15 + 15 * kick + 220 * snare + 190 * crash
        rgb[:, :, 0] = np.clip(r * self._kick_w, 0, 255)
        rgb[:, :, 1] = np.clip(g * (0.55 + 0.45 * self._snare_w), 0, 255)
        rgb[:, :, 2] = np.clip(b * self._ceil_w, 0, 255)
        return rgb
