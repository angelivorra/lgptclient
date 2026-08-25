#!/usr/bin/env python3
"""LOG TEMPORAL DE TIMING (quitar tras depurar).

Registra en JSONL los instantes de llegada, programación y disparo real de
los eventos que mueven solenoides, para comparar el camino de una CANCIÓN
con el del CALIBRADOR. Cada línea lleva `t` (reloj de pared en ms, ya
sincronizado con el sinte por los SYNC) y `mono` (monotónico en ms).

Se activa por defecto; para desactivar: TIMING_LOG=0. Fichero por defecto:
/tmp/cliente_timing.jsonl (TIMING_LOG_PATH para cambiarlo).

Para retirar todo esto: borrar este fichero y las llamadas `timing_log.log(`.
"""
from __future__ import annotations

import json
import os
import time

_ENABLED = os.environ.get("TIMING_LOG", "1") != "0"
_PATH = os.environ.get("TIMING_LOG_PATH", "/tmp/cliente_timing.jsonl")
_f = None


def log(event: str, **fields):
    global _f
    if not _ENABLED:
        return
    try:
        if _f is None:
            _f = open(_PATH, "a", buffering=1)  # line-buffered
        rec = {"t": round(time.time() * 1000, 1),
               "mono": round(time.monotonic() * 1000, 1),
               "ev": event}
        rec.update(fields)
        _f.write(json.dumps(rec) + "\n")
    except Exception:
        pass
