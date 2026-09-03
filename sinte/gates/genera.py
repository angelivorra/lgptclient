#!/usr/bin/env python3
"""Bounces de puertas rítmicas sobre el bajo de abducción.

Mismo riff (canal 3) y barrido de 10 s que distorsion_ladspa:

  0-2 s  seco
  2-4 s  fundido al gate
  4-6 s  gate a tope (amount=1)
  6-8 s  fundido a seco
  8-10 s seco

Todo a tempo de la canción (numpy, no LADSPA: esos gates son de umbral).

  sinte/.venv/bin/python gates/genera.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SINTE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SINTE))

from lgpt_engine import Engine  # noqa: E402

SONG = SINTE / "songs" / "lgpt_abduccion"
OUT = Path(__file__).resolve().parent
SEG = 2.0
SECONDS = SEG * 5
BLOCK = 2048
BASS_CH = 2
SMOOTH_S = 0.004       # anti-clic en pulsos/patrones (4 ms)


def _render_dry() -> tuple[np.ndarray, int, float]:
    engine = Engine(SONG)
    engine.master_chain = None
    engine.muted = {i for i in range(8) if i != BASS_CH}
    for ch in engine.channels:
        ch.fx_presence = False
        ch.fx_amounts.clear()
        ch.fx_mix.clear()
    engine.start()
    n = int(SECONDS * engine.sr)
    chunks = []
    got = 0
    while got < n:
        take = min(BLOCK, n - got)
        chunks.append(engine.render(take).copy())
        got += take
    return np.concatenate(chunks, axis=0), engine.sr, float(engine.tempo)


def _envelope(n: int, sr: int) -> np.ndarray:
    t = np.arange(n, dtype=np.float64) / sr
    env = np.zeros(n, dtype=np.float64)
    s = SEG
    m = (t >= s) & (t < 2 * s)
    env[m] = (t[m] - s) / s
    env[(t >= 2 * s) & (t < 3 * s)] = 1.0
    m = (t >= 3 * s) & (t < 4 * s)
    env[m] = 1.0 - (t[m] - 3 * s) / s
    return env.astype(np.float32)


def _smooth(gain: np.ndarray, sr: int) -> np.ndarray:
    k = max(3, int(SMOOTH_S * sr))
    if k % 2 == 0:
        k += 1
    win = np.hanning(k)
    win /= win.sum()
    return np.convolve(gain.astype(np.float64), win, mode="same").astype(np.float32)


def _freq(tempo: float, subdivs: float) -> float:
    """Golpes de gate por segundo: BPM/60 × subdivs por negra."""
    return max(tempo, 1.0) / 60.0 * subdivs


def _phase01(n: int, sr: int, freq: float) -> np.ndarray:
    return (np.arange(n, dtype=np.float64) * freq / sr) % 1.0


def gate_coseno(n, sr, tempo, subdivs=4.0, shape=3.0) -> np.ndarray:
    """El actual trance_gate: ((1+cos)/2)**shape."""
    ph = _phase01(n, sr, _freq(tempo, subdivs)) * 2.0 * np.pi
    env = ((1.0 + np.cos(ph)) * 0.5) ** shape
    return env.astype(np.float32)


def gate_pulso(n, sr, tempo, subdivs=4.0, duty=0.5) -> np.ndarray:
    frac = _phase01(n, sr, _freq(tempo, subdivs))
    raw = (frac < duty).astype(np.float64)
    return _smooth(raw, sr)


def gate_rampa(n, sr, tempo, subdivs=4.0, down=False) -> np.ndarray:
    frac = _phase01(n, sr, _freq(tempo, subdivs))
    env = (1.0 - frac) if down else frac
    return _smooth(env, sr)


def gate_patron(n, sr, tempo, pattern: str, subdivs=4.0) -> np.ndarray:
    """pattern: '1' abierto, '0' cerrado, un carácter por step."""
    bits = np.array([1.0 if c == "1" else 0.0 for c in pattern], dtype=np.float64)
    steps_per_s = _freq(tempo, subdivs)
    step = (np.arange(n, dtype=np.float64) * steps_per_s / sr).astype(int) % len(bits)
    return _smooth(bits[step], sr)


def _aplica(dry: np.ndarray, gain: np.ndarray, stereo: str = "mono") -> np.ndarray:
    """gain (n,) 0-1. stereo=mono aplica a L/R; pingpong usa gain y 1-gain."""
    if stereo == "pingpong":
        g = np.column_stack([gain, 1.0 - gain])
    elif stereo == "pump":
        g = (1.0 - gain)[:, None]
    else:
        g = gain[:, None]
    return dry * g


def _limpia():
    for p in OUT.iterdir():
        if p.name == "genera.py":
            continue
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()


# (carpeta, stem, builder) builder(n, sr, tempo) -> (gain, stereo_mode, nota)
VARIANTES: list[tuple] = []


def _add(carpeta, stem, fn):
    VARIANTES.append((carpeta, stem, fn))


# -- coseno (el de K2 hoy: subdiv 4, shape 3) --------------------------------
for subdivs, tag in ((2.0, "corchea"), (4.0, "semicorchea"), (8.0, "fusa")):
    for shape in (2.0, 3.0, 6.0):
        def _f(n, sr, tempo, sd=subdivs, sh=shape, t=tag):
            return (gate_coseno(n, sr, tempo, sd, sh), "mono",
                    f"coseno {t}  shape={sh:g}  (K2 actual = semicorchea shape=3)")
        _add("coseno", f"{tag}_shape{int(shape)}", _f)

# -- pulso (chop) ------------------------------------------------------------
for subdivs, tag in ((2.0, "corchea"), (4.0, "semicorchea"), (8.0, "fusa")):
    for duty in (0.25, 0.50, 0.75):
        def _f(n, sr, tempo, sd=subdivs, d=duty, t=tag):
            return (gate_pulso(n, sr, tempo, sd, d), "mono",
                    f"pulso {t}  duty={d:.0%}")
        _add("pulso", f"{tag}_duty{int(duty * 100):02d}", _f)

# -- rampa -------------------------------------------------------------------
for down, name in ((False, "abre"), (True, "cierra")):
    for subdivs, tag in ((4.0, "semicorchea"), (8.0, "fusa")):
        def _f(n, sr, tempo, sd=subdivs, dn=down, t=tag, nm=name):
            return (gate_rampa(n, sr, tempo, sd, dn), "mono",
                    f"rampa {nm} {t}")
        _add("rampa", f"{name}_{tag}", _f)

# -- patrón 16 semicorcheas (un compás 4/4) ----------------------------------
PATRONES = {
    "negras":        "1000100010001000",
    "offbeat":       "0101010101010101",
    "trance":        "1010101010101010",
    "trance_corto":  "1000100010101000",
    "euro":          "1101110111011101",
    "galope":        "1101110111011101",
    "tres_y_una":    "1110111011101110",
    "mitad":         "1111111100000000",
    "estribillo":    "1011101110111011",
}
# galope duplicaba euro; sustituyo galope por 16ths típico de bass
PATRONES["galope"] = "1011011010110110"

for nombre, bits in PATRONES.items():
    def _f(n, sr, tempo, p=bits, nm=nombre):
        return (gate_patron(n, sr, tempo, p), "mono",
                f"patrón {nm}  {p}")
    _add("patron", nombre, _f)

# -- ping-pong ---------------------------------------------------------------
def _pp_cos(n, sr, tempo):
    return (gate_coseno(n, sr, tempo, 4.0, 3.0), "pingpong",
            "L y R en contrafase, coseno semicorchea shape=3")


def _pp_pulso(n, sr, tempo):
    return (gate_pulso(n, sr, tempo, 4.0, 0.5), "pingpong",
            "L y R en contrafase, pulso 50 % semicorchea")


_add("pingpong", "coseno_semi", _pp_cos)
_add("pingpong", "pulso50_semi", _pp_pulso)

# -- pump (invertido: calla el pico, no el valle) ----------------------------
def _pump_cos(n, sr, tempo):
    return (gate_coseno(n, sr, tempo, 4.0, 3.0), "pump",
            "invertido: duck en el pico del coseno (sidechain)")


def _pump_pulso(n, sr, tempo):
    return (gate_pulso(n, sr, tempo, 4.0, 0.25), "pump",
            "invertido: duck en el pulso corto")


_add("pump", "coseno_semi", _pump_cos)
_add("pump", "pulso25_semi", _pump_pulso)


def main():
    _limpia()
    print(f"render seco: {SONG.name} canal {BASS_CH + 1}, {SECONDS:.0f}s")
    dry, sr, tempo = _render_dry()
    rms = float(np.sqrt((dry ** 2).mean()))
    print(f"  rms={rms:.4f}  tempo={tempo:.1f} BPM")
    if rms < 1e-4:
        raise SystemExit("el bajo ha salido en silencio")
    sf.write(OUT / "00_dry.wav", dry, sr, subtype="FLOAT")
    env = _envelope(len(dry), sr)
    n = len(dry)

    lineas = [
        f"Riff: {SONG.name} canal 3, {SECONDS:.0f} s, tempo {tempo:.1f} BPM.",
        "Barrido: 2s seco · 2s in · 2s gate 100% · 2s out · 2s seco.",
        "K2 actual ≈ coseno/semicorchea_shape3.wav",
        "",
    ]
    actual = None
    for carpeta, stem, fn in VARIANTES:
        if carpeta != actual:
            actual = carpeta
            print(f"  [{carpeta}]")
            lineas.append(f"## {carpeta}")
        dest = OUT / carpeta
        dest.mkdir(exist_ok=True)
        gain, stereo, nota = fn(n, sr, tempo)
        gated = _aplica(dry, gain, stereo)
        mixed = dry * (1.0 - env[:, None]) + gated * env[:, None]
        name = f"{stem}.wav"
        sf.write(dest / name, mixed.astype(np.float32), sr, subtype="FLOAT")
        print(f"    {name}")
        lineas.append(f"  {name}  {nota}")
    lineas.append("")
    (OUT / "indice.txt").write_text("\n".join(lineas), encoding="utf-8")
    print(f"listo: {OUT}")


if __name__ == "__main__":
    main()
