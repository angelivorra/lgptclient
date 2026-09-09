"""Test del pintado MIDI en vivo en PHRASE (R2+START).

Verifica:
  - `PhraseGrid.live_note`: pinta nota + instrumento por defecto y guarda la
    velocidad como VOLM (vel*2) en el primer hueco de FX libre (o actualiza
    el VOLM existente) sin pisar otros efectos.
  - Canal de robotas: la nota pinta el golpe (HIT) con el instrumento fijo.
  - App: R2+START alterna el modo MIDI live (con fakes para mido), con su
    indicador '●' en la cabecera, y los avisos de config/no-disponible.
  - App: `_paint_midi_notes` pinta en el step del playhead solo si la phrase
    que suena es la que se está editando.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from types import SimpleNamespace

from controls import L2, R2, RIGHT, START  # noqa: E402
from lgpt_model import CHAIN_LEN, EMPTY, NUM_TRACKS  # noqa: E402
from midi_input import midi_note_event  # noqa: E402
from songs import DEFAULT_SONGS  # noqa: E402


def _clear_step(pg, step, track):
    """Deja el step de la phrase vacío (la phrase real puede traer datos)."""
    p = pg.pv.project
    i = pg.pv._index(step, track)
    p.notes[i] = EMPTY
    p.instruments[i] = EMPTY
    p.cmd1[i] = "----"
    p.param1[i] = 0
    p.cmd2[i] = "----"
    p.param2[i] = 0


def _goto_phrase(app, row, chain_idx, phrase_idx):
    """SONG -> CHAIN -> PHRASE con `chain_idx` en (row,0) apuntando su step 0
    a `phrase_idx`. Devuelve el PhraseGrid."""
    ed = app.editor_screen
    if ed.current != "song":
        ed.goto("song")          # vuelve a la base antes de navegar
    g = ed.song_grid
    p = g.view.project
    g.cursor_row, g.cursor_track = row, 0
    g.view.set_value(row, 0, chain_idx)
    p.chains[chain_idx * CHAIN_LEN + 0] = phrase_idx
    app._dispatch(RIGHT, {RIGHT, L2})
    assert ed.current == "chain", "debe estar en CHAIN"
    app._dispatch(RIGHT, {RIGHT, L2})
    assert ed.current == "phrase", "debe estar en PHRASE"
    return ed.phrase_grid


def _test_live_note(app):
    pg = _goto_phrase(app, 0, 0x05, 0x20)
    t = pg.track
    _clear_step(pg, 0, t)
    # nota + instrumento por defecto + VOLM con la velocidad (100 -> 0x00C8)
    pg.live_note(0, 60, 100)
    assert pg._note(0) == 60, "la nota debe pintarse"
    assert pg._instr(0) == 0, "instrumento por defecto 0"
    assert pg._cmd(0, 1) == "VOLM", f"fx1 debe ser VOLM, hay {pg._cmd(0, 1)}"
    assert pg._prm(0, 1) == 200, "vel 100 -> VOLM 00C8"
    assert pg._cmd(0, 2) is None, "fx2 debe seguir libre"
    print("  live_note pinta nota+instr+vel OK")

    # segunda pulsación en el mismo step: actualiza la nota y el VOLM
    pg.live_note(0, 62, 50)
    assert pg._note(0) == 62
    assert pg._prm(0, 1) == 100, "el VOLM existente se actualiza (50*2)"
    assert pg._cmd(0, 2) is None, "fx2 sigue libre tras actualizar VOLM"
    print("  live_note actualiza nota/VOLM sin duplicar OK")

    # fx1 ocupado: la velocidad va al primer hueco libre (fx2)
    pg.pv.set_fx_cmd(0, t, 1, "KILL")
    pg.pv.set_fx_param(0, t, 1, 0x0005)
    pg.live_note(0, 65, 120)
    assert pg._cmd(0, 1) == "KILL", "no pisa fx1"
    assert pg._cmd(0, 2) == "VOLM", "velocidad en fx2"
    assert pg._prm(0, 2) == 240, "vel 120 -> VOLM 00F0"
    print("  live_note usa el hueco de FX libre OK")

    # fx1 y fx2 ocupados: pinta la nota pero no pisa ningún efecto
    pg.pv.set_fx_cmd(0, t, 2, "TABL")
    pg.pv.set_fx_param(0, t, 2, 0x0003)
    pg.live_note(0, 67, 90)
    assert pg._note(0) == 67, "la nota se pinta igualmente"
    assert pg._cmd(0, 1) == "KILL", "fx1 intacto"
    assert pg._cmd(0, 2) == "TABL", "fx2 intacto"
    print("  live_note con fx llenos no pisa nada OK")


def _test_live_note_robot(app):
    from screens.phrase_view import PhraseGrid

    ed = app.editor_screen
    p = ed.song_grid.view.project
    # phrase 0x21 para el canal 8 (track 7) en la fila 1
    p.song[1 * NUM_TRACKS + 7] = 0x06
    p.chains[0x06 * CHAIN_LEN + 0] = 0x21
    pg = PhraseGrid()
    pg.set_context(p, 1, 7, 0)
    _clear_step(pg, 0, 7)
    pg.live_note(0, 62, 100)          # BOMBO con velocidad
    assert pg._note(0) == 62, "el golpe se pinta"
    assert pg._instr(0) == 0x80, "canal de robotas usa el instrumento fijo"
    assert pg._cmd(0, 1) == "VOLM", "velocidad guardada en fx1"
    assert pg._prm(0, 1) == 200
    print("  live_note en canal de robotas OK")


def _test_toggle(app):
    import robotracker2 as r2mod

    ed = app.editor_screen
    app.config["midi_notes"] = "PuertoTest"

    class _FakeMidi:
        def __init__(self, events=None):
            self.opened = None
            self.closed = 0
            self._active = False
            self._events = events or []
            self.error = None

        @property
        def active(self):
            return self._active

        def open_port(self, name):
            self.opened = name
            self._active = True
            return True

        def close(self):
            self.closed += 1
            self._active = False

        def poll(self):
            return self._events

    app._midi_notes = _FakeMidi()
    r2mod.midi_input_names = lambda: ["PuertoTest"]

    # R2+START -> ON
    app._fresh_press = True
    app._dispatch(START, {START, R2})
    assert app.midi_live, "R2+START debe activar el modo"
    assert ed.live_ind.text == "●", "debe verse el indicador ●"
    assert app._midi_notes.opened == "PuertoTest"
    print("  R2+START activa MIDI live OK")

    # R2+START -> OFF (el puerto se queda abierto: hotplug / preview)
    app._fresh_press = True
    app._dispatch(START, {START, R2})
    assert not app.midi_live, "R2+START debe desactivar el modo"
    assert ed.live_ind.text == "", "el indicador se oculta"
    assert app._midi_notes.active, "el puerto no se cierra al apagar live"
    print("  R2+START desactiva MIDI live OK")

    # sin interfaz configurada: aviso y no activa
    app.config["midi_notes"] = None
    app._fresh_press = True
    app._dispatch(START, {START, R2})
    assert not app.midi_live
    assert "Configura" in ed.toast.text, "aviso de config pendiente"
    print("  sin MIDI Notas configurado avisa OK")

    # interfaz guardada pero no disponible: aviso y no activa
    app.config["midi_notes"] = "PuertoTest"
    r2mod.midi_input_names = lambda: []
    app._fresh_press = True
    app._dispatch(START, {START, R2})
    assert not app.midi_live
    assert "no disponible" in ed.toast.text, "aviso de interfaz no disponible"
    print("  interfaz no disponible avisa OK")

    # el id ALSA cambia de puerto USB: sigue siendo el LPK25
    app.config["midi_notes"] = "LPK25:LPK25 MIDI 1 16:0"
    r2mod.midi_input_names = lambda: ["LPK25:LPK25 MIDI 1 24:0"]
    app._midi_notes = _FakeMidi()
    app._fresh_press = True
    app._dispatch(START, {START, R2})
    assert app.midi_live, "el LPK25 debe cogerse con otro client ALSA"
    assert app._midi_notes.opened == "LPK25:LPK25 MIDI 1 16:0"
    app._set_midi_live(False)
    print("  LPK25 con otro puerto USB / id ALSA OK")


def _test_paint(app):
    ed = app.editor_screen
    pg = _goto_phrase(app, 2, 0x07, 0x22)
    t = pg.track
    assert pg.pv.phrase_of(t) == 0x22
    for step in range(16):
        _clear_step(pg, step, t)

    class _Chan:
        def __init__(self, phrase, pos):
            self.playing = True
            self.phrase = phrase
            self.phrase_pos = pos

    class _Eng:
        def __init__(self, chans):
            self.channels = chans

    class _Player:
        def __init__(self, chans):
            self.playing = True
            self.engine = _Eng(chans)

        def close(self):
            pass

    class _FakeMidi:
        def __init__(self, notes):
            self._notes = notes
            self._active = True

        @property
        def active(self):
            return self._active

        def poll(self):
            notes, self._notes = self._notes, []
            return notes

        def close(self):
            self._active = False

        def open_port(self, name):
            self._active = True
            return True

    # el canal toca la phrase editada en el step 3 -> pinta ahí
    app.player = _Player([_Chan(0x22, 3)] * NUM_TRACKS)
    app._midi_notes = _FakeMidi([("on", 60, 100), ("on", 62, 127)])
    app._paint_midi_notes()
    assert pg._note(3) == 62, "nota pintada en el step del playhead"
    assert pg._instr(3) == 0
    assert pg._cmd(3, 1) == "VOLM"
    assert pg._prm(3, 1) == 254, "vel 127 -> VOLM 00FE"
    print("  _paint_midi_notes pinta en el step del playhead OK")

    # el canal toca OTRA phrase -> no pinta nada
    app.player = _Player([_Chan(0x55, 7)] * NUM_TRACKS)
    app._midi_notes = _FakeMidi([("on", 70, 80)])
    app._paint_midi_notes()
    assert pg._note(7) is None, "no pinta si la phrase que suena no es la editada"
    assert pg._note(3) == 62, "los datos previos no cambian"
    print("  _paint_midi_notes ignora si suena otra phrase OK")

    # sin play -> no pinta
    app.player = _Player([_Chan(0x22, 5)] * NUM_TRACKS)
    app.player.playing = False
    app._midi_notes = _FakeMidi([("on", 72, 80)])
    app._paint_midi_notes()
    assert pg._note(5) is None, "sin play no se pinta"
    print("  _paint_midi_notes sin play no pinta OK")


def _test_midi_note_event():
    on = SimpleNamespace(type="note_on", note=60, velocity=100)
    assert midi_note_event(on) == ("on", 60, 100)
    off = SimpleNamespace(type="note_off", note=61, velocity=40)
    assert midi_note_event(off) == ("off", 61, 0)
    zero = SimpleNamespace(type="note_on", note=62, velocity=0)
    assert midi_note_event(zero) == ("off", 62, 0)
    cc = SimpleNamespace(type="control_change", note=0, velocity=0)
    assert midi_note_event(cc) is None
    print("  midi_note_event on/off/vel0 OK")


def _test_hotplug(app):
    """Enchufar el LPK25 a posteriori (otro id ALSA) lo abre solo."""
    import robotracker2 as r2mod

    fake = type("N", (), {})()
    fake.opened = None
    fake.closed = 0
    fake._active = False
    fake.error = None

    def open_port(name):
        fake.opened = name
        fake._active = True
        return True

    def close():
        fake.closed += 1
        fake._active = False

    fake.open_port = open_port
    fake.close = close
    fake.poll = lambda: []
    type(fake).active = property(lambda self: fake._active)

    orig_notes = app.config.get("midi_notes")
    orig_ctrl = app.config.get("midi_control")
    app._midi_notes = fake
    app._midi_hotplug = True
    app._midi_ports_retry = 0.0
    app.config["midi_notes"] = "LPK25:LPK25 MIDI 1 16:0"
    app.config["midi_control"] = None

    r2mod.midi_input_names = lambda: []
    app._ensure_midi_ports()
    assert fake.opened is None, "sin teclado no abre"
    print("  hotplug sin LPK25 no abre OK")

    app._midi_ports_retry = 0.0
    r2mod.midi_input_names = lambda: ["LPK25:LPK25 MIDI 1 24:0"]
    app._ensure_midi_ports()
    assert fake.opened == "LPK25:LPK25 MIDI 1 16:0", fake.opened
    assert fake._active
    print("  hotplug enciende el LPK25 con otro id ALSA OK")

    app._midi_ports_retry = 0.0
    r2mod.midi_input_names = lambda: []
    app._ensure_midi_ports()
    assert fake.closed >= 1, "al desenchufar cierra"
    print("  hotplug cierra al desenchufar OK")

    app._midi_hotplug = False
    app.config["midi_notes"] = orig_notes
    app.config["midi_control"] = orig_ctrl


def _run(app):
    app._midi_hotplug = False
    app._midi_notes.close()
    app._midi_ctrl.close()
    songs = app.load_screen.songs
    assert songs, "debe haber canciones"
    app._request_load(songs[0])
    assert app.editor_screen.current == "song"

    _test_midi_note_event()
    _test_live_note(app)
    _test_live_note_robot(app)
    _test_hotplug(app)
    _test_toggle(app)
    _test_paint(app)


def main():
    from robotracker2 import Robotracker2App  # noqa: E402

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

