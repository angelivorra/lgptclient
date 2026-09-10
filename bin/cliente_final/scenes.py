"""Escena procedural para el framebuffer (800×480 RGB565).

Al START de una canción el cliente la arranca solo: no hay que poner MDCC
en la partitura ni cambiar el tracker. El GPIO no se entera.

Plasma al BPM de la canción; cada bombo/caja/crash encola un flash (mismo
reloj ts+1s que el audio). El render solo lee.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Optional

import numpy as np

WIDTH = 800
HEIGHT = 480
FRAME_BYTES = WIDTH * HEIGHT * 2

_HALF_LIFE = {
    "kick": 0.14,
    "snare": 0.10,
    "crash": 0.28,
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
        self._x = x
        self._y = y
        self._kick_w = 0.25 + 0.75 * y
        self._snare_w = np.clip(np.minimum(x, 1 - x) * 2.4, 0, 1)
        self._ceil_w = 1.0 - 0.25 * y
        self._v = np.empty((HEIGHT, WIDTH), dtype=np.float32)
        self._tmp = np.empty((HEIGHT, WIDTH), dtype=np.float32)
        self._r = np.empty((HEIGHT, WIDTH), dtype=np.float32)
        self._g = np.empty((HEIGHT, WIDTH), dtype=np.float32)
        self._b = np.empty((HEIGHT, WIDTH), dtype=np.float32)
        self._rgb = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

    def set_scene(self, name: Optional[str]):
        new = name if name == "live" else None
        if new == self.name:
            return
        self.name = new
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
        """Plasma al tempo + flashes a pantalla completa (bombo/caja/crash)."""
        ph = 2.0 * math.pi * (self.bpm / 60.0) * t
        v = self._v
        tmp = self._tmp

        np.multiply(self._x, 10.0, out=tmp)
        tmp += ph
        np.sin(tmp, out=v)

        np.multiply(self._y, 8.0, out=tmp)
        tmp -= ph * 1.15
        np.sin(tmp, out=tmp)
        v += tmp

        np.add(self._x, self._y, out=tmp)
        tmp *= 6.0
        tmp += ph * 0.45
        np.sin(tmp, out=tmp)
        v += tmp

        v += 3.0
        v *= (1.0 / 6.0)

        # Pulso de brillo a negra: 35% → 100%. Se tiene que ver de lejos.
        beat = 0.5 + 0.5 * math.sin(ph)
        level = 0.35 + 0.65 * beat
        r, g, b = self._r, self._g, self._b
        np.multiply(v, 140.0, out=r)
        r += 40.0
        r *= level
        r += 255.0 * kick + 40.0 * snare + 220.0 * crash

        np.multiply(v, 50.0, out=g)
        g += 12.0
        g *= level
        g += 30.0 * kick + 255.0 * snare + 220.0 * crash

        np.multiply(v, 180.0, out=b)
        b += 70.0
        b *= level
        b += 20.0 * kick + 180.0 * snare + 255.0 * crash

        np.clip(r, 0, 255, out=r)
        np.clip(g, 0, 255, out=g)
        np.clip(b, 0, 255, out=b)
        rgb = self._rgb
        rgb[:, :, 0] = r
        rgb[:, :, 1] = g
        rgb[:, :, 2] = b
        return rgb
