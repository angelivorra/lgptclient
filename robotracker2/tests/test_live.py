"""LIVE: hold de MDCC, combos de pads y destello en LiveGrid."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robots import (ROBOT_TRACK, RobotPlayback, anim_fps,  # noqa: E402
                    anim_frame_paths, hit_pad_notes, mdcc_pack)


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


def test_anim_helpers():
    root = Path(__file__).resolve().parents[2] / "images"
    frames = anim_frame_paths(root, 3, 2)
    assert frames[0].name == "01.png"
    assert frames[1].name == "02.png"
    assert len(frames) >= 4
    assert anim_fps(root, 3, 2) == 30
    assert anim_frame_paths(root, 3, 99) == []
    eyes = anim_frame_paths(root, 3, 3)
    assert [p.name for p in eyes[:3]] == ["1.png", "2.png", "3.png"]
    print("  anim_frame_paths / anim_fps OK")


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


def test_live_grid_ribbon_comparte_el_modulo_de_las_robotas():
    from kivy.app import App
    from screens.live_view import LiveGrid
    from shared_visuals import FondoRibbon

    class _App(App):
        def build(self):
            return None

    _App().build()
    g = LiveGrid()
    assert isinstance(g.ribbon, FondoRibbon)
    g.hit(62)
    assert g.ribbon.env["kick"] > 0.9
    g.set_vocoder(3, [40], 100)          # engancha, no dispara historia
    assert g.neon.level() == 0.0
    g.set_vocoder(4, [48], 127)
    assert g.neon.level() > 0.9
    print("  LIVE usa el mismo FondoRibbon que las robotas OK")


def test_live_grid_01_es_chispazo():
    from types import SimpleNamespace
    from kivy.app import App
    from screens.live_view import LiveGrid
    from shared_visuals import SPARK_CC, SPARK_VALUE

    class _App(App):
        def build(self):
            return None

    _App().build()
    g = LiveGrid()
    g._preview_path = "foto"
    g._preview_tex = None
    g._loaded = (1, 30)
    g.cc, g.value = 1, 30
    pb = SimpleNamespace(cc=SPARK_CC, value=SPARK_VALUE, note=None,
                         playing=True, muted=False, hit_note=None)
    g.set_from(pb)
    assert g._preview_path == "foto"
    assert g.spark.pending() == 1
    assert g.fade.pending()
    g.set_from(pb)
    assert g.spark.pending() == 1, "el hold de la 01 no dispara otro"

    pb.value = 30
    g.set_from(pb)
    assert g.spark.pending() == 1, "la imagen nueva no apaga el chispazo"
    print("  LIVE: 01 estampa chispazo y no quita la imagen OK")


def _kivy():
    from kivy.app import App

    class _App(App):
        def build(self):
            return None

    _App().build()


def test_el_negro_del_ojo_no_tapa_el_fondo():
    import numpy as np
    from screens.live_view import punch_rgba

    img = np.zeros((2, 2, 4), dtype=np.uint8)
    img[:, :] = (0, 7, 6, 255)
    img[0, 0] = (0, 255, 0, 255)
    out = punch_rgba(img)
    assert tuple(out[0, 0]) == (0, 255, 0, 255)
    assert out[1, 1, 3] == 0
    print("  el negro del ojo queda transparente OK")


def test_frame_de_ojos_deja_el_fondo():
    import numpy as np
    from screens.live_view import _load_rgba_texture

    _kivy()
    path = Path(__file__).resolve().parents[2] / "images" / "003" / "003" / "1.png"
    tex = _load_rgba_texture(path, punch_dark=True)
    assert tex is not None
    w, h = tex.size
    raw = np.frombuffer(tex.pixels, dtype=np.uint8).reshape(h, w, 4)
    assert (raw[:, :, 3] == 0).mean() > 0.4
    print("  el frame de ojos no tapa el fondo OK")


def test_gesto_rgb_tambien_deja_el_fondo():
    """Los clips del pad son PNG RGB. El negro tiene que quedar transparente
    igual que en el parpadeo (RGBA)."""
    import numpy as np
    from screens.live_view import _load_rgba_texture

    _kivy()
    root = Path(__file__).resolve().parents[2] / "images" / "003"
    for rel in ("014/34.png", "016/25.png", "018/44.png"):
        tex = _load_rgba_texture(root / rel, punch_dark=True)
        assert tex is not None, rel
        w, h = tex.size
        raw = np.frombuffer(tex.pixels, dtype=np.uint8).reshape(h, w, 4)
        assert (raw[:, :, 3] == 0).mean() > 0.4, rel
    print("  el gesto RGB no tapa el fondo OK")


def test_live_ojos_en_pausa():
    from screens.live_view import IDLE_EYES_CC, IDLE_EYES_VALUE, LiveGrid

    _kivy()
    g = LiveGrid()
    g._images_dir = Path("/tmp")
    g.playing = False
    loaded = {}

    def fake(cc, value):
        loaded["k"] = (cc, value)
        g._anim_textures = [object(), object(), object()]
        g._anim_interval = 1.0 / 30
        g._anim_idx = 0
        return True

    g._load_anim = fake
    g._ensure_idle_eyes()
    assert loaded["k"] == (IDLE_EYES_CC, IDLE_EYES_VALUE)
    assert g._idle_active
    assert len(g._anim_textures) == 3

    g.playing = True
    g._clear_anim()
    g._ensure_idle_eyes()
    assert not g._idle_active
    assert g._anim_textures == []
    print("  LIVE parado muestra ojos; en canción no OK")


def test_live_pad_en_pausa_hace_el_gesto_y_vuelve_a_parpadear():
    from screens.live_view import IDLE_EYES_CC, IDLE_EYES_VALUE, LiveGrid

    _kivy()
    g = LiveGrid()
    g.playing = False
    g._images_dir = Path("/tmp")
    loaded = []

    def fake(cc, value):
        loaded.append((cc, value))
        g._anim_textures = [object(), object(), object()]
        g._anim_interval = 0.1
        g._anim_idx = 0
        g._anim_elapsed = 0.0
        return True

    g._load_anim = fake
    g._redraw = lambda *_a, **_k: None
    assert g.play_idle_gesture(0)
    assert loaded[-1] == (IDLE_EYES_CC, 14)
    assert g._gesture and g._gesture_value == 14
    g._tick_gesture(0.25)
    assert g._anim_idx == 2
    g._tick_gesture(0.1)
    assert not g._gesture
    assert loaded[-1] == (IDLE_EYES_CC, IDLE_EYES_VALUE)
    assert g._idle_active
    g.playing = True
    assert g.play_idle_gesture(1) is False
    print("  LIVE: el pad en pausa hace el gesto y vuelve al parpadeo OK")


def test_live_parpadeo_pausa_y_rearranca():
    from screens.live_view import LiveGrid

    _kivy()
    g = LiveGrid()
    g.playing = False
    g._idle_active = True
    g._anim_textures = [object(), object(), object()]
    g._blink_base_interval = 0.1
    g._anim_interval = 0.1
    g._idle_wait = 0.0
    g._anim_idx = 0
    g._anim_elapsed = 0.0
    g._tick_idle(0.25)
    assert g._anim_idx == 2
    assert g._tick_idle(0.1)
    assert g._idle_wait > 0
    assert g._anim_idx == 2
    g._tick_idle(g._idle_wait + 0.01)
    assert g._anim_idx == 0
    assert g._idle_wait == 0.0
    print("  LIVE: el parpadeo espera y vuelve al primer frame OK")


def test_al_parar_se_vacía_la_cache_y_precarga_los_gestos():
    import screens.live_view as lv
    from screens.live_view import LiveGrid

    _kivy()
    g = LiveGrid()
    g._redraw = lambda *_a, **_k: None
    g._images_dir = Path("/tmp/images")
    g._img_cache["song"] = object()
    seen = []

    def frames(_images_dir, _cc, value):
        seen.append(value)
        return [Path(f"/tmp/{value}a.png"), Path(f"/tmp/{value}b.png")]

    def load(path, punch_dark=False, punch_lyric=False):
        return str(path)

    old_frames, old_load = lv.anim_frame_paths, lv._load_rgba_texture
    lv.anim_frame_paths = frames
    lv._load_rgba_texture = load
    try:
        g.preload_idle_gestures()
        assert "song" not in g._img_cache
        assert not g._idle_prepared
        assert seen == [3, 14, 15, 16, 17]
        g.preload_idle_gestures()
        g.preload_idle_gestures()
        assert g._idle_prepared
        assert g._idle_preload is None
        assert len(g._img_cache) == 10
        assert seen == [3, 14, 15, 16, 17]
        g.drop_idle_cache()
        assert g._img_cache == {}
        assert not g._idle_prepared
        g._img_cache["song-frame"] = 1
        g.drop_idle_cache()
        assert g._img_cache == {"song-frame": 1}
    finally:
        lv.anim_frame_paths = old_frames
        lv._load_rgba_texture = old_load
    print("  LIVE: al parar se vacía la cache y se precargan los gestos OK")


if __name__ == "__main__":
    test_hit_pad_notes()
    test_mdcc_hold_and_hit()
    test_robot_channel_gap_keeps_screen()
    test_mute_flag()
    test_anim_helpers()
    test_live_grid_combo_pulse()
    test_live_grid_ribbon_comparte_el_modulo_de_las_robotas()
    test_live_grid_01_es_chispazo()
    test_el_negro_del_ojo_no_tapa_el_fondo()
    test_frame_de_ojos_deja_el_fondo()
    test_gesto_rgb_tambien_deja_el_fondo()
    test_live_ojos_en_pausa()
    test_live_pad_en_pausa_hace_el_gesto_y_vuelve_a_parpadear()
    test_live_parpadeo_pausa_y_rearranca()
    test_al_parar_se_vacía_la_cache_y_precarga_los_gestos()
    print("TODOS LOS TESTS OK")
