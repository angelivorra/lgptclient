"""Chispazo estampado encima del live.

CC 001/001 (en gobiernoIA, B4:08 y el resto de 01) no pone el 404:
dispara este sprite, teñido con un neón y en un sitio al azar. El
sprite es un estallido del mp4 de referencia, sin el verde de fondo.
Dura lo que duran sus frames a 30 fps y no usa el hold de las imágenes.
"""
from __future__ import annotations

import random
import threading
import time
from pathlib import Path

import numpy as np

from ribbon import HEIGHT, WIDTH

SPARK_CC = 1
SPARK_VALUE = 1
SPARK_FPS = 30
KEY_THRESHOLD = 36
KEY_GAIN = 3

# Misma paleta que lyric_render.TEMAS_ROBOT.
NEON_COLORS = (
    (0, 229, 255),    # cian
    (57, 255, 20),    # verde
    (255, 176, 0),    # ámbar
    (255, 45, 45),    # rojo
    (255, 0, 200),    # magenta
    (120, 200, 255),  # hielo
    (180, 120, 255),  # violeta
)

_ASSET = Path(__file__).with_name("spark_hit.npz")


def key_alpha(rgb: np.ndarray, threshold: int = KEY_THRESHOLD,
              gain: int = KEY_GAIN) -> np.ndarray:
    """Verde de croma → alpha 0. La chispa es el rojo (y el azul) por encima."""
    r = rgb[:, :, 0].astype(np.int16)
    b = rgb[:, :, 2].astype(np.int16)
    return np.clip((np.maximum(r, b) - threshold) * gain, 0, 255).astype(np.uint8)


def load_alpha(path: Path | None = None) -> np.ndarray:
    path = Path(path) if path is not None else _ASSET
    if not path.is_file():
        return np.zeros((0, 1, 1), dtype=np.uint8)
    with np.load(path) as data:
        alpha = np.asarray(data["alpha"], dtype=np.uint8)
    if alpha.ndim != 3 or alpha.shape[0] == 0:
        return np.zeros((0, 1, 1), dtype=np.uint8)
    return alpha


def _stamp(view: np.ndarray, alpha: np.ndarray, color: tuple[int, int, int]) -> None:
    """Suma el sprite (alpha 0–255) sobre una ventana RGB565."""
    a = alpha.astype(np.float32) * (1.0 / 255.0)
    r = ((view >> 11) & 31).astype(np.float32)
    g = ((view >> 5) & 63).astype(np.float32)
    b = (view & 31).astype(np.float32)
    r += (color[0] * (31.0 / 255.0)) * a
    g += (color[1] * (63.0 / 255.0)) * a
    b += (color[2] * (31.0 / 255.0)) * a
    np.minimum(31.0, r, out=r)
    np.minimum(63.0, g, out=g)
    np.minimum(31.0, b, out=b)
    view[:, :] = (
        (r.astype(np.uint16) << 11)
        | (g.astype(np.uint16) << 5)
        | b.astype(np.uint16)
    )


class SparkHit:
    """Uno o dos estallidos a la vez. El render solo toca el rectángulo."""

    def __init__(self, alpha: np.ndarray | None = None):
        self._alpha = load_alpha() if alpha is None else np.asarray(alpha, dtype=np.uint8)
        self._lock = threading.Lock()
        self._hits: list[tuple[float, int, int, tuple[int, int, int]]] = []

    @property
    def frames(self) -> int:
        return int(self._alpha.shape[0]) if self._alpha.ndim == 3 else 0

    @property
    def size(self) -> tuple[int, int]:
        if self.frames == 0:
            return (0, 0)
        return int(self._alpha.shape[1]), int(self._alpha.shape[2])

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()

    def trigger(self, now: float | None = None,
                rng: random.Random | None = None) -> bool:
        if self.frames == 0:
            return False
        h, w = self.size
        pick = rng if rng is not None else random
        x = pick.randint(0, max(0, WIDTH - w))
        y = pick.randint(0, max(0, HEIGHT - h))
        color = pick.choice(NEON_COLORS)
        t0 = time.time() if now is None else now
        with self._lock:
            self._hits.append((t0, x, y, color))
            if len(self._hits) > 4:
                self._hits = self._hits[-4:]
        return True

    def pending(self, now: float | None = None) -> int:
        return len(self.active_hits(now))

    def active_hits(self, now: float | None = None
                    ) -> list[tuple[int, int, int, tuple[int, int, int]]]:
        """(frame, x, y, color) de los que siguen en pantalla."""
        now = time.time() if now is None else now
        with self._lock:
            live = []
            out = []
            for t0, x, y, color in self._hits:
                idx = self._index(now, t0)
                if idx < self.frames:
                    live.append((t0, x, y, color))
                    out.append((max(0, idx), x, y, color))
            self._hits = live
        return out

    def frame_rgba(self, index: int, color: tuple[int, int, int]
                   ) -> tuple[bytes, int, int] | None:
        """RGBA (el color en RGB, la chispa en alpha) de un frame."""
        if self.frames == 0 or index < 0 or index >= self.frames:
            return None
        alpha = self._alpha[index]
        h, w = alpha.shape
        rgba = np.empty((h, w, 4), dtype=np.uint8)
        rgba[:, :, 0] = color[0]
        rgba[:, :, 1] = color[1]
        rgba[:, :, 2] = color[2]
        rgba[:, :, 3] = alpha
        return rgba.tobytes(), w, h

    def places(self) -> list[tuple[int, int, tuple[int, int, int]]]:
        with self._lock:
            return [(x, y, color) for _t, x, y, color in self._hits]

    def _index(self, now: float, t0: float) -> int:
        return int((now - t0) * SPARK_FPS)

    def blit_rgb565(self, frame: bytes, now: float | None = None) -> bytes:
        now = time.time() if now is None else now
        if len(frame) != WIDTH * HEIGHT * 2 or self.frames == 0:
            return frame
        with self._lock:
            live = []
            for hit in self._hits:
                if self._index(now, hit[0]) < self.frames:
                    live.append(hit)
            self._hits = live
            snapshot = list(live)
        if not snapshot:
            return frame
        arr = np.frombuffer(bytearray(frame), dtype="<u2").reshape(HEIGHT, WIDTH)
        for t0, x, y, color in snapshot:
            idx = self._index(now, t0)
            if idx < 0:
                idx = 0
            alpha = self._alpha[idx]
            h, w = alpha.shape
            _stamp(arr[y:y + h, x:x + w], alpha, color)
        return arr.astype("<u2").tobytes()
