"""Test del controlador MIDI del reproductor (botones + knobs, del mixer).

Verifica:
  - `build_song_pots` (sinte/midi_control): knobs -> targets de
    robotraca.json de la canción, con los físicos del config.
  - `MidiControl.set_song`: aplica el robotraca.json al engine (mute/
    presence/vocoder/pad_volume/pads), reconfigura los knobs y apunta
    engine_ref. Los pads son SOLO por canción (clave "pads" contra la
    biblioteca pads/): sin la clave, vacíos, sin banco global.
  - `MidiControl.open` no abre nada sin interfaz configurada (sin auto).
  - App: al cargar la canción se aplica su mute de robotraca.json, y los
    botones del controlador (up/down/play/stop) llegan por ui_queue y
    ejecutan la acción (up/down cambian de canción).
"""

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from midi_ctrl import MidiControl  # noqa: E402
from sinte_bridge import build_song_pots  # noqa: E402
from songs import DEFAULT_SONGS  # noqa: E402

# Mismo mapeo físico que config.py DEFAULTS (LPD8, knobs CC 70-77 canal 0).
HW_POTS = {f"pot{i}": {"cc": f"cc:0:{69 + i}"} for i in range(1, 9)}


class StubChannel:
    def __init__(self, idx):
        self.idx = idx
        self.fx_presence = False
        self.vocoder_out = False
        self.fx_amounts = {}
        self.fx_mix = {}


class StubEngine:
    """Solo lo que toca apply_song_config: sin audio ni proyecto."""

    def __init__(self):
        self.muted = set()
        self.channels = [StubChannel(i) for i in range(8)]
        self.base_master = 0.5
        self.master = 0.5
        self.pad_volume_map = {}
        self.pad_volume_default = 0.5
        self.pad_names = [None] * 8
        self.pad_samples = [None] * 8
        self.reloads = 0            # veces que se pidió el banco global
        self.pad_bank = None        # (meta, base) del último load_pad_bank
        self.events = []            # push_event recibidos

    def push_event(self, *args):
        self.events.append(args)

    def reload_pad_samples(self):
        self.reloads += 1

    def load_pad_bank(self, meta, base):
        self.pad_bank = (dict(meta), base)
        self.pad_names = [None] * 8
        for i in range(8):
            rel = meta.get(str(i + 1))
            if rel:
                self.pad_names[i] = rel


def test_build_song_pots():
    """build_song_pots: targets de robotraca.json sobre los físicos del
    config; los knobs sin target en la canción se quedan fuera."""
    cfg = {"pots": {"pot1": "2:acid", "pot8": "0:tempo:50"},
           "pots_red": ["pot3"]}
    pots, pots_red = build_song_pots(HW_POTS, cfg)
    assert len(pots) == 2, f"deben quedar 2 knobs, no {pots}"
    spec, target, idx = pots[0]
    assert spec == ("control_change", 0, 70) and idx == 0
    assert target == ((2,), "acid", 1.0)
    spec, target, idx = pots[1]
    assert spec == ("control_change", 0, 77) and idx == 7
    assert target == ((0,), "tempo", 0.5)     # tope 50%
    assert pots_red == [(("control_change", 0, 72), 3)], pots_red
    # canción sin pots: sin knobs y sin red
    assert build_song_pots(HW_POTS, {}) == ([], [])
    print("  build_song_pots OK")


