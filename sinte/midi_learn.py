#!/usr/bin/env python3
"""Volcador de MIDI entrante para averiguar qué manda cada pad/knob del
controlador. Escucha en paralelo al player (ALSA permite varios
suscriptores al mismo puerto de entrada, así que NO hace falta pararlo).

Uso en el sinte:
    ~/lgptclient/sinte/.venv/bin/python ~/lgptclient/sinte/midi_learn.py

Pulsa cada pad y gira cada knob; anota lo que imprime. Ctrl-C para salir.
"""
from __future__ import annotations

import sys
import time

import mido


def main():
    names = mido.get_input_names()
    if not names:
        print("No hay puertos MIDI de entrada. ¿Está enchufado el controlador?")
        return 1
    # Mismo criterio que el player: si pasan un nombre por argumento, se usa;
    # si no, el primero que no sea el 'Through' de ALSA.
    wanted = sys.argv[1] if len(sys.argv) > 1 else None
    if wanted:
        chosen = next((n for n in names if wanted.lower() in n.lower()), names[0])
    else:
        chosen = next((n for n in names if "through" not in n.lower()), names[0])

    print(f"Escuchando '{chosen}'. Pulsa pads y gira knobs (Ctrl-C para salir).")
    print("-" * 60)
    with mido.open_input(chosen) as port:
        for msg in port:
            if msg.type == "note_on" and msg.velocity > 0:
                print(f"  PAD  -> note:{msg.channel}:{msg.note}   "
                      f"(canal {msg.channel}, nota {msg.note})")
            elif msg.type == "control_change":
                print(f"  KNOB -> cc:{msg.channel}:{msg.control}   "
                      f"(canal {msg.channel}, control {msg.control}, "
                      f"valor {msg.value})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
