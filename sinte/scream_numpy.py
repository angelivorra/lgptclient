"""Filtro scream en arrays numpy, paralelo al lazo de `Voice._render_filter`.

El scream del engine es un IIR con saturación en cada muestra: no se puede
vectorizar (cada salida depende del estado ya recortado). Este módulo hace
la misma cuenta sobre numpy; si hay numba, el lazo se compila.

No sustituye `_render_filter`. El engine solo lo usa en modo `scream`
cuando `enabled()` es verdadero (`SCREAM_NUMPY=1` fuerza; `=0` apaga;
sin variable: se enciende si numba compiló).
"""

from __future__ import annotations

import os
from typing import Optional

import numpy as np

_ENV = "SCREAM_NUMPY"

# Mismo lazo que Voice._render_filter (scream=True). Numba lo baja a
# máquina; sin numba se usa el fallback Python, idéntico en float64.
_loop = None
_loop_impl = "python"


def _filter_loop(col, sp, hg, dl, mix_inv, f_mix, reso, freq, dirt, scream):
    n = col.shape[0]
    for i in range(n):
        s = col[i]
        lpin = s * mix_inv
        hpin = -s * f_mix
        if scream:
            if sp > 1.0:
                sp = 2.0 / 3.0
            elif sp < -1.0:
                sp = -2.0 / 3.0
            sp *= dirt
        sp = sp * reso + (lpin - hg) * freq
        if sp > 1.0:
            sp = 1.0
        elif sp < -1.0:
            sp = -1.0
        hg = hg + sp + dl - hpin
        if hg > 1.0:
            hg = 1.0
        elif hg < -1.0:
            hg = -1.0
        dl = hpin
        col[i] = hg
    return sp, hg, dl


def _bind_loop():
    global _loop, _loop_impl
    try:
        from numba import njit
        compiled = njit(cache=True)(_filter_loop)
        probe = np.zeros(8, dtype=np.float64)
        compiled(probe, 0.0, 0.0, 0.0, 1.0, 0.0, 0.5, 0.2, 100.0, True)
        _loop = compiled
        _loop_impl = "numba"
    except Exception:
        _loop = _filter_loop
        _loop_impl = "python"


_bind_loop()


def enabled() -> bool:
    v = os.environ.get(_ENV, "").strip().lower()
    if v in ("0", "false", "off", "no"):
        return False
    if v in ("1", "true", "on", "yes"):
        return True
    return _loop_impl == "numba"


def coeffs(cut: float, reso_base: float) -> tuple[float, float, float]:
    """freq, reso y dirt: las mismas fórmulas que `_render_filter`."""
    cut = min(max(float(cut), 0.0), 1.0)
    freq = cut * cut
    reso = 1.0 - (1.0 - float(reso_base)) ** 3
    dirt = 100.0 * (1.0 - cut) + 5000.0 * cut
    return freq, reso, dirt


def filter_block(
    x: np.ndarray,
    *,
    cut: float,
    reso_base: float,
    mix: float,
    scream: bool = True,
    speed: Optional[list[float]] = None,
    height: Optional[list[float]] = None,
    delay: Optional[list[float]] = None,
) -> tuple[np.ndarray, list[float], list[float], list[float]]:
    """Filtra un bloque `(n, canales)` float32. Devuelve copia + estado.

    `speed`/`height`/`delay` son el estado por canal (como en Voice).
    """
    y = np.array(x, dtype=np.float32, copy=True)
    n_ch = 1 if y.ndim == 1 else y.shape[1]
    if y.ndim == 1:
        y = y[:, None]
    sp = list(speed) if speed is not None else [0.0] * n_ch
    hg = list(height) if height is not None else [0.0] * n_ch
    dl = list(delay) if delay is not None else [0.0] * n_ch
    while len(sp) < n_ch:
        sp.append(0.0)
        hg.append(0.0)
        dl.append(0.0)
    freq, reso, dirt = coeffs(cut, reso_base)
    mix = float(mix)
    mix_inv = 1.0 - mix
    apply_scream = bool(scream)
    for c in range(n_ch):
        col = y[:, c].astype(np.float64, copy=True)
        sp[c], hg[c], dl[c] = _loop(
            col, float(sp[c]), float(hg[c]), float(dl[c]),
            mix_inv, mix, reso, freq, dirt, apply_scream,
        )
        y[:, c] = col.astype(np.float32)
    return y, sp, hg, dl


def apply(x: np.ndarray, voice) -> None:
    """In-place sobre el buffer de una Voice, mismo contrato que `_render_filter`."""
    cut = min(max(voice.f_cut_base * voice.cc_cutoff, 0.0), 1.0)
    y, sp, hg, dl = filter_block(
        x,
        cut=cut,
        reso_base=voice.f_reso_base,
        mix=voice.f_mix,
        scream=voice.f_scream,
        speed=voice.f_speed,
        height=voice.f_height,
        delay=voice.f_delay,
    )
    x[:] = y
    voice.f_speed = sp
    voice.f_height = hg
    voice.f_delay = dl
