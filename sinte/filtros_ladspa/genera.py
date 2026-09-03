#!/usr/bin/env python3
"""Bounces del bajo de abducción: filtros LADSPA del sistema.

Cada WAV dura 10 s, mismo riff (canal 3 / índice 2, sin FX de canción):

  0-2 s  seco
  2-4 s  fundido lineal a 100 % filtro
  4-6 s  filtro a tope (esta combinación, 100 % wet)
  6-8 s  fundido lineal a seco
  8-10 s seco

Una subcarpeta por plugin; dentro, combinaciones de cutoff / Q / modo.
Los WAV están en .gitignore.

  sinte/.venv/bin/python filtros_ladspa/genera.py
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
N_SEGS = 5
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
    left = LadspaPlugin(path, uid, sr, controls)
    right = LadspaPlugin(path, uid, sr, controls)
    out = np.empty_like(dry)
    for i in range(0, len(dry), BLOCK):
        sl = np.ascontiguousarray(dry[i:i + BLOCK, 0])
        sr_ = np.ascontiguousarray(dry[i:i + BLOCK, 1])
        ol = np.empty_like(sl)
        or_ = np.empty_like(sr_)
        left.run_to(sl, ol, in_p, out_p)
        right.run_to(sr_, or_, in_p, out_p)
        out[i:i + BLOCK, 0] = ol
        out[i:i + BLOCK, 1] = or_
    return out


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


def _sweep(dry: np.ndarray, wet: np.ndarray, env: np.ndarray) -> np.ndarray:
    return dry * (1.0 - env[:, None]) + wet * env[:, None]


def _limpia():
    for p in OUT.iterdir():
        if p.name == "genera.py":
            continue
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()


VARIANTES: list[tuple] = []


def _add(carpeta, stem, so, uid, ctl, ip, op, nota):
    VARIANTES.append((carpeta, stem, so, uid, ctl, ip, op, nota))


# --- State Variable Filter (svf_1214): type, freq ≤6000, Q 0-1, res 0-1 ---
# ports: in 0, out 1, type 2, freq 3, Q 4, resonance 5
_SVF = "svf_1214.so"
_SVF_T = {1: "lp", 2: "hp", 3: "bp", 4: "br"}
for hz in (200.0, 400.0, 800.0, 1600.0):
    for q in (0.25, 0.70):
        for res in (0.0, 0.45):
            _add("svf", f"lp_f{int(hz)}_q{q:.2f}_r{res:.2f}",
                 _SVF, 1214, {2: 1.0, 3: hz, 4: q, 5: res}, 0, 1,
                 f"SVF LP freq={int(hz)} Q={q} res={res}")
for hz in (80.0, 150.0, 300.0):
    _add("svf", f"hp_f{int(hz)}_q025",
         _SVF, 1214, {2: 2.0, 3: hz, 4: 0.25, 5: 0.0}, 0, 1,
         f"SVF HP freq={int(hz)} Q=0.25")
for hz in (200.0, 400.0, 800.0):
    for q in (0.35, 0.70):
        _add("svf", f"bp_f{int(hz)}_q{q:.2f}",
             _SVF, 1214, {2: 3.0, 3: hz, 4: q, 5: 0.30}, 0, 1,
             f"SVF BP freq={int(hz)} Q={q} res=0.3")
for hz in (400.0, 800.0):
    _add("svf", f"br_f{int(hz)}_q050",
         _SVF, 1214, {2: 4.0, 3: hz, 4: 0.50, 5: 0.0}, 0, 1,
         f"SVF notch (BR) freq={int(hz)} Q=0.5")

# --- LS Filter (ls_filter_1908): 0=LP 1=BP 2=HP, cutoff, resonance ---
# ports: type 0, cutoff 1, res 2, in 3, out 4
_LS = "ls_filter_1908.so"
for tipo, tname in ((0.0, "lp"), (1.0, "bp"), (2.0, "hp")):
    cortes = (200.0, 500.0, 1200.0) if tname != "hp" else (80.0, 150.0, 300.0)
    for hz in cortes:
        for res in (0.0, 0.55):
            _add("ls_filter", f"{tname}_f{int(hz)}_r{res:.2f}",
                 _LS, 1908, {0: tipo, 1: hz, 2: res}, 3, 4,
                 f"LS {tname.upper()} cutoff={int(hz)} res={res}")

# --- Glame IIR ---
for hz in (200.0, 400.0, 800.0, 2000.0):
    for st in (1.0, 2.0, 4.0):
        _add("glame_lp", f"f{int(hz)}_st{int(st)}",
             "lowpass_iir_1891.so", 1891, {0: hz, 1: st}, 2, 3,
             f"Glame LP cutoff={int(hz)} stages={int(st)}")
for hz in (80.0, 150.0, 300.0):
    for st in (1.0, 2.0):
        _add("glame_hp", f"f{int(hz)}_st{int(st)}",
             "highpass_iir_1890.so", 1890, {0: hz, 1: st}, 2, 3,
             f"Glame HP cutoff={int(hz)} stages={int(st)}")
for hz in (200.0, 400.0, 800.0):
    for bw in (100.0, 300.0):
        for st in (1.0, 2.0):
            _add("glame_bp", f"c{int(hz)}_bw{int(bw)}_st{int(st)}",
                 "bandpass_iir_1892.so", 1892, {0: hz, 1: bw, 2: st}, 3, 4,
                 f"Glame BP center={int(hz)} bw={int(bw)} stages={int(st)}")
for hz in (200.0, 400.0, 800.0):
    for bw in (100.0, 300.0):
        _add("glame_bp_analog", f"c{int(hz)}_bw{int(bw)}",
             "bandpass_a_iir_1893.so", 1893, {0: hz, 1: bw}, 2, 3,
             f"Glame analog BP center={int(hz)} bw={int(bw)}")
for hz in (200.0, 400.0, 800.0):
    for bw in (80.0, 200.0):
        _add("glame_notch", f"c{int(hz)}_bw{int(bw)}",
             "notch_iir_1894.so", 1894, {0: hz, 1: bw, 2: 1.0}, 3, 4,
             f"Glame notch center={int(hz)} bw={int(bw)} stages=1")

# --- Butterworth (resonance 0.1–1.41) ---
for hz in (200.0, 500.0, 1200.0):
    for res in (0.30, 0.755, 1.20):
        _add("butter_lp", f"f{int(hz)}_r{res:.2f}".replace(".", "p"),
             "butterworth_1902.so", 1903, {0: hz, 1: res}, 2, 3,
             f"Butterworth LP cutoff={int(hz)} res={res}")
for hz in (80.0, 150.0, 300.0):
    for res in (0.30, 0.755):
        _add("butter_hp", f"f{int(hz)}_r{res:.2f}".replace(".", "p"),
             "butterworth_1902.so", 1904, {0: hz, 1: res}, 2, 3,
             f"Butterworth HP cutoff={int(hz)} res={res}")

# --- LADSPA examples (simples) ---
for hz in (200.0, 400.0, 800.0, 2000.0):
    _add("simple_lpf", f"f{int(hz)}",
         "filter.so", 1041, {0: hz}, 1, 2,
         f"Simple LPF cutoff={int(hz)}")
for hz in (80.0, 150.0, 300.0):
    _add("simple_hpf", f"f{int(hz)}",
         "filter.so", 1042, {0: hz}, 1, 2,
         f"Simple HPF cutoff={int(hz)}")

# --- C* AutoFilter (el acid del motor, para comparar) ---
# mode 0=LP 1=HP, filter, f, Q, depth, lfo/env=0, rate, shape, in 8, out 9
for hz in (200.0, 500.0, 1000.0, 2000.0):
    for q in (0.20, 0.50, 0.85):
        _add("autofilter", f"lp_f{int(hz)}_q{q:.2f}",
             "caps.so", 2593,
             {0: 0.0, 1: 0.0, 2: hz, 3: q, 4: 1.0, 5: 0.0, 6: 0.25, 7: 1.0},
             8, 9,
             f"AutoFilter LP f={int(hz)} Q={q} (lfo/env=0, como acid)")
for hz in (150.0, 400.0):
    _add("autofilter", f"hp_f{int(hz)}_q050",
         "caps.so", 2593,
         {0: 1.0, 1: 0.0, 2: hz, 3: 0.50, 4: 1.0, 5: 0.0, 6: 0.25, 7: 1.0},
         8, 9,
         f"AutoFilter HP f={int(hz)} Q=0.5")

# --- C* ToneStack (modelos de amp) ---
for model in range(9):
    _add("tonestack", f"m{model}_b50_m50_t50",
         "caps.so", 2589, {0: float(model), 1: 0.5, 2: 0.5, 3: 0.5}, 4, 5,
         f"ToneStack model={model} bass/mid/treble=0.5")
for model, bass, mid, tre in (
        (0, 1.0, 0.35, 0.20),
        (2, 0.85, 0.40, 0.15),
        (4, 0.70, 0.55, 0.25),
):
    _add("tonestack",
         f"m{model}_b{int(bass * 100)}_m{int(mid * 100)}_t{int(tre * 100)}",
         "caps.so", 2589, {0: float(model), 1: bass, 2: mid, 3: tre}, 4, 5,
         f"ToneStack model={model} bass={bass} mid={mid} treble={tre}")

# --- DJ EQ mono ---
# lo 0, mid 1, hi 2, in 3, out 4
for lo in (-12.0, -6.0, 0.0, 6.0):
    _add("dj_eq", f"lo{int(lo):+d}_mid0_hi0".replace("+", "p").replace("-", "m"),
         "dj_eq_1901.so", 1907, {0: lo, 1: 0.0, 2: 0.0}, 3, 4,
         f"DJ EQ Lo={lo} dB Mid=0 Hi=0")
for hi in (-12.0, -6.0, 6.0):
    _add("dj_eq", f"lo0_mid0_hi{int(hi):+d}".replace("+", "p").replace("-", "m"),
         "dj_eq_1901.so", 1907, {0: 0.0, 1: 0.0, 2: hi}, 3, 4,
         f"DJ EQ Lo=0 Mid=0 Hi={hi} dB")
_add("dj_eq", "scoop_mid_m12",
     "dj_eq_1901.so", 1907, {0: 3.0, 1: -12.0, 2: 3.0}, 3, 4,
     "DJ EQ Lo=+3 Mid=-12 Hi=+3")

# --- Single band parametric ---
# gain 0, freq 1, bw oct 2, in 3, out 4
for hz in (80.0, 160.0, 400.0, 800.0):
    for db in (-12.0, 6.0, 12.0):
        tag = f"m{int(abs(db))}" if db < 0 else f"p{int(db)}"
        _add("single_para", f"f{int(hz)}_{tag}_bw1",
             "single_para_1203.so", 1203, {0: db, 1: hz, 2: 1.0}, 3, 4,
             f"para 1 banda f={int(hz)} gain={db} dB bw=1 oct")
for hz in (200.0, 400.0):
    for bw in (0.4, 2.0):
        _add("single_para", f"f{int(hz)}_p8_bw{bw:.1f}".replace(".", "p"),
             "single_para_1203.so", 1203, {0: 8.0, 1: hz, 2: bw}, 3, 4,
             f"para 1 banda f={int(hz)} +8 dB bw={bw} oct")

# --- Triple para + shelves ---
# 0-2 lo shelf, 3-5 b1, 6-8 b2, 9-11 b3, 12-14 hi shelf, 15 in, 16 out
def _triple(lo_g=0, lo_f=80, lo_s=0.5, b1g=0, b1f=200, b1bw=1,
            b2g=0, b2f=400, b2bw=1, b3g=0, b3f=800, b3bw=1,
            hi_g=0, hi_f=4000, hi_s=0.5):
    return {0: lo_g, 1: lo_f, 2: lo_s,
            3: b1g, 4: b1f, 5: b1bw,
            6: b2g, 7: b2f, 8: b2bw,
            9: b3g, 10: b3f, 11: b3bw,
            12: hi_g, 13: hi_f, 14: hi_s}

_add("triple_para", "lo_shelf_p8_f80",
     "triple_para_1204.so", 1204, _triple(lo_g=8, lo_f=80), 15, 16,
     "shelf graves +8 dB @ 80 Hz")
_add("triple_para", "lo_shelf_m12_f80",
     "triple_para_1204.so", 1204, _triple(lo_g=-12, lo_f=80), 15, 16,
     "shelf graves -12 dB @ 80 Hz")
_add("triple_para", "peak_p8_f200",
     "triple_para_1204.so", 1204, _triple(b1g=8, b1f=200), 15, 16,
     "pico +8 dB @ 200 Hz")
_add("triple_para", "peak_m10_f400",
     "triple_para_1204.so", 1204, _triple(b1g=-10, b1f=400), 15, 16,
     "pico -10 dB @ 400 Hz (quita barro)")
_add("triple_para", "hi_shelf_m12_f1500",
     "triple_para_1204.so", 1204, _triple(hi_g=-12, hi_f=1500), 15, 16,
     "shelf agudos -12 dB @ 1500 Hz")
_add("triple_para", "lo_p6_mid_m8_hi_m10",
     "triple_para_1204.so", 1204,
     _triple(lo_g=6, lo_f=70, b1g=-8, b1f=350, hi_g=-10, hi_f=2000), 15, 16,
     "graves +6, 350 Hz -8, agudos -10")

# --- Multiband EQ (15 bandas, 50 Hz–20 kHz) ---
def _mbeq(bandas: dict[int, float]) -> dict[int, float]:
    ctl = {i: 0.0 for i in range(15)}
    ctl.update(bandas)
    return ctl

_add("mbeq", "grave_p8_50_100",
     "mbeq_1197.so", 1197, _mbeq({0: 8, 1: 8}), 15, 16,
     "mbeq +8 dB @ 50 y 100 Hz")
_add("mbeq", "grave_m12_50_100",
     "mbeq_1197.so", 1197, _mbeq({0: -12, 1: -12}), 15, 16,
     "mbeq -12 dB @ 50 y 100 Hz")
_add("mbeq", "barro_m10_220_311",
     "mbeq_1197.so", 1197, _mbeq({3: -10, 4: -10}), 15, 16,
     "mbeq -10 dB @ 220 y 311 Hz")
_add("mbeq", "presencia_p8_1250",
     "mbeq_1197.so", 1197, _mbeq({8: 8}), 15, 16,
     "mbeq +8 dB @ 1250 Hz")
_add("mbeq", "cierra_desde_2500",
     "mbeq_1197.so", 1197, _mbeq({i: -18 for i in range(10, 15)}), 15, 16,
     "mbeq -18 dB desde 2500 Hz (casi LP)")
_add("mbeq", "cierra_desde_880",
     "mbeq_1197.so", 1197, _mbeq({i: -18 for i in range(7, 15)}), 15, 16,
     "mbeq -18 dB desde 880 Hz")

# --- C* Eq10 ---
def _eq10(*dbs: float) -> dict[int, float]:
    return {i: float(dbs[i]) if i < len(dbs) else 0.0 for i in range(10)}

_add("eq10", "grave_p8_31_63",
     "caps.so", 1773, _eq10(8, 8), 10, 11,
     "Eq10 +8 @ 31 y 63 Hz")
_add("eq10", "grave_m12_31_63",
     "caps.so", 1773, _eq10(-12, -12), 10, 11,
     "Eq10 -12 @ 31 y 63 Hz")
_add("eq10", "barro_m10_250",
     "caps.so", 1773, _eq10(0, 0, 0, -10), 10, 11,
     "Eq10 -10 @ 250 Hz")
_add("eq10", "cierra_desde_2k",
     "caps.so", 1773, _eq10(0, 0, 0, 0, 0, 0, -18, -18, -18, -18), 10, 11,
     "Eq10 -18 desde 2 kHz")
_add("eq10", "smiley_p6_m6_p4",
     "caps.so", 1773, _eq10(6, 4, 0, -6, -6, 0, 2, 4, 4, 2), 10, 11,
     "Eq10 smiley (graves/agudos +)")

# --- C* Eq4p (mode -1 off, 0 lo-shelf, 1 peak, 2 hi-shelf) ---
# a 0-3, b 4-7, c 8-11, d 12-15, lat 16, in 17, out 18
def _eq4p_a(mode, f, q, g):
    return {0: mode, 1: f, 2: q, 3: g,
            4: -1, 8: -1, 12: -1}

_add("eq4p", "loshelf_p8_f80",
     "caps.so", 2608, _eq4p_a(0, 80, 0.25, 8), 17, 18,
     "Eq4p low-shelf +8 @ 80 Hz")
_add("eq4p", "loshelf_m12_f80",
     "caps.so", 2608, _eq4p_a(0, 80, 0.25, -12), 17, 18,
     "Eq4p low-shelf -12 @ 80 Hz")
_add("eq4p", "peak_p8_f200_q025",
     "caps.so", 2608, _eq4p_a(1, 200, 0.25, 8), 17, 18,
     "Eq4p peak +8 @ 200 Hz")
_add("eq4p", "peak_p8_f400_q050",
     "caps.so", 2608, _eq4p_a(1, 400, 0.50, 8), 17, 18,
     "Eq4p peak +8 @ 400 Hz")
_add("eq4p", "peak_m10_f350",
     "caps.so", 2608, _eq4p_a(1, 350, 0.40, -10), 17, 18,
     "Eq4p peak -10 @ 350 Hz")
_add("eq4p", "hishelf_m12_f1200",
     "caps.so", 2608, _eq4p_a(2, 1200, 0.25, -12), 17, 18,
     "Eq4p high-shelf -12 @ 1200 Hz")

# --- C* EqFA4p ---
# a 0-3, b 4-7, c 8-11, d 12-15, gain 16, lat 17, in 18, out 19
def _eqfa(f, bw, g):
    return {0: 1.0, 1: f, 2: bw, 3: g, 16: 0.0}

for hz in (80.0, 160.0, 400.0, 800.0):
    for db in (-10.0, 8.0):
        tag = f"m{int(abs(db))}" if db < 0 else f"p{int(db)}"
        _add("eqfa4p", f"f{int(hz)}_{tag}",
             "caps.so", 2609, _eqfa(hz, 1.0, db), 18, 19,
             f"EqFA4p banda A f={int(hz)} {db} dB")

# --- ZamGEQ31 (master=2, 32 Hz=3 …). ZamEQ2 se salta: sale NaN. ---
def _geq(**hz_db: float) -> dict[int, float]:
    nombres = [32, 40, 50, 63, 79, 100, 126, 158, 200, 251, 316, 398,
               501, 631, 794, 999]
    idx = {n: 3 + i for i, n in enumerate(nombres)}
    ctl = {2: 0.0}
    for n, db in hz_db.items():
        ctl[idx[int(n)]] = db
    return ctl

_add("zamgeq31", "p8_32_50",
     "ZamGEQ31-ladspa.so", 1514615601, _geq(**{"32": 8, "50": 8}), 0, 1,
     "GEQ31 +8 @ 32 y 50 Hz")
_add("zamgeq31", "m8_32_50",
     "ZamGEQ31-ladspa.so", 1514615601, _geq(**{"32": -8, "50": -8}), 0, 1,
     "GEQ31 -8 @ 32 y 50 Hz")
_add("zamgeq31", "p8_100",
     "ZamGEQ31-ladspa.so", 1514615601, _geq(**{"100": 8}), 0, 1,
     "GEQ31 +8 @ 100 Hz")
_add("zamgeq31", "m10_200_251",
     "ZamGEQ31-ladspa.so", 1514615601, _geq(**{"200": -10, "251": -10}), 0, 1,
     "GEQ31 -10 @ 200 y 251 Hz")
_add("zamgeq31", "p6_501",
     "ZamGEQ31-ladspa.so", 1514615601, _geq(**{"501": 6}), 0, 1,
     "GEQ31 +6 @ 501 Hz")

# --- Comb filter (swh) ---
for sep in (40.0, 80.0, 160.0, 320.0):
    for fb in (0.40, 0.70, 0.90):
        _add("comb", f"sep{int(sep)}_fb{int(fb * 100)}",
             "comb_1190.so", 1190, {0: sep, 1: fb}, 2, 3,
             f"comb sep={int(sep)} Hz feedback={fb}")

# --- 4x4 pole allpass (resonante) ---
def _fourpole(f1, fb):
    return {0: f1, 1: fb, 2: f1 * 2, 3: fb, 4: f1 * 3, 5: fb,
            6: min(f1 * 4, 20000), 7: fb}

for f1 in (80.0, 160.0, 300.0, 600.0):
    for fb in (0.40, 0.75):
        _add("fourpole", f"f{int(f1)}_fb{int(fb * 100)}",
             "phasers_1217.so", 1218, _fourpole(f1, fb), 8, 9,
             f"4x4 allpass f1={int(f1)} fb={fb}")

# --- LFO phaser (filtro móvil) ---
for rate in (0.2, 0.8, 3.0):
    for depth in (0.4, 0.9):
        _add("lfo_phaser", f"rate{rate:.1f}_d{depth:.1f}".replace(".", "p"),
             "phasers_1217.so", 1217,
             {0: rate, 1: depth, 2: 0.35, 3: 1.0}, 4, 5,
             f"LFO phaser rate={rate} Hz depth={depth}")

# --- C* PhaserII ---
for rate in (0.15, 0.40, 0.80):
    for res in (0.20, 0.60):
        _add("phaser2", f"rate{int(rate * 100)}_r{int(res * 100)}",
             "caps.so", 2586,
             {0: rate, 1: 0.0, 2: 0.75, 3: 0.75, 4: res}, 5, 6,
             f"PhaserII rate={rate} res={res} lfo=0")

# --- C* Spice (exciter de graves/agudos) ---
_add("spice", "lo_f80_g050",
     "caps.so", 2603,
     {0: 80, 1: 0.5, 2: 0.5, 3: 0, 4: 800, 5: 0.1, 6: -12}, 7, 8,
     "Spice lo 80 Hz gain 0.5, hi casi mute")
_add("spice", "lo_f120_g080",
     "caps.so", 2603,
     {0: 120, 1: 0.6, 2: 0.8, 3: 3, 4: 800, 5: 0.1, 6: -12}, 7, 8,
     "Spice lo 120 Hz más agresivo")
_add("spice", "hi_f800_g040",
     "caps.so", 2603,
     {0: 100, 1: 0.3, 2: 0.15, 3: 0, 4: 800, 5: 0.4, 6: 0}, 7, 8,
     "Spice más agudos @ 800 Hz")
_add("spice", "hi_f2000_g050",
     "caps.so", 2603,
     {0: 100, 1: 0.3, 2: 0.15, 3: 0, 4: 2000, 5: 0.5, 6: 0}, 7, 8,
     "Spice más agudos @ 2000 Hz")

# --- Cabinets (filtro de altavoz) ---
for model in (0, 4, 8, 12, 16):
    _add("cabinet3", f"m{model}_g0",
         "caps.so", 2601, {0: float(model), 1: 0.0, 2: 0.0}, 3, 4,
         f"CabinetIII model={model}")
for model in (0, 8, 16, 24):
    _add("cabinet4", f"m{model}_g0",
         "caps.so", 2606, {0: float(model), 1: 0.0}, 2, 3,
         f"CabinetIV model={model}")

# --- DC remover (HPF extremo; un WAV de referencia) ---
_add("dc_remove", "default",
     "dc_remove_1207.so", 1207, {}, 0, 1,
     "quita offset DC (casi transparente en este bajo)")


def main():
    _limpia()
    print(f"render seco: {SONG.name} canal {BASS_CH + 1}, {SECONDS:.0f}s")
    dry, sr = _render_dry()
    rms = float(np.sqrt((dry ** 2).mean()))
    print(f"  {len(dry)} samples, rms={rms:.4f}, {len(VARIANTES)} variantes")
    if rms < 1e-4:
        raise SystemExit("el bajo ha salido en silencio: revisa el canal")
    sf.write(OUT / "00_dry.wav", dry, sr, subtype="FLOAT")
    env = _envelope(len(dry), sr)

    lineas = [
        "Riff: lgpt_abduccion canal 3, 10 s. En cada WAV:",
        "  0-2 s seco · 2-4 s fundido al filtro · 4-6 s filtro 100 %",
        "  6-8 s fundido a seco · 8-10 s seco",
        "El nombre del fichero es la combinación de controles a tope (wet).",
        "00_dry.wav en la raíz = el riff sin ningún plugin.",
        "Hermes, allpass y ZamEQ2 no están (sinte / delay / NaN).",
        "ZamDynamicEQ tampoco: EQ dinámico con sidechain.",
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
    print(f"listo: {OUT}")


if __name__ == "__main__":
    main()
