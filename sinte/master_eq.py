"""EQ gráfico de 7 bandas para la mezcla final.

Nativo (biquads RBJ), el mismo en sinte, mixer, Pi y Odin: no depende de
LADSPA. Se guarda por canción en robotraca.json (`eq`: 7 dB). Plano = no
hace nada (no gasta CPU).
"""

from __future__ import annotations

import math

import numpy as np

EQ_FREQS = (60.0, 150.0, 400.0, 1000.0, 2500.0, 6000.0, 12000.0)
EQ_LABELS = ("60", "150", "400", "1k", "2k5", "6k", "12k")
EQ_BANDS = 7
EQ_MIN_DB = -12.0
EQ_MAX_DB = 12.0
EQ_Q = 1.2
_FLAT = 0.05          # por debajo no se aplica la banda


def parse_eq(raw) -> list[float]:
    """Lista de 7 dB desde el JSON (o plano si falta / es inválido)."""
    out = [0.0] * EQ_BANDS
    if not isinstance(raw, (list, tuple)):
        return out
    for i, v in enumerate(raw[:EQ_BANDS]):
        try:
            out[i] = max(EQ_MIN_DB, min(EQ_MAX_DB, float(v)))
        except (TypeError, ValueError):
            pass
    return out


def eq_to_cfg(gains) -> list[float] | None:
    """Para el JSON: None si está plano (no ensucia el fichero)."""
    g = parse_eq(gains)
    if all(abs(x) < _FLAT for x in g):
        return None
    return [round(x, 1) for x in g]


def _peaking_coeff(sr: float, freq: float, db: float, q: float):
    """RBJ peaking: (b0, b1, b2, a1, a2) ya normalizado por a0."""
    freq = min(freq, sr * 0.45)
    a = 10.0 ** (db / 40.0)
    w0 = 2.0 * math.pi * freq / sr
    alpha = math.sin(w0) / (2.0 * q)
    cosw = math.cos(w0)
    b0 = 1.0 + alpha * a
    b1 = -2.0 * cosw
    b2 = 1.0 - alpha * a
    a0 = 1.0 + alpha / a
    a1 = -2.0 * cosw
    a2 = 1.0 - alpha / a
    inv = 1.0 / a0
    return (b0 * inv, b1 * inv, b2 * inv, a1 * inv, a2 * inv)


def _biquad(x: np.ndarray, b0, b1, b2, a1, a2, z1, z2):
    """IIR in-place sobre un canal. Devuelve el estado."""
    n = x.shape[0]
    for i in range(n):
        xi = float(x[i])
        yi = b0 * xi + z1
        z1 = b1 * xi - a1 * yi + z2
        z2 = b2 * xi - a2 * yi
        x[i] = yi
    return z1, z2


class GraphicEQ:
    """7 picos en cascada, estéreo. `set_gains` es thread-safe a efectos
    prácticos (se leen floats; un bloque a medias usa coeffs viejos)."""

    def __init__(self, sample_rate: int):
        self.sr = float(sample_rate)
        self.gains = [0.0] * EQ_BANDS
        self._coeff = [None] * EQ_BANDS
        # estado (banda, canal) -> (z1, z2)
        self._z = [[(0.0, 0.0), (0.0, 0.0)] for _ in range(EQ_BANDS)]
        self.active = False

    def set_gains(self, gains):
        self.gains = parse_eq(gains)
        self.active = False
        for i, db in enumerate(self.gains):
            if abs(db) < _FLAT:
                self._coeff[i] = None
                self._z[i] = [(0.0, 0.0), (0.0, 0.0)]
                continue
            self._coeff[i] = _peaking_coeff(self.sr, EQ_FREQS[i], db, EQ_Q)
            self.active = True

    def apply(self, buf: np.ndarray):
        """Mezcla estéreo float32 (n, 2), in-place."""
        if not self.active or buf is None or len(buf) == 0:
            return
        for i, coeff in enumerate(self._coeff):
            if coeff is None:
                continue
            b0, b1, b2, a1, a2 = coeff
            z = self._z[i]
            z[0] = _biquad(buf[:, 0], b0, b1, b2, a1, a2, *z[0])
            z[1] = _biquad(buf[:, 1], b0, b1, b2, a1, a2, *z[1])