def test_midictrl_set_song():
    """MidiControl.set_song: robotraca.json al engine + knobs + engine_ref."""
    engine = StubEngine()
    with tempfile.TemporaryDirectory() as tmp:
        pads_dir = Path(tmp) / "pads"       # biblioteca de pads
        pads_dir.mkdir()
        ctrl = MidiControl(buttons={}, hw_pots=HW_POTS, pad_volume=60,
                           pads_dir=pads_dir)
        cfg = {"mute": [3, 7],
               "presence": [2],
               "vocoder": [3],
               "pad_volume": {"1": 27},
               "pads": {"1": "hola.wav", "4": "adios.wav"},
               "pots": {"pot2": "5:bode"}}
        song_dir = Path(tmp) / "song"
        song_dir.mkdir()
        (song_dir / "robotraca.json").write_text(json.dumps(cfg))
        ctrl.set_song(engine, song_dir)
        assert engine.muted == {3, 7}, engine.muted
        assert engine.channels[2].fx_presence
        assert engine.channels[3].vocoder_out
        assert not engine.channels[0].fx_presence
        assert engine.pad_volume_map == {0: 0.27}, engine.pad_volume_map
        assert engine.pad_volume_default == 0.6     # 60 del config
        # pads por canción: load_pad_bank contra la biblioteca de pads
        assert engine.pad_bank == ({"1": "hola.wav", "4": "adios.wav"},
                                   pads_dir), engine.pad_bank
        assert engine.pad_names[0] == "hola.wav"
        assert engine.pad_names[3] == "adios.wav"
        assert engine.pad_names[1] is None
        assert engine.reloads == 0, "con 'pads' no se toca el banco global"
        assert len(ctrl.pots) == 1, ctrl.pots
        spec, target, idx = ctrl.pots[0]
        assert spec == ("control_change", 0, 71) and idx == 1
        assert target == ((5,), "bode", 1.0)
        assert ctrl.engine_ref["engine"] is engine
        # sin robotraca.json: sin mute, knobs sin targets, pads VACÍOS
        # (sin banco global: load_pad_bank con dict vacío, nunca reload)
        ctrl.set_song(engine, Path(tmp))
        assert engine.muted == set()
        assert ctrl.pots == []
        assert engine.pad_bank == ({}, pads_dir), engine.pad_bank
        assert engine.reloads == 0, "sin 'pads' no se recarga ningún banco"
    print("  MidiControl.set_song OK")


def test_assign_pad_y_volumen():
    """assign_pad/set_pad_volume de la pantalla PADS: quedan EN MEMORIA
    (cfg + engine en vivo) y solo save() los persiste en robotraca.json."""
    engine = StubEngine()
    with tempfile.TemporaryDirectory() as tmp:
        pads_dir = Path(tmp) / "pads"       # biblioteca de pads
        pads_dir.mkdir()
        ctrl = MidiControl(buttons={}, hw_pots={}, pad_volume=60,
                           pads_dir=pads_dir)
        song_dir = Path(tmp) / "song"
        song_dir.mkdir()
        cfg_file = song_dir / "robotraca.json"
        cfg_file.write_text(json.dumps({"pad_volume": 60}))
        ctrl.set_song(engine, song_dir)

        # asignar: en vivo sobre el engine pero SIN persistir aún
        ctrl.assign_pad(1, "hola.wav")
        assert json.loads(cfg_file.read_text()) == {"pad_volume": 60}, \
            "sin save() el robotraca.json no cambia"
        assert engine.pad_bank == ({"1": "hola.wav"}, pads_dir), \
            engine.pad_bank
        assert engine.pad_names[0] == "hola.wav"
        assert ctrl.pads_state() == [("hola.wav", 60), (None, 60),
                                     (None, 60), (None, 60)], \
            ctrl.pads_state()

        # save() persiste la clave "pads"
        ctrl.save()
        cfg = json.loads(cfg_file.read_text())
        assert cfg["pads"] == {"1": "hola.wav"}, cfg

        # quitar: la clave "pads" se queda (vacía): los pads son de la
        # canción, no se resucita el banco global
        ctrl.assign_pad(3, "tres.wav")
        ctrl.assign_pad(1, None)
        ctrl.save()
        cfg = json.loads(cfg_file.read_text())
        assert cfg["pads"] == {"3": "tres.wav"}, cfg
        assert engine.pad_bank[0] == {"3": "tres.wav"}
        assert engine.pad_names[0] is None
        assert engine.pad_names[2] == "tres.wav"

        # pad fuera de rango: se ignora (sin romper ni guardar)
        ctrl.assign_pad(0, "cero.wav")
        ctrl.assign_pad(5, "cinco.wav")
        ctrl.save()
        assert json.loads(cfg_file.read_text())["pads"] == {"3": "tres.wav"}

        # volumen de un pad: el "pad_volume" 60 (número) se reparte a los 4
        ctrl.set_pad_volume(2, 80)
        assert json.loads(cfg_file.read_text())["pad_volume"] == 60, \
            "sin save() el volumen no se persiste"
        assert engine.pad_volume_map[0] == 0.6
        assert engine.pad_volume_map[1] == 0.8
        assert ctrl.pads_state() == [(None, 60), (None, 80),
                                     ("tres.wav", 60), (None, 60)], \
            ctrl.pads_state()
        ctrl.save()
        cfg = json.loads(cfg_file.read_text())
        assert cfg["pad_volume"] == {"1": 60, "2": 80, "3": 60, "4": 60}, cfg

        # clamp 0-100 y pad fuera de rango
        ctrl.set_pad_volume(4, 150)
        assert engine.pad_volume_map[3] == 1.0
        ctrl.set_pad_volume(4, -20)
        assert engine.pad_volume_map[3] == 0.0
        ctrl.set_pad_volume(9, 50)      # fuera de rango: no cambia nada
        ctrl.save()
        assert json.loads(cfg_file.read_text())["pad_volume"]["4"] == 0
    print("  assign_pad y volumen OK")


