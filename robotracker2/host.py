"""Dónde corre el tracker: PC de edición vs Odin (ROCKNIX).

El launcher de la Odin exporta `ROBOTRACKER2_EVDEV_GAMEPAD=1`. En el PC
esa variable no está: el audio y la UI se quedan como siempre.
"""

import os


def is_handheld() -> bool:
    return bool(os.environ.get("ROBOTRACKER2_EVDEV_GAMEPAD"))
