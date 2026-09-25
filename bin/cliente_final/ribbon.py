"""Línea de glow que cruza el horizonte del fondo.

Fuente única para las robotas (`display_executor`) y Robotracker
(`robotracker2/shared_visuals.py` → pantalla LIVE). Un cambio aquí
se ve en los dos.

La línea en reposo avanza de izquierda a derecha. Cada frame una onda
al BPM reescribe el path visible (800 senos; las Pi pueden). El buffer
de reposo no se toca. Cada evento es una
figura (forma + color) que nace a la izquierda a tamaño 0, crece
apartando la línea y viaja con ella. Hoy el bombo es un cuadrado negro
rodeado por el trazo; las cajas son círculos (azul caja1, verde caja2).
Añadir un kind en FIGURES basta para otro gesto.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Dict, List

import numpy as np

WIDTH = 800
HEIGHT = 480

BAND_CENTER = 240
BAND_HALF = 36

# Compat: pulse() sigue anotando env por si un reactor antiguo lo lee.
REACTORS: Dict[str, Dict[str, float]] = {
    "kick": {"amp": -48.0, "half_life": 0.16, "glow": 1.00},
    "snare": {"amp": -16.0, "half_life": 0.09, "glow": 0.70},
    "snare1": {"amp": -16.0, "half_life": 0.09, "glow": 0.70},
    "snare2": {"amp": -16.0, "half_life": 0.09, "glow": 0.70},
    "crash": {"amp": 10.0, "half_life": 0.28, "glow": 0.90},
    "button": {"amp": 8.0, "half_life": 0.16, "glow": 0.55},
}

# Figura por tipo de evento. fill/outline en RGB 0-255.
# Caja1 azul / caja2 verde: mismos colores que el monitor MIDI.
_SNARE_CIRCLE = {"shape": "circle", "fill": (0, 0, 0), "size": 22.0, "grow_s": 0.14}
FIGURES: Dict[str, Dict] = {
    "kick": {
        "shape": "square",
        "fill": (0, 0, 0),
        "outline": (0, 230, 255),
        "size": 34.0,
        "grow_s": 0.22,
    },
    "snare1": {**_SNARE_CIRCLE, "outline": (52, 170, 255)},
    "snare2": {**_SNARE_CIRCLE, "outline": (46, 255, 113)},
    "snare": {**_SNARE_CIRCLE, "outline": (52, 170, 255)},
}

_KERNEL = np.array(
    [0.08, 0.18, 0.35, 0.60, 0.85, 1.00, 0.85, 0.60, 0.35, 0.18, 0.08],
    dtype=np.float32,
)
_KERNEL_MID = len(_KERNEL) // 2

_LINE_R, _LINE_G, _LINE_B = 0, 230, 255

# El overlay tapa la línea solo en las columnas con tinta (ojos, trazo).
# Un poco de dilate cierra pupilas; el hueco entre sprites se deja ver.
_OVERLAY_BAND = 56
_OVERLAY_DILATE = 8


def overlay_block_cols(fg: bytes, width: int = WIDTH,
                       height: int = HEIGHT) -> np.ndarray:
    """True = esa columna la cubre el overlay; la línea no pinta ahí."""
    block = np.zeros(width, dtype=bool)
    if len(fg) != width * height * 2:
        return block
    pix = np.frombuffer(fg, dtype="<u2").reshape(height, width).astype(np.uint32)
    r = (pix >> 11) & 0x1F
    g5 = (pix >> 5) & 0x3F
    b = pix & 0x1F
    lum = r + g5 + b
    opaque = ~((lum <= 6) | ((b > r) & (lum <= 25)))
    y0 = max(0, BAND_CENTER - _OVERLAY_BAND)
    y1 = min(height, BAND_CENTER + _OVERLAY_BAND)
    cols = opaque[y0:y1].any(axis=0)
    if not cols.any():
        return block
    k = _OVERLAY_DILATE
    acc = cols.copy()
    for d in range(1, k + 1):
        acc[d:] |= cols[:-d]
        acc[:-d] |= cols[d:]
    return acc

# Onda que reescribe el path visible cada frame (800 senos; barato en la Pi).
WAVE_LAMBDA = 96.0
WAVE_AMP_REST = 2.8
WAVE_AMP_BEAT = 11.0

# Misma curva que el slideshow (display_executor.FONDO_BPM_CURVE).
# El knob solo sube el tempo un 12 %; **8 lo convierte en ~2.5× de avance,
# igual que los frames del fondo. Al tempo de la canción la velocidad
# sigue siendo 130 px/s a 120 BPM.
SPEED_AT_120 = 130.0
BPM_CURVE = 8


@dataclass
class RibbonFigure:
    kind: str
    x: float
    born: float
    vel: float


class FondoRibbon:
    """Línea de reposo + figuras que viajan de izquierda a derecha."""

    def __init__(self, width: int = WIDTH, center: int = BAND_CENTER):
        self.width = width
        self.center = center
        self.offset = np.zeros(width, dtype=np.float32)
        self.bright = np.full(width, 0.50, dtype=np.float32)
        self.env: Dict[str, float] = {k: 0.0 for k in REACTORS}
        self.bpm = 120.0
        self._base_bpm = 0.0  # 0 = el próximo set_bpm fija el tempo de la canción
        self._scroll_acc = 0.0
        self._last = 0.0
        self._beat_t0: float | None = None
        self._lock = threading.Lock()
        self._figures: List[RibbonFigure] = []
        self._xs = np.arange(width, dtype=np.float32)
        self._wave = np.zeros(width, dtype=np.float32)
        self._wave_now: float | None = None

    def pulse(self, kind: str, velocity: int = 127) -> None:
        """Nace una figura a la izquierda, tamaño 0, en ese punto de la línea."""
        v = max(0.25, min(1.0, velocity / 127.0))
        born = self._last if self._last > 0 else time.monotonic()
        with self._lock:
            if kind not in self.env:
                self.env[kind] = 0.0
            self.env[kind] = min(1.0, self.env[kind] + v)
            if kind in FIGURES:
                self._figures.append(RibbonFigure(kind, x=0.0, born=born, vel=v))

    def path_ys(self, now: float | None = None) -> np.ndarray:
        """Y en framebuffer (0 arriba): reposo + onda al BPM (reescribe el path)."""
        now = self._last if now is None else now
        return self.center + self.offset + self._wave_ys(now)

    def snapshot_figures(self, now: float | None = None) -> List[dict]:
        """Estado dibujable de las figuras (para LIVE y blit)."""
        now = self._last if now is None else now
        with self._lock:
            figs = list(self._figures)
        ys = self.path_ys(now)
        out = []
        for fig in figs:
            spec = FIGURES.get(fig.kind, FIGURES["kick"])
            grow_s = float(spec["grow_s"])
            u = 0.0 if grow_s <= 0 else min(1.0, max(0.0, (now - fig.born) / grow_s))
            grow = 1.0 - (1.0 - u) ** 2
            side = float(spec["size"]) * grow * fig.vel
            xi = min(self.width - 1, max(0, int(round(fig.x))))
            out.append({
                "kind": fig.kind,
                "shape": spec["shape"],
                "x": fig.x,
                "y": float(ys[xi]),
                "side": side,
                "fill": spec["fill"],
                "outline": spec["outline"],
            })
        return out

    def set_bpm(self, bpm: float, base: float | None = None) -> None:
        """Tempo audible. `base` es el de la canción (knob abajo).

        Sin `base`, el primero que llega se queda como referencia — el
        sinte manda ese valor antes que el tempo ya acelerado por el knob.
        """
        if bpm <= 0:
            return
        bpm = float(bpm)
        if base is not None and base > 0:
            self._base_bpm = float(base)
        elif self._base_bpm <= 0:
            self._base_bpm = bpm
        if bpm == self.bpm:
            return
        now = self._last if self._last > 0 else time.monotonic()
        if self._beat_t0 is not None:
            old_period = 60.0 / max(self.bpm, 1.0)
            phase = (now - self._beat_t0) / old_period
            self._beat_t0 = now - (phase % 1.0) * (60.0 / bpm)
        self.bpm = bpm

    def reset_tempo_base(self) -> None:
        """La próxima lectura de BPM vuelve a ser el tempo de la canción."""
        self._base_bpm = 0.0

    def reset_beat(self, now: float | None = None) -> None:
        """Alinea el pulso al instante actual (START de la canción)."""
        self._beat_t0 = (
            now if now is not None
            else (self._last if self._last > 0 else time.monotonic())
        )

    def beat_pulse(self, now: float | None = None) -> float:
        """0 en el valle, 1 en el golpe del tempo. No se hornea en el historial."""
        now = self._last if now is None else now
        if now <= 0:
            now = time.monotonic()
        if self._beat_t0 is None:
            self._beat_t0 = now
        period = 60.0 / max(self.bpm, 1.0)
        frac = ((now - self._beat_t0) / period) % 1.0
        return math.exp(-frac / 0.16)

    def _beats(self, now: float) -> float:
        if self._beat_t0 is None:
            self._beat_t0 = now
        return (now - self._beat_t0) * self.bpm / 60.0

    def _wave_ys(self, now: float) -> np.ndarray:
        """Deforma las 800 columnas; el buffer de reposo no se toca."""
        if now <= 0:
            return self._wave
        if self._wave_now == now:
            return self._wave
        amp = WAVE_AMP_REST + WAVE_AMP_BEAT * self.beat_pulse(now)
        np.sin(
            (2.0 * math.pi) * (self._xs / WAVE_LAMBDA - self._beats(now)),
            out=self._wave,
        )
        self._wave *= amp
        self._wave_now = now
        return self._wave

    @property
    def speed_px_s(self) -> float:
        """Avance de la línea. Al tempo base, lineal con el BPM; el knob
        aplica la misma curva que el slideshow."""
        base = self._base_bpm if self._base_bpm > 0 else self.bpm
        ratio = self.bpm / max(base, 1.0)
        return SPEED_AT_120 * (base / 120.0) * (ratio ** BPM_CURVE)

    def _sample(self, t: float) -> tuple[float, float]:
        return 2.2 * math.sin(t * 1.7), 0.50

    def step(self, now: float) -> int:
        if self._last <= 0:
            self._last = now
            return 0
        dt = min(0.08, max(0.0, now - self._last))
        self._last = now
        speed = self.speed_px_s
        self._scroll_acc += speed * dt
        n = int(self._scroll_acc)
        if n <= 0:
            return 0
        self._scroll_acc -= n
        n = min(n, self.width)
        self.offset[n:] = self.offset[:-n]
        self.bright[n:] = self.bright[:-n]
        for i in range(n):
            t = now - (n - 1 - i) / max(speed, 1.0)
            off, glow = self._sample(t)
            self.offset[i] = off
            self.bright[i] = glow
        max_side = max(float(s["size"]) for s in FIGURES.values())
        with self._lock:
            for fig in self._figures:
                fig.x += n
            self._figures = [
                fig for fig in self._figures
                if fig.x - max_side < self.width
            ]
        return n

    def _gap_mask(self, now: float) -> np.ndarray:
        """True = esa columna la ocupa una figura (la línea de reposo calla)."""
        mask = np.zeros(self.width, dtype=bool)
        for fig in self.snapshot_figures(now):
            half = fig["side"] / 2.0
            if half < 0.5:
                continue
            a = max(0, int(math.floor(fig["x"] - half)))
            b = min(self.width, int(math.ceil(fig["x"] + half)) + 1)
            mask[a:b] = True
        return mask

    def blit_rgb565(self, frame: bytes, now: float,
                    block_cols: np.ndarray | None = None) -> bytes:
        self.step(now)
        if len(frame) != self.width * HEIGHT * 2:
            return frame
        arr = np.frombuffer(bytearray(frame), dtype="<u2").reshape(HEIGHT, self.width)
        r = (arr >> 11) & 31
        g = (arr >> 5) & 63
        b = arr & 31
        self._blit_line(r, g, b, now, block_cols)
        self._blit_figures(arr, r, g, b, now, block_cols)
        arr[:, :] = (r << 11) | (g << 5) | b
        return arr.astype("<u2").tobytes()

    def _blit_line(self, r, g, b, now: float,
                   block_cols: np.ndarray | None = None) -> None:
        ys = np.clip(
            np.rint(self.path_ys(now)).astype(np.int32),
            _KERNEL_MID,
            HEIGHT - 1 - _KERNEL_MID,
        )
        gap = self._gap_mask(now)
        add_r = (_LINE_R / 255.0) * 31.0
        add_g = (_LINE_G / 255.0) * 63.0
        add_b = (_LINE_B / 255.0) * 31.0
        glow = self.bright * (1.0 + 1.15 * self.beat_pulse(now))
        xs = np.arange(self.width, dtype=np.int32)
        live = ~gap
        if block_cols is not None:
            live = live & ~np.asarray(block_cols, dtype=bool)
        if not live.any():
            return
        xs_l = xs[live]
        for k, w in enumerate(_KERNEL):
            rows = ys[live] + (k - _KERNEL_MID)
            amp = glow[live] * w
            r[rows, xs_l] = np.minimum(31, r[rows, xs_l] + (add_r * amp).astype(np.uint16))
            g[rows, xs_l] = np.minimum(63, g[rows, xs_l] + (add_g * amp).astype(np.uint16))
            b[rows, xs_l] = np.minimum(31, b[rows, xs_l] + (add_b * amp).astype(np.uint16))

    def _blit_figures(self, arr, r, g, b, now: float,
                      block_cols: np.ndarray | None = None) -> None:
        for fig in self.snapshot_figures(now):
            if fig["side"] < 1.0:
                continue
            if block_cols is not None:
                xi = min(self.width - 1, max(0, int(round(fig["x"]))))
                if block_cols[xi]:
                    continue
            if fig["shape"] == "circle":
                self._blit_circle(r, g, b, fig)
            else:
                self._blit_square(r, g, b, fig)

    def _figure_box(self, fig: dict) -> tuple[int, int, int, int] | None:
        half = fig["side"] / 2.0
        x0 = max(0, int(math.floor(fig["x"] - half)))
        x1 = min(self.width - 1, int(math.ceil(fig["x"] + half)))
        y0 = max(0, int(math.floor(fig["y"] - half)))
        y1 = min(HEIGHT - 1, int(math.ceil(fig["y"] + half)))
        if x1 < x0 or y1 < y0:
            return None
        return x0, x1, y0, y1

    def _blit_square(self, r, g, b, fig: dict) -> None:
        box = self._figure_box(fig)
        if box is None:
            return
        x0, x1, y0, y1 = box
        fr, fg, fb = fig["fill"]
        r[y0:y1 + 1, x0:x1 + 1] = fr >> 3
        g[y0:y1 + 1, x0:x1 + 1] = fg >> 2
        b[y0:y1 + 1, x0:x1 + 1] = fb >> 3
        or_, og, ob = fig["outline"]
        or5, og6, ob5 = or_ >> 3, og >> 2, ob >> 3
        r[y0, x0:x1 + 1] = or5
        g[y0, x0:x1 + 1] = og6
        b[y0, x0:x1 + 1] = ob5
        r[y1, x0:x1 + 1] = or5
        g[y1, x0:x1 + 1] = og6
        b[y1, x0:x1 + 1] = ob5
        r[y0:y1 + 1, x0] = or5
        g[y0:y1 + 1, x0] = og6
        b[y0:y1 + 1, x0] = ob5
        r[y0:y1 + 1, x1] = or5
        g[y0:y1 + 1, x1] = og6
        b[y0:y1 + 1, x1] = ob5

    def _blit_circle(self, r, g, b, fig: dict) -> None:
        box = self._figure_box(fig)
        if box is None:
            return
        x0, x1, y0, y1 = box
        rad = fig["side"] / 2.0
        yy = np.arange(y0, y1 + 1, dtype=np.float32)[:, None]
        xx = np.arange(x0, x1 + 1, dtype=np.float32)[None, :]
        dist = np.sqrt((xx - fig["x"]) ** 2 + (yy - fig["y"]) ** 2)
        interior = dist <= max(0.0, rad - 0.65)
        ring = (dist <= rad + 0.55) & (dist >= max(0.0, rad - 0.65))
        sl_r = r[y0:y1 + 1, x0:x1 + 1]
        sl_g = g[y0:y1 + 1, x0:x1 + 1]
        sl_b = b[y0:y1 + 1, x0:x1 + 1]
        fr, fg, fb = fig["fill"]
        sl_r[interior] = fr >> 3
        sl_g[interior] = fg >> 2
        sl_b[interior] = fb >> 3
        or_, og, ob = fig["outline"]
        sl_r[ring] = or_ >> 3
        sl_g[ring] = og >> 2
        sl_b[ring] = ob >> 3