def test_midictrl_botones_parseados():
    """Regresión: MidiControl debe parsear los specs "note:canal:nota" del
    config ANTES de pasarlos a open_midi_input. match_button espera tuplas
    ya parseadas; con cadenas hacía `mtype, ch, num = "note:9:41"` ->
    ValueError dentro del callback de mido (el MIDI moría en silencio)."""
    from sinte_bridge import match_button
    ctrl = MidiControl(buttons={"play": "note:9:41",
                                "pot_roto": "chorizo"},
                       hw_pots={}, pad_volume=45)
    assert ctrl.buttons["play"] == ("note_on", 9, 41), ctrl.buttons
    assert ctrl.buttons["pot_roto"] is None          # inválido: se ignora
    # un note_on real del LPD8 debe casar y devolver la acción
    msg = type("Msg", (), {"type": "note_on", "channel": 9,
                           "note": 41, "velocity": 127})
    assert match_button(ctrl.buttons, msg) == "play"
    print("  MidiControl botones parseados OK")


def test_pots_state_y_edicion():
    """pots_state/set_pot_* de la pantalla EFECTOS: canal/efecto/% por knob
    (1/2/5/6), en memoria ("pots" y "fx_mix" del robotraca.json) con los
    targets en vivo reconstruidos (self.pots) y el fx_mix al engine por
    push_event. Sin save(), el JSON no cambia."""
    engine = StubEngine()
    with tempfile.TemporaryDirectory() as tmp:
        pads_dir = Path(tmp) / "pads"       # biblioteca de pads
        pads_dir.mkdir()
        ctrl = MidiControl(buttons={}, hw_pots=HW_POTS, pad_volume=45,
                           pads_dir=pads_dir)
        song_dir = Path(tmp) / "song"
        song_dir.mkdir()
        cfg = {"pots": {"pot1": "2:acid"},
               "fx_mix": {"2": {"acid": 40}}}
        cfg_file = song_dir / "robotraca.json"
        cfg_file.write_text(json.dumps(cfg))
        ctrl.set_song(engine, song_dir)
        assert ctrl.pots_state() == [(3, "acid", 40), (None, None, 100),
                                     (None, None, 100), (None, None, 100)], \
            ctrl.pots_state()
        assert ctrl.pots[0][1] == ((2,), "acid", 1.0), ctrl.pots

        # canal +1: spec "canal-1:efecto" en memoria, targets al momento
        ctrl.set_pot_canal(1, 1)
        assert ctrl.pots_state()[0] == (4, "acid", 100), ctrl.pots_state()
        assert ctrl._cfg["pots"] == {"pot1": "3:acid"}, ctrl._cfg["pots"]
        assert ctrl.pots[0][1] == ((3,), "acid", 1.0)

        # efecto +1: acid -> acid_lfo (orden de EFFECT_PRESETS)
        ctrl.set_pot_efecto(1, 1)
        assert ctrl.pots_state()[0][1] == "acid_lfo"
        assert ctrl._cfg["pots"] == {"pot1": "3:acid_lfo"}

        # % -5: fx_mix del canal/efecto actual, en vivo por push_event
        ctrl.set_pot_mix(1, -5)
        assert ctrl._cfg["fx_mix"] == {"2": {"acid": 40},
                                       "3": {"acid_lfo": 95}}, \
            ctrl._cfg["fx_mix"]
        assert ("fx_mix", 3, "acid_lfo", 95) in engine.events, engine.events

        # sin save(), el robotraca.json no cambia
        assert json.loads(cfg_file.read_text()) == cfg
        ctrl.save()
        disk = json.loads(cfg_file.read_text())
        assert disk["pots"] == {"pot1": "3:acid_lfo"}, disk
        assert disk["fx_mix"] == {"2": {"acid": 40},
                                  "3": {"acid_lfo": 95}}, disk

        # efecto a "off" (cicla): target fuera y sin fx_mix tocado
        while ctrl.pots_state()[0][1] is not None:
            ctrl.set_pot_efecto(1, 1)
        assert "pot1" not in ctrl._cfg["pots"], ctrl._cfg["pots"]
        assert ctrl.pots == [], ctrl.pots

        # canción sin "pots": borrador en cualquier orden (canal primero)
        ctrl.set_song(engine, Path(tmp))
        ctrl.set_pot_canal(5, 1)            # pot5, sin target: borrador
        assert ctrl.pots_state()[2] == (1, None, 100), ctrl.pots_state()
        ctrl.set_pot_efecto(5, 1)           # primer efecto: valve
        assert ctrl._cfg["pots"] == {"pot5": "0:valve"}, ctrl._cfg["pots"]
        assert ctrl.pots_state()[2] == (1, "valve", 100)
        assert ctrl.pots[0][1] == ((0,), "valve", 1.0)

        # borrador en el otro orden (efecto primero, por la lista del
        # picker): set_pot_efecto_nombre guarda el draft y, al elegir el
        # canal después, se compone la spec
        ctrl.set_song(engine, Path(tmp))
        ctrl.set_pot_efecto_nombre(6, "delay")      # pot6: efecto sin canal
        assert ctrl.pots_state()[3] == (None, "delay", 100), \
            ctrl.pots_state()
        assert "pot6" not in ctrl._cfg["pots"], ctrl._cfg["pots"]
        ctrl.set_pot_canal(6, 1)                    # canal después
        assert ctrl._cfg["pots"] == {"pot6": "0:delay"}, ctrl._cfg["pots"]
        assert ctrl.pots_state()[3] == (1, "delay", 100)
        # "off" desde la lista deja el knob sin target
        ctrl.set_pot_efecto_nombre(6, "off")
        assert "pot6" not in ctrl._cfg["pots"], ctrl._cfg["pots"]
        assert ctrl.pots == [], ctrl.pots
    print("  pots_state y set_pot_* OK")


