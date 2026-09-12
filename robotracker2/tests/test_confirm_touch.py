"""Clic / toque en el diálogo Guardar · Descartar · Cancelar."""

import os
import sys
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class _Touch:
    def __init__(self, x, y):
        self.pos = (x, y)
        self.grab_current = None

    def grab(self, w):
        self.grab_current = w

    def ungrab(self, w):
        self.grab_current = None


def test_tap_button_chooses():
    from screens.confirm import ConfirmDialog

    chosen = []
    cancelled = []
    d = ConfirmDialog(
        "Cambios sin guardar",
        [("save", "Guardar"), ("discard", "Descartar"), ("cancel", "Cancelar")],
        on_proceed=lambda: None, selected=2,
        on_choose=lambda: chosen.append(d.selected_key()),
        on_cancel=lambda: cancelled.append(True),
        size=(800, 600), pos=(0, 0))
    b = d._btns[0]
    b.pos = (20, 20)
    b.size = (120, 80)
    t = _Touch(50, 50)
    assert b.on_touch_down(t) is True
    assert b.on_touch_up(t) is True
    assert chosen == ["save"], chosen
    assert cancelled == []
    print("  tap Guardar elige save OK")


def test_tap_scrim_cancels():
    from screens.confirm import ConfirmDialog

    cancelled = []
    d = ConfirmDialog(
        "msg", [("yes", "Sí"), ("no", "No")],
        on_proceed=lambda: None, selected=1,
        on_choose=lambda: None,
        on_cancel=lambda: cancelled.append(True),
        size=(800, 600), pos=(0, 0))
    d._panel.pos = (200, 200)
    d._panel.size = (400, 200)
    for b in d._btns:
        b.pos = (220, 220)
        b.size = (80, 60)
    t = _Touch(10, 10)
    assert d.on_touch_down(t) is True
    assert d.on_touch_up(t) is True
    assert cancelled == [True]
    print("  tap en el velo cancela OK")


def main():
    test_tap_button_chooses()
    test_tap_scrim_cancels()
    print("TODOS LOS TESTS OK")


if __name__ == "__main__":
    main()
