"""LIVE: hold de MDCC, combos de pads y destello en LiveGrid."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robots import (ROBOT_TRACK, RobotPlayback, hit_pad_notes,  # noqa: E402
                    mdcc_pack)


class _Chan:
    def __init__(self):
        self.playing = False
        self.phrase = 0xFF
        self.phrase_pos = 0


def _engine(n=32):
    chans = [_Chan() for _ in range(8)]
    proj = SimpleNamespace(
        notes=[0xFF] * n,
        cmd1=["----"] * n,
        param1=[0] * n,
    )
    return SimpleNamespace(channels=chans, muted=set(), project=proj)


def test_hit_pad_notes():
    assert hit_pad_notes(62) == (62,)
    assert hit_pad_notes(63) == (63,)
    assert hit_pad_notes(65) == (65,)
    assert hit_pad_notes(64) == (62, 63)
    assert hit_pad_notes(66) == (62, 65)
    assert hit_pad_notes(67) == (63, 65)
    assert hit_pad_notes(99) == ()
    print("  hit_pad_notes combos OK")


def test_mdcc_hold_and_hit():
    eng = _engine()
    robot = eng.channels[ROBOT_TRACK]
    robot.playing = True
    robot.phrase = 0
    robot.phrase_pos = 0
    eng.project.notes[0] = 62
    eng.project.cmd1[0] = "MDCC"
    eng.project.param1[0] = mdcc_pack(1, 7)

    pb = RobotPlayback()
    pb.update(eng)
    assert pb.playing
    assert pb.note == 62
    assert pb.hit_note == 62
    assert pb.cc == 1 and pb.value == 7

    pb.update(eng)                    # mismo step: no re-golpe
    assert pb.hit_note is None
    assert pb.cc == 1 and pb.value == 7

    robot.phrase_pos = 1              # step sin MDCC ni nota
    pb.update(eng)
    assert pb.note is None
    assert pb.hit_note is None
    assert pb.cc == 1 and pb.value == 7, "SCREEN se sostiene"

    robot.phrase_pos = 2
    eng.project.notes[2] = 64
    pb.update(eng)
    assert pb.hit_note == 64
    assert pb.cc == 1 and pb.value == 7

    pb.reset()
    assert pb.cc is None and pb.value is None
    print("  RobotPlayback hold MDCC + hit al avanzar OK")


def test_robot_channel_gap_keeps_screen():
    eng = _engine()
    robot = eng.channels[ROBOT_TRACK]
    robot.playing = True
    robot.phrase = 0
    robot.phrase_pos = 0
    eng.project.cmd1[0] = "MDCC"
    eng.project.param1[0] = mdcc_pack(3, 2)
    pb = RobotPlayback()
    pb.update(eng)
    assert pb.cc == 3

    robot.playing = False
    robot.phrase = 0xFF
    pb.update(eng)
    assert not pb.playing
    assert pb.cc == 3 and pb.value == 2
    print("  canal robot parado conserva SCREEN OK")


def test_mute_flag():
    eng = _engine()
    eng.muted.add(ROBOT_TRACK)
    robot = eng.channels[ROBOT_TRACK]
    robot.playing = True
    robot.phrase = 0
    pb = RobotPlayback()
    pb.update(eng)
    assert pb.muted
    print("  mute del canal robot OK")


def test_live_grid_combo_pulse():
    from kivy.app import App
    from screens.live_view import LiveGrid

    class _App(App):
        def build(self):
            return None

    app = _App()
    app.build()
    g = LiveGrid()
    g.hit(64)
    assert g.pulse[62] == 1.0
    assert g.pulse[63] == 1.0
    assert g.pulse[65] == 0.0
    g.hit(65)
    assert g.pulse[65] == 1.0
    print("  LiveGrid.hit combo enciende pads OK")


if __name__ == "__main__":
    test_hit_pad_notes()
    test_mdcc_hold_and_hit()
    test_robot_channel_gap_keeps_screen()
    test_mute_flag()
    test_live_grid_combo_pulse()
    print("TODOS LOS TESTS OK")
