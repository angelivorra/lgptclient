"""Chispazos robóticos: cuatro animaciones cortas, cada una en un sitio.

Duran menos que la cuenta atrás (10 frames a 30 fps). Fondo con alpha 0.
"""
from __future__ import annotations

import math
import random
from typing import List, Sequence, Tuple

import numpy as np
from PIL import Image

SCREEN_W = 800
SCREEN_H = 480

SPARK_FPS = 30
SPARK_FRAMES = 6
# Un compás de gobiernoIA: 16 filas × 15/180 s = 40 frames a 30 fps.
SHUTDOWN_FRAMES = 40
SHUTDOWN_SLOT = "012"
# Gris por encima del umbral del composite (lum<=6 es el slideshow).
_OFF = (18, 18, 18, 255)

# slot = carpeta images/003/NNN. El número ocupa 10 frames; esto, 6.
SPARKS = (
    {"slot": "008", "kind": "radial", "origin": (140, 78),
     "color": (0, 229, 255), "seed": 8},
    {"slot": "009", "kind": "slash", "origin": (660, 92),
     "color": (255, 0, 200), "seed": 9},
    {"slot": "010", "kind": "weld", "origin": (160, 400),
     "color": (255, 176, 0), "seed": 10},
    {"slot": "011", "kind": "scan", "origin": (710, 320),
     "color": (57, 255, 20), "seed": 11},
)

Point = Tuple[float, float]
Rgb = Tuple[int, int, int]