def test_on_trigger_hook():
    """El hook on_trigger (asegurar el stream al disparar un pad, para que
    los pads suenen sin reproducción) viaja en engine_ref, que el callback
    MIDI evalúa en cada mensaje."""
    hook = lambda: None
    ctrl = MidiControl(buttons={}, hw_pots={}, pad_volume=45,
                       on_trigger=hook)
    assert ctrl.engine_ref["on_trigger"] is hook
    ctrl2 = MidiControl(buttons={}, hw_pots={}, pad_volume=45)
    assert "on_trigger" not in ctrl2.engine_ref, \
        "sin hook, el callback no debe llamar a nada"
    ctrl.close()
    ctrl2.close()
    print("  on_trigger en engine_ref OK")


def test_midictrl_open_sin_auto():
    """Sin interfaz configurada (None) no abre nada: el primer puerto del
    sistema podría ser la interfaz de notas, no la de control."""
    ctrl = MidiControl(buttons={}, hw_pots={}, pad_volume=45)
    llamadas = []

    def fake_open(port, *_args, **_kw):
        llamadas.append(port)
        return object()

    import midi_ctrl as mc
    original = mc.open_midi_input
    mc.open_midi_input = fake_open
    try:
        assert ctrl.open(None) is False
        assert llamadas == [], "None no debe llegar a open_midi_input"
        assert ctrl.open("LPD8") is True
        assert llamadas == ["LPD8"]
    finally:
        mc.open_midi_input = original
    ctrl.close()
    print("  MidiControl.open sin auto OK")


