#!/usr/bin/env python3
"""Captura eventos evdev crudos de los dispositivos indicados (diagnóstico).

Uso: cap_ev.py /dev/input/event3 /dev/input/event6 /dev/input/event13
Duración: CAP_SECS (por defecto 40 s).
"""
import os
import select
import struct
import sys
import time

EV_KEY, EV_ABS = 1, 3
ABS = {0: "X", 1: "Y", 2: "Z(L2)", 3: "RX", 4: "RY", 5: "RZ(R2)"}
KEY = {29: "LEFTCTRL", 97: "RIGHTCTRL", 30: "A", 31: "S", 32: "D", 17: "W",
       45: "X", 103: "UP", 105: "LEFT", 106: "RIGHT", 108: "DOWN",
       57: "SPACE", 28: "ENTER", 1: "ESC", 44: "Z"}


def fmt(t, c, v):
    if t == EV_KEY:
        return f"KEY {KEY.get(c, c)} {v}"
    if t == EV_ABS:
        return f"ABS {ABS.get(c, c)} {v}"
    return f"EV{t} {c} {v}"


devs = []
for p in sys.argv[1:]:
    f = open(p, "rb", buffering=0)
    os.set_blocking(f.fileno(), False)
    devs.append((p, f))

t0 = time.monotonic()
end = t0 + float(os.environ.get("CAP_SECS", "40"))
print(f"[{0:7.2f}] CAPTURA INICIADA de {[os.path.basename(p) for p, _ in devs]} "
      f"({end - t0:.0f} s)", flush=True)
while time.monotonic() < end:
    r, _, _ = select.select([f for _, f in devs], [], [], 0.5)
    for p, f in devs:
        if f not in r:
            continue
        try:
            data = f.read(4096)
        except OSError as exc:
            print(f"[{time.monotonic() - t0:7.2f}] {os.path.basename(p)} "
                  f"READ-ERR {exc}", flush=True)
            continue
        for i in range(0, len(data) // 24 * 24, 24):
            _sec, _usec, typ, code, val = struct.unpack("llHHi",
                                                        data[i:i + 24])
            if typ == 0:  # EV_SYN
                continue
            print(f"[{time.monotonic() - t0:7.2f}] "
                  f"{os.path.basename(p):8s} {fmt(typ, code, val)}",
                  flush=True)
print("CAPTURE END", flush=True)