def _core(color: Rgb) -> Rgb:
    return tuple(min(255, c // 3 + 190) for c in color)  # type: ignore[return-value]


def _line(a: Point, b: Point) -> List[Tuple[int, int]]:
    x0, y0 = int(round(a[0])), int(round(a[1]))
    x1, y1 = int(round(b[0])), int(round(b[1]))
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx - dy
    pts = []
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return pts


def _poly(points: Sequence[Point], frac: float) -> List[Tuple[int, int]]:
    pts: List[Tuple[int, int]] = []
    for a, b in zip(points, points[1:]):
        pts.extend(_line(a, b)[:-1])
    if points:
        pts.append((int(round(points[-1][0])), int(round(points[-1][1]))))
    if not pts:
        return pts
    n = max(1, int(round(len(pts) * frac)))
    return pts[:n]


def _stamp(arr: np.ndarray, x: int, y: int, rgb: Rgb, r: int) -> None:
    h, w = arr.shape[:2]
    for yy in range(y - r, y + r + 1):
        if yy < 0 or yy >= h:
            continue
        for xx in range(x - r, x + r + 1):
            if xx < 0 or xx >= w:
                continue
            pix = arr[yy, xx]
            pix[0] = max(int(pix[0]), rgb[0])
            pix[1] = max(int(pix[1]), rgb[1])
            pix[2] = max(int(pix[2]), rgb[2])
            pix[3] = 255


def _paint(arr: np.ndarray, pts: Sequence[Tuple[int, int]], color: Rgb,
           core: Rgb, dash: int, thick: int) -> None:
    for i, (x, y) in enumerate(pts):
        if dash and (i // dash) % 2 == 1:
            continue
        _stamp(arr, x, y, color, thick)
        if thick > 0:
            _stamp(arr, x, y, core, 0)


def _square(arr: np.ndarray, x: int, y: int, color: Rgb, core: Rgb, size: int) -> None:
    half = size // 2
    for yy in range(int(y) - half, int(y) + half + 1):
        for xx in range(int(x) - half, int(x) + half + 1):
            _stamp(arr, xx, yy, color, 0)
    _stamp(arr, int(x), int(y), core, 0)


def _rays(origin: Point, seed: int, n: int, length: float) -> List[List[Point]]:
    rng = random.Random(seed)
    ox, oy = origin
    out = []
    for i in range(n):
        ang = (i / n) * math.tau + rng.uniform(-0.35, 0.35)
        ln = length * rng.uniform(0.65, 1.0)
        kink_t = rng.uniform(0.4, 0.62)
        kink = rng.uniform(-1.0, 1.0)
        mx = ox + math.cos(ang) * ln * kink_t
        my = oy + math.sin(ang) * ln * kink_t
        ex = mx + math.cos(ang + kink) * ln * (1 - kink_t)
        ey = my + math.sin(ang + kink) * ln * (1 - kink_t)
        out.append([(ox, oy), (mx, my), (ex, ey)])
    return out


def _motif(kind: str, origin: Point, seed: int) -> List[List[Point]]:
    ox, oy = origin
    if kind == "radial":
        return _rays(origin, seed, 6, 72)
    if kind == "slash":
        return [
            [(ox - 58, oy - 36), (ox, oy), (ox + 64, oy + 28)],
            [(ox - 40, oy + 44), (ox + 6, oy - 4), (ox + 52, oy - 40)],
            [(ox, oy), (ox + 18, oy - 22), (ox + 22, oy + 8)],
        ]
    if kind == "weld":
        return [
            [(ox, oy + 18), (ox, oy), (ox + 4, oy - 70)],
            [(ox, oy - 16), (ox - 28, oy - 10), (ox - 34, oy + 6)],
            [(ox, oy - 36), (ox + 26, oy - 30), (ox + 30, oy - 14)],
            [(ox, oy - 52), (ox - 16, oy - 60), (ox - 8, oy - 74)],
        ]
    # scan: tres segmentos horizontales y chispas hacia abajo
    return [
        [(ox - 70, oy), (ox - 24, oy - 8), (ox + 18, oy + 4), (ox + 62, oy - 6)],
        [(ox - 20, oy), (ox - 8, oy + 22), (ox + 4, oy + 36)],
        [(ox + 16, oy + 4), (ox + 28, oy + 20), (ox + 22, oy + 40)],
        [(ox + 40, oy - 2), (ox + 48, oy + 16), (ox + 58, oy + 28)],
    ]


def spark_frames(kind: str, origin: Point, color: Rgb, seed: int,
                 n: int = SPARK_FRAMES,
                 width: int = SCREEN_W, height: int = SCREEN_H) -> List[Image.Image]:
    """Un chispazo. El último frame está vacío."""
    core = _core(color)
    chains = _motif(kind, origin, seed)
    # Crecer, aguantar un instante, romperse en tramos, dejar solo las puntas.
    plan = (
        {"frac": 0.45, "dash": 0, "thick": 1, "tips": False},
        {"frac": 0.85, "dash": 0, "thick": 1, "tips": False},
        {"frac": 1.0, "dash": 0, "thick": 2, "tips": True},
        {"frac": 1.0, "dash": 7, "thick": 1, "tips": True},
        {"frac": 1.0, "dash": 5, "thick": 0, "tips": True},
    )
    frames = []
    for i in range(n):
        arr = np.zeros((height, width, 4), dtype=np.uint8)
        if i < len(plan):
            step = plan[i]
            for chain in chains:
                pts = _poly(chain, step["frac"])
                _paint(arr, pts, color, core, step["dash"], step["thick"])
                if step["tips"] and pts:
                    _square(arr, pts[-1][0], pts[-1][1], color, core, 5)
            if i < 3:
                _square(arr, origin[0], origin[1], core, (255, 255, 255), 3)
        frames.append(Image.fromarray(arr, "RGBA"))
    return frames


def shutdown_frames(n: int = SHUTDOWN_FRAMES,
                    width: int = SCREEN_W, height: int = SCREEN_H
                    ) -> List[Image.Image]:
    """El monitor se cierra a una línea y se queda apagado el resto del compás."""
    collapse = 14
    shrink = 8
    frames = []
    for i in range(n):
        arr = np.empty((height, width, 4), dtype=np.uint8)
        arr[:, :] = _OFF
        cy = height // 2
        if i < collapse:
            t = i / (collapse - 1)
            half = max(1, int(round((height / 2) * (1 - t) ** 2)))
            y0, y1 = cy - half, cy + half + 1
            arr[y0:y1, :, 0] = 40
            arr[y0:y1, :, 1] = 220
            arr[y0:y1, :, 2] = 160
            arr[cy - 1:cy + 2, :] = (230, 255, 255, 255)
        elif i < collapse + shrink:
            t = (i - collapse + 1) / shrink
            halfw = max(0, int(round((width / 2) * (1 - t))))
            if halfw > 0:
                x0, x1 = width // 2 - halfw, width // 2 + halfw
                arr[cy - 1:cy + 2, x0:x1] = (210, 255, 255, 255)
        frames.append(Image.fromarray(arr, "RGBA"))
    return frames