def _song_with_robotraca():
    """Primera canción de DEFAULT_SONGS con robotraca.json (y su config)."""
    for song_dir in sorted(Path(DEFAULT_SONGS).iterdir()):
        cfg_file = song_dir / "robotraca.json"
        if cfg_file.is_file():
            return song_dir, json.loads(cfg_file.read_text())
    raise AssertionError(f"ninguna canción con robotraca.json en "
                         f"{DEFAULT_SONGS}")


def _run(app):
    from robotracker2 import Robotracker2App  # noqa: E402

    assert isinstance(app, Robotracker2App)
    app._midi_ctrl.close()      # sin puertos reales en los tests

    songs = app.load_screen.songs
    assert songs, "debe haber canciones"
    song_dir, cfg = _song_with_robotraca()

    # --- cargar la canción aplica su robotraca.json (mute incluido) --------
    app._request_load(song_dir)
    assert app.editor_screen.current == "song"
    assert app._song_dir == song_dir
    expected_mute = set(cfg.get("mute", []))
    assert app.player.engine.muted == expected_mute, \
        f"mute de robotraca.json no aplicado: {app.player.engine.muted}"
    # los knobs de la canción quedan configurados en el controlador
    assert len(app._midi_ctrl.pots) == len(
        [k for k, t in cfg.get("pots", {}).items() if t]), \
        f"knobs no reconfigurados: {app._midi_ctrl.pots}"

    # --- botones del controlador por ui_queue (drenada en _tick) -----------
    idx = songs.index(song_dir)
    down = songs[(idx + 1) % len(songs)]
    up = songs[idx]

    app._midi_ctrl.ui_queue.put("down")
    app._tick(0)
    assert app._song_dir == down, "down debe cambiar a la siguiente canción"
    app._midi_ctrl.ui_queue.put("up")
    app._tick(0)
    assert app._song_dir == up, "up debe volver a la anterior"

    # play/stop sin audio (tests headless): no deben reventar. Sin stream el
    # play no arranca y el stop es un push_event inerte.
    from player import Player
    Player._ensure_stream = lambda self: False
    app._midi_ctrl.ui_queue.put("play")
    app._tick(0)
    app._midi_ctrl.ui_queue.put("stop")
    app._tick(0)
    assert not app.player.playing
    # acción desconocida ("calib", sampleN sin canción): se ignora
    app._midi_ctrl.ui_queue.put("calib")
    app._tick(0)
    print("  botones del controlador en la app OK")


def main():
    from robotracker2 import Robotracker2App  # noqa: E402

    test_build_song_pots()
    test_midictrl_set_song()
    test_assign_pad_y_volumen()
    test_midictrl_botones_parseados()
    test_midictrl_open_sin_auto()
    test_on_trigger_hook()
    test_pots_state_y_edicion()

    app = Robotracker2App(songs_dir=DEFAULT_SONGS)

    def _go(_dt):
        try:
            _run(app)
            print("TODOS LOS TESTS OK")
        except Exception as exc:                 # noqa: BLE001
            import traceback
            traceback.print_exc()
        finally:
            app.stop()

    Clock.schedule_once(_go, 0)
    app.run()


if __name__ == "__main__":
    main()
