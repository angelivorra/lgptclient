"""El mismo código visual que las robotas.

Importa ``bin/cliente_final`` (lo que Ansible copia a las Pi). Editar
``ribbon.py`` o ``vocoder_neon.py`` ahí cambia el LIVE de Robotracker
y, al desplegar, las pantallas reales.
"""
from __future__ import annotations

import sys
from pathlib import Path

_CLIENT = Path(__file__).resolve().parent.parent / "bin" / "cliente_final"
_client = str(_CLIENT)
if _client not in sys.path:
    sys.path.insert(0, _client)

from ribbon import (  # noqa: E402
    BAND_CENTER,
    HEIGHT,
    REACTORS,
    WIDTH,
    FondoRibbon,
)
from fade_black import FADE_ROWS, FadeBlack, fade_seconds  # noqa: E402
from spark_hit import SPARK_CC, SPARK_VALUE, SparkHit  # noqa: E402
from vocoder_neon import MARGIN, VocoderNeon  # noqa: E402

__all__ = [
    "BAND_CENTER",
    "FADE_ROWS",
    "FadeBlack",
    "FondoRibbon",
    "HEIGHT",
    "MARGIN",
    "REACTORS",
    "SPARK_CC",
    "SPARK_VALUE",
    "SparkHit",
    "WIDTH",
    "VocoderNeon",
    "fade_seconds",
]
