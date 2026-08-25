#!/usr/bin/env python3
"""LOG TEMPORAL DE TIMING del sinte (quitar tras depurar).

Registra en JSONL cuándo el sinte EMITE cada evento a los robots y a qué
instante audible corresponde, para compararlo con lo que las robotas
reciben/ejecutan (ver bin/cliente_final/timing_log.py). El reloj es el del
sinte (las robotas se sincronizan a él por los SYNC), así que los `t` y los
`ts`/`audible` son directamente comparables entre ambos ficheros.

Desactivar con TIMING_LOG=0. Fichero: /tmp/sinte_timing.jsonl.
Para retirar: borrar este fichero y las llamadas `timing_log.log(`.
"""
from __future__ import annotations

import json
import os
import time

_ENABLED = os.environ.get("TIMING_LOG", "1") != "0"
_PATH = os.environ.get("TIMING_LOG_PATH", "/tmp/sinte_timing.jsonl")
_f = None


def log(event: str, **fields):
    global _f
    if not _ENABLED:
        return
    try:
        if _f is None:
            _f = open(_PATH, "a", buffering=1)
        rec = {"t": round(time.time() * 1000, 1), "ev": event}
        rec.update(fields)
        _f.write(json.dumps(rec) + "\n")
    except Exception:
        pass
