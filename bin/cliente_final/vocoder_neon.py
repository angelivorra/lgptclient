"""Latigazo de las notas de voz en los márgenes del framebuffer.

Cada ``ACRD`` enciende las dos bandas laterales de golpe (la raíz elige
el color, la velocidad el brillo) y se funde solo. Un acorde y una nota
suelta se ven igual: la pantalla reacciona con el vocoder, no dibuja
el acorde.

Fuente única para las robotas (``display_executor``) y el LIVE de
Robotracker (``shared_visuals``). Solo se escriben las columnas
``x < MARGIN`` y ``x >= WIDTH - MARGIN``.
"""
from __future__ import annotations

import math
import threading
import time

import numpy as np

from ribbon import HEIGHT, WIDTH

MARGIN = 56
FADE_S = 0.50
# A los FADE_S el golpe está ~al 5 %.
TAU = FADE_S / 3.0

# Graves magenta, agudos cian (misma familia que lyric_render.TEMAS_ROBOT).
MAGENTA = (255, 0, 200)
CYAN = (0, 229, 255)
NOTE_LO = 36   # C2
NOTE_HI = 84   # C6

_XS = np.arange(MARGIN, dtype=np.float32)
# Núcleo sólido en el borde y caída hacia dentro. Índice 0 = borde exterior.
_WEIGHTS = np.exp(-_XS / 12.0).astype(np.float32)
_WEIGHTS[:4] = 1.0


def color_for_note(note: int) -> tuple[int, int, int]:
    """Graves → magenta, agudos → cian. Fuera de C2–C6, clamp."""
    t = (max(NOTE_LO, min(NOTE_HI, int(note))) - NOTE_LO) / float(NOTE_HI - NOTE_LO)
    return tuple(int(round(m + (c - m) * t)) for m, c in zip(MAGENTA, CYAN))


def parse_acrd(parts: list[str]) -> tuple[int, int, int, list[int]] | None:
    """``ACRD,ts,canal,vel,nota1,...`` → (ts, canal, vel, notas). None si no vale."""
    if not parts or parts[0] != "ACRD" or len(parts) < 5:
        return None
    try:
        ts = int(parts[1])
        channel = int(parts[2])
        vel = int(parts[3])
        notes = [int(p) for p in parts[4:]]
    except ValueError:
        return None
    if not notes:
        return None
    vel = max(1, min(127, vel))
    return ts, channel, vel, notes


def _rgba(amp: float, color: tuple[int, int, int]) -> np.ndarray:
    """(MARGIN, 4) float 0–1, índice 0 = borde exterior: r, g, b, alpha."""
    w = _WEIGHTS
    mix = 0.45 * w
    cr, cg, cb = (c / 255.0 for c in color)
    out = np.empty((MARGIN, 4), dtype=np.float32)
    out[:, 0] = cr + (1.0 - cr) * mix
    out[:, 1] = cg + (1.0 - cg) * mix
    out[:, 2] = cb + (1.0 - cb) * mix
    out[:, 3] = np.clip(amp * w, 0.0, 1.0)
    return out


def _paint(view: np.ndarray, rgba: np.ndarray, *, outer_left: bool) -> None:
    """Suma el latigazo sobre una franja (alto, MARGIN) RGB565."""
    tone = rgba if outer_left else rgba[::-1]
    r = ((view >> 11) & 31).astype(np.float32)
    g = ((view >> 5) & 63).astype(np.float32)
    b = (view & 31).astype(np.float32)
    a = tone[:, 3]
    r += tone[:, 0] * 31.0 * a
    g += tone[:, 1] * 63.0 * a
    b += tone[:, 2] * 31.0 * a
    np.minimum(31.0, r, out=r)
    np.minimum(63.0, g, out=g)
    np.minimum(31.0, b, out=b)
    view[:, :] = (
        (r.astype(np.uint16) << 11)
        | (g.astype(np.uint16) << 5)
        | b.astype(np.uint16)
    )


class VocoderNeon:
    """Un golpe en los dos márgenes. El siguiente ACRD lo re-dispara."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._on = False
        self._peak = 0.0
        self._born = 0.0
        self._color = CYAN

    def pulse(self, notes, velocity: int = 127, now: float | None = None) -> None:
        if not notes:
            return
        now = time.time() if now is None else now
        v = max(0.0, min(1.0, int(velocity) / 127.0))
        color = color_for_note(int(notes[0]))
        with self._lock:
            self._color = color
            self._peak = 0.40 + 0.60 * v
            self._born = now
            self._on = True

    def release(self, now: float | None = None) -> None:
        """STOP/END: el brillo que haya empieza a fundirse desde ya."""
        now = time.time() if now is None else now
        with self._lock:
            if not self._on:
                return
            age = max(0.0, now - self._born)
            self._peak = self._peak * math.exp(-age / TAU)
            self._born = now

    def clear(self) -> None:
        with self._lock:
            self._on = False
            self._peak = 0.0

    def level(self, now: float | None = None) -> float:
        amp, _color = self._sample(now)
        return amp

    def columns(self, now: float | None = None) -> np.ndarray | None:
        """RGBA 0–1 por columna, índice 0 = borde exterior. None si está apagado."""
        amp, color = self._sample(now)
        if amp < 0.02:
            return None
        return _rgba(amp, color)

    def blit_rgb565(self, frame: bytes, now: float) -> bytes:
        cols = self.columns(now)
        if cols is None or len(frame) != WIDTH * HEIGHT * 2:
            return frame
        arr = np.frombuffer(bytearray(frame), dtype="<u2").reshape(HEIGHT, WIDTH)
        _paint(arr[:, :MARGIN], cols, outer_left=True)
        _paint(arr[:, WIDTH - MARGIN:], cols, outer_left=False)
        return arr.astype("<u2").tobytes()

    def _sample(self, now: float | None) -> tuple[float, tuple[int, int, int]]:
        with self._lock:
            color = self._color
            if not self._on:
                return 0.0, color
            now = time.time() if now is None else now
            age = max(0.0, now - self._born)
            amp = self._peak * math.exp(-age / TAU)
            if amp < 0.02:
                self._on = False
                return 0.0, color
            return amp, color
