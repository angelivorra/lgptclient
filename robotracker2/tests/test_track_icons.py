"""Los iconos de pista son glifos Phosphor, no dibujos vectoriales.

En la Odin los Line+miter tapaban media pantalla; un glifo de fuente
tiene que caber en una caja del tamaño pedido.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracks import TRACK_KINDS  # noqa: E402


def test_phosphor_glyphs_fit():
    from screens.icons import GLYPH, icon_texture

    for kind in TRACK_KINDS:
        assert kind in GLYPH, kind
        tex = icon_texture(kind, 24)
        tw, th = tex.size
        assert tw > 4 and th > 4, (kind, tw, th)
        assert tw <= 48 and th <= 48, (
            f"{kind} {tw}x{th} se sale de una caja de 24")
    from screens.icons import GLYPH, icon_texture
    from screens.project_view import ITEMS

    extra = [it[3] for it in ITEMS if it[1] != "gap"]
    extra += ["save", "discard", "cancel", "yes", "no",
              "pads", "sample", "volume", "empty", "effects", "fx", "mix"]
    for name in extra:
        assert name in GLYPH, name
        tw, th = icon_texture(name, 24).size
        assert tw <= 48 and th <= 48, (name, tw, th)
    print("  iconos Phosphor caben en su caja OK")


def main():
    test_phosphor_glyphs_fit()
    print("TODOS LOS TESTS OK")


if __name__ == "__main__":
    main()
