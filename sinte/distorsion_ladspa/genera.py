#!/usr/bin/env python3
"""Bounces del bajo de abducción: barrido seco ↔ efecto por plugin LADSPA.

Cada WAV dura 10 s, mismo riff (canal 3 / índice 2, sin FX de canción):

  0-2 s  seco
  2-4 s  fundido lineal a 100 % efecto
  4-6 s  efecto a tope (esta combinación, 100 % wet)
  6-8 s  fundido lineal a seco
  8-10 s seco

Una subcarpeta por tipo de distorsión; dentro, combinaciones de sus
controles (analyseplugin). Los WAV están en .gitignore.

  sinte/.venv/bin/python distorsion_ladspa/genera.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SINTE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SINTE))

from ladspa_fx import LadspaPlugin  # noqa: E402
from lgpt_engine import Engine  # noqa: E402

SONG = SINTE / "songs" / "lgpt_abduccion"
OUT = Path(__file__).resolve().parent
SEG = 2.0
N_SEGS = 5                 # seco, in, 100 %, out, seco
SECONDS = SEG * N_SEGS
BLOCK = 2048
BASS_CH = 2
LADSPA = Path("/usr/lib/ladspa")


def _render_dry() -> tuple[np.ndarray, int]:
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
    return np.concatenate(chunks, axis=0), engine.sr


def _apply(dry: np.ndarray, sr: int, so: str, uid: int,
           controls: dict[int, float], in_p: int, out_p: int) -> np.ndarray:
    path = str(LADSPA / so)
    left = LadspaPlugin(path, uid, sr)
    right = LadspaPlugin(path, uid, sr)
    for port, val in controls.items():
        left.set_control(port, val)
        right.set_control(port, val)
    out = np.empty_like(dry)
    for i in range(0, len(dry), BLOCK):
        sl = np.ascontiguousarray(dry[i:i + BLOCK, 0])
        sr_ = np.ascontiguousarray(dry[i:i + BLOCK, 1])
        left.run(sl, in_p, out_p)
        right.run(sr_, in_p, out_p)
        out[i:i + BLOCK, 0] = sl
        out[i:i + BLOCK, 1] = sr_
    return out


def _envelope(n: int, sr: int) -> np.ndarray:
    """0, 0→1, 1, 1→0, 0  (2 s cada tramo)."""
    t = np.arange(n, dtype=np.float64) / sr
    env = np.zeros(n, dtype=np.float64)
    s = SEG
    m = (t >= s) & (t < 2 * s)
    env[m] = (t[m] - s) / s
    env[(t >= 2 * s) & (t < 3 * s)] = 1.0
    m = (t >= 3 * s) & (t < 4 * s)
    env[m] = 1.0 - (t[m] - 3 * s) / s
    return env.astype(np.float32)


def _sweep(dry: np.ndarray, wet: np.ndarray, env: np.ndarray) -> np.ndarray:
    return dry * (1.0 - env[:, None]) + wet * env[:, None]


def _rms(buf: np.ndarray) -> float:
    return float(np.sqrt((buf.astype(np.float64) ** 2).mean()))


def _match_rms(sig: np.ndarray, ref: np.ndarray, ratio: float) -> np.ndarray:
    """Escala `sig` para que su RMS sea `ratio` × RMS de `ref`."""
    s, r = _rms(sig), _rms(ref)
    if s < 1e-9:
        return sig
    return (sig * (r * ratio / s)).astype(np.float32)


def _lpf(x: np.ndarray, fc: float, sr: int) -> np.ndarray:
    """Paso bajo de un polo (complementario: x - lpf = altos)."""
    a = float(np.exp(-2.0 * np.pi * fc / sr))
    g = 1.0 - a
    y = np.empty_like(x, dtype=np.float64)
    acc = np.zeros(x.shape[1], dtype=np.float64)
    xd = x.astype(np.float64)
    for i in range(len(x)):
        acc = a * acc + g * xd[i]
        y[i] = acc
    return y.astype(np.float32)


def _pointer_cast(dry: np.ndarray, sr: int, cutoff_hz: float,
                  plugin_wet: float = 1.0) -> np.ndarray:
    return _apply(dry, sr, "pointer_cast_1910.so", 1910,
                  {0: float(cutoff_hz), 1: float(plugin_wet)}, 2, 3)


def _escribe_barrido(path: Path, dry: np.ndarray, wet: np.ndarray,
                     env: np.ndarray, sr: int, lineas: list, nota: str):
    if not np.isfinite(wet).all():
        print(f"    SKIP {path.name}: NaN")
        lineas.append(f"  {path.name}  SKIP NaN")
        return
    mixed = _sweep(dry, wet, env)
    sf.write(path, mixed, sr, subtype="FLOAT")
    print(f"    {path.name}")
    lineas.append(f"  {path.name}  {nota}")


def _esencia_pointer_cast(dry: np.ndarray, sr: int, env: np.ndarray) -> None:
    """Opciones para conservar el grave y el volumen (el WAV que te gustó
    era cutoff 2000 Hz al 100 % wet, sin igualar RMS)."""
    dest = OUT / "pointer_cast" / "esencia"
    dest.mkdir(parents=True, exist_ok=True)
    for p in dest.glob("*.wav"):
        p.unlink()
    lineas = [
        "Mismo riff y barrido 2s seco / 2s in / 2s tope / 2s out / 2s seco.",
        "Partimos de pointer_cast cutoff=2000 Hz (el que te gustó) y buscamos",
        "que el tramo 'efecto 100%' no dispare el volumen ni se coma el grave.",
        "",
        "Familias:",
        "  rms*     — 100% wet, cutoff 2000, RMS = 100/110/120 % del seco",
        "  mix*     — paralelo (seco + wet) y luego RMS 110 %",
        "  grave*   — graves del seco + agudos del pointer_cast (cruce)",
        "  agudos*  — graves del seco + pointer_cast SOLO de los agudos",
        "  corte*   — mix 55 % y RMS 110 %, cutoff alrededor de 2000 Hz",
        "",
    ]
    print("  [pointer_cast/esencia]")
    cast = _pointer_cast(dry, sr, 2000.0)

    for pct in (100, 110, 120):
        wet = _match_rms(cast, dry, pct / 100.0)
        _escribe_barrido(
            dest / f"rms{pct}_cut2000_wet100.wav", dry, wet, env, sr, lineas,
            f"100% wet, cutoff 2000, RMS={pct}% del seco")

    for mix in (0.25, 0.40, 0.55, 0.70):
        para = dry * (1.0 - mix) + cast * mix
        wet = _match_rms(para, dry, 1.10)
        _escribe_barrido(
            dest / f"mix{int(mix * 100):02d}_rms110_cut2000.wav",
            dry, wet, env, sr, lineas,
            f"paralelo mix={mix:.2f} (seco+cast), RMS 110%, cutoff 2000")

    for fc in (120, 200, 300, 450):
        grave = _lpf(dry, fc, sr)
        agudo = cast - _lpf(cast, fc, sr)
        cruz = grave + agudo
        wet = _match_rms(cruz, dry, 1.10)
        _escribe_barrido(
            dest / f"grave_seco_fc{fc}_rms110.wav", dry, wet, env, sr, lineas,
            f"LPF seco @{fc} Hz + HPF del cast 2000 Hz, RMS 110%")

    for fc in (200, 300):
        grave = _lpf(dry, fc, sr)
        altos = dry - grave
        dist = _pointer_cast(altos, sr, 2000.0)
        cruz = grave + dist
        wet = _match_rms(cruz, dry, 1.10)
        _escribe_barrido(
            dest / f"agudos_cast_fc{fc}_rms110.wav", dry, wet, env, sr, lineas,
            f"grave seco @{fc} Hz + pointer_cast solo de los agudos, RMS 110%")

    for hz in (1200, 1600, 2000, 2800, 4000):
        c = _pointer_cast(dry, sr, hz)
        para = dry * 0.45 + c * 0.55
        wet = _match_rms(para, dry, 1.10)
        _escribe_barrido(
            dest / f"corte{int(hz)}_mix55_rms110.wav", dry, wet, env, sr, lineas,
            f"cutoff={int(hz)} Hz, mix 55%, RMS 110%")

    (dest / "indice.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")


def _limpia():
    for p in OUT.iterdir():
        if p.name == "genera.py":
            continue
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()


# carpeta, stem, .so, uid, controles, in, out, nota
#
# El WAV siempre barre 0↔100 % wet; los controles son la combinación a tope.
VARIANTES: list[tuple] = []


def _add(carpeta, stem, so, uid, ctl, ip, op, nota):
    VARIANTES.append((carpeta, stem, so, uid, ctl, ip, op, nota))


# Foldover: Drive 0-1, Skew 0-1
for drive in (0.5, 1.0):
    for skew in (0.0, 0.3, 0.6, 1.0):
        _add("foldover", f"drive{drive:.2f}_skew{skew:.2f}",
             "foldover_1213.so", 1213, {0: drive, 1: skew}, 2, 3,
             f"Drive={drive} Skew={skew} (plegado; Skew 0 = simétrico)")

# Chebyshev: un control Distortion 0-3
for d in (1.0, 2.0, 3.0):
    _add("chebstortion", f"dist{d:.0f}",
         "chebstortion_1430.so", 1430, {0: d}, 1, 2,
         f"Distortion={d} (máx. 3)")

# Sinus wavewrapper: Wrap degree 0-10
for w in (3.0, 6.0, 10.0):
    _add("sinus_wavewrapper", f"wrap{w:.0f}",
         "sinus_wavewrapper_1198.so", 1198, {0: w}, 1, 2,
         f"Wrap degree={w} (máx. 10)")

# Satan: Decay 2-30 samples, Knee -90..0 dB
for knee in (-20.0, -40.0, -60.0):
    for decay in (4.0, 16.0):
        _add("satan_maximiser", f"knee{int(knee)}_decay{int(decay)}",
             "satan_maximiser_1408.so", 1408, {0: decay, 1: knee}, 2, 3,
             f"Knee={knee} dB  Decay={decay} samples")

# Aliasing 0-1
for a in (0.5, 1.0):
    _add("alias", f"level{a:.2f}",
         "alias_1407.so", 1407, {0: a}, 1, 2,
         f"Aliasing level={a}")

# Pointer cast: cutoff Hz, dry/wet del plugin a 1 (el barrido es el nuestro)
for hz in (200.0, 800.0, 2000.0, 5000.0):
    _add("pointer_cast", f"cutoff{int(hz)}hz",
         "pointer_cast_1910.so", 1910, {0: hz, 1: 1.0}, 2, 3,
         f"cutoff={int(hz)} Hz  plugin wet=1")

# Wave shaper -10..10 (valores negativos reventaban NaN en este riff)
for shp in (4.0, 8.0, 10.0):
    tag = f"m{abs(int(shp))}" if shp < 0 else f"p{int(shp)}"
    _add("shaper", f"shape_{tag}",
         "shaper_1187.so", 1187, {0: shp}, 1, 2,
         f"Waveshape={shp}")

# Diode: 1 half, 2 full, 3 (rango 0-3)
for mode, name in ((1.0, "half"), (2.0, "full"), (3.0, "mode3")):
    _add("diode", name,
         "diode_1185.so", 1185, {0: mode}, 1, 2,
         f"Mode={int(mode)}")

# Valve: Distortion level 0-1, character 0-1
for level in (0.5, 1.0):
    for char in (0.0, 0.5, 1.0):
        _add("valve", f"level{level:.1f}_char{char:.1f}",
             "valve_1209.so", 1209, {0: level, 1: char}, 2, 3,
             f"level={level} character={char} (saturación de válvulas)")

# Fast overdrive Drive 1-3
for drive in (2.0, 3.0):
    _add("foverdrive", f"drive{drive:.0f}",
         "foverdrive_1196.so", 1196, {0: drive}, 1, 2,
         f"Drive={drive} (rango 1-3)")

# Crossover: amplitude (usamos 0.1 y 0.2), smoothing 0-1
for amp in (0.10, 0.20):
    for smooth in (0.0, 0.5, 1.0):
        _add("crossover_dist", f"amp{amp:.2f}_smooth{smooth:.1f}",
             "crossover_dist_1404.so", 1404, {0: amp, 1: smooth}, 2, 3,
             f"amplitude={amp} smoothing={smooth}")

# Decimator: bits + sample rate fijo
for bits in (12.0, 8.0, 4.0):
    _add("decimator", f"bits{int(bits)}",
         "decimator_1202.so", 1202, {0: bits, 1: 44100.0}, 2, 3,
         f"bits={int(bits)}  srate=44100 (bitcrush del preset valve)")


def main():
    _limpia()
    print(f"render seco: {SONG.name} canal {BASS_CH + 1}, {SECONDS:.0f}s")
    dry, sr = _render_dry()
    rms = float(np.sqrt((dry ** 2).mean()))
    print(f"  {len(dry)} samples, rms={rms:.4f}")
    if rms < 1e-4:
        raise SystemExit("el bajo ha salido en silencio: revisa el canal")
    sf.write(OUT / "00_dry.wav", dry, sr, subtype="FLOAT")
    env = _envelope(len(dry), sr)

    lineas = [
        "Riff: lgpt_abduccion canal 3, 10 s. En cada WAV:",
        "  0-2 s seco · 2-4 s fundido al efecto · 4-6 s efecto 100 %",
        "  6-8 s fundido a seco · 8-10 s seco",
        "El nombre del fichero es la combinación de controles a tope (wet).",
        "00_dry.wav en la raíz = el riff sin ningún plugin.",
        "",
    ]
    actual = None
    for carpeta, stem, so, uid, ctl, ip, op, nota in VARIANTES:
        if carpeta != actual:
            actual = carpeta
            print(f"  [{carpeta}]")
            lineas.append(f"## {carpeta}  ({so})")
        dest = OUT / carpeta
        dest.mkdir(exist_ok=True)
        name = f"{stem}.wav"
        try:
            wet = _apply(dry, sr, so, uid, ctl, ip, op)
        except Exception as exc:
            print(f"    SKIP {name}: {exc}")
            lineas.append(f"  {name}  ERROR {exc}")
            continue
        if not np.isfinite(wet).all():
            print(f"    SKIP {name}: NaN/inf")
            lineas.append(f"  {name}  SKIP NaN")
            continue
        mixed = _sweep(dry, wet, env)
        sf.write(dest / name, mixed, sr, subtype="FLOAT")
        print(f"    {name}")
        lineas.append(f"  {name}  {nota}")
    lineas.append("")
    (OUT / "indice.txt").write_text("\n".join(lineas), encoding="utf-8")
    _esencia_pointer_cast(dry, sr, env)
    print(f"listo: {OUT}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "esencia":
        print(f"render seco: {SONG.name} canal {BASS_CH + 1}, {SECONDS:.0f}s")
        dry, sr = _render_dry()
        print(f"  rms={_rms(dry):.4f}")
        _esencia_pointer_cast(dry, sr, _envelope(len(dry), sr))
    else:
        main()
