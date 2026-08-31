"""Test de Compact Sequencer / Compact Instruments (menú PROJECT).

Semántica del LGPT original (Project::Purge / PurgeInstruments): borrado
in-place SIN renumerar. Compact Sequencer borra las chains que la song no
usa y las phrases que ninguna chain usada referencia (directo, sin diálogo).
Compact Instruments elimina del banco los instrumentos que NINGUNA phrase
referencia (se miran TODAS las frases, también las de chains no usadas) y
pregunta (Sí/No) si borrar del disco los .wav sin usar de samples/.

Flujo e2e sobre una canción copiada a un directorio temporal (nunca toca
las canciones versionadas de sinte/songs/): injectar un instrumento Sample
sin referencia + un wav huérfano, play, PROJECT -> Compact Sequencer (A),
Compact Instruments (A) -> diálogo (No por defecto no borra; Sí borra;
B cierra sin borrar) y roundtrip guardar+recargar (el writer no resucita
los instrumentos popeados).
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from controls import A, B, DOWN, L2, LEFT, START, UP  # noqa: E402
from lgpt_model import (CHAIN_LEN, EMPTY, FX_EMPTY, PHRASE_LEN,
                        compact_instruments, compact_sequencer,
                        load_project)  # noqa: E402
from robots import ROBOT_INSTR  # noqa: E402
from sinte_bridge import LGPTProject  # noqa: E402
from songs import DEFAULT_SONGS  # noqa: E402


def _make_project(tmp: Path) -> LGPTProject:
    """Proyecto sintético como make_project de sinte/tests/test_engine.py."""
    p = LGPTProject(tmp)
    p.root = object()
    p.project = {"tempo": "120", "master": "100", "transpose": "0"}
    p.song = bytearray([EMPTY] * (8 * 256))
    p.chains = bytearray([EMPTY] * (255 * 16))
    p.transposes = bytearray(255 * 16)
    p.notes = bytearray([EMPTY] * (255 * 16))
    p.instruments = bytearray([EMPTY] * (255 * 16))
    p.cmd1 = [FX_EMPTY] * (255 * 16)
    p.param1 = [0] * (255 * 16)
    p.cmd2 = [FX_EMPTY] * (255 * 16)
    p.param2 = [0] * (255 * 16)
    p.tables = {}
    p.grooves = bytearray()
    p.instrument_bank = {}
    return p


def _cancion_origen():
    """Cualquier canción real de sinte/songs (solo se usa su lgptsav.dat)."""
    for song_dir in sorted(Path(DEFAULT_SONGS).iterdir()):
        if (song_dir / "lgptsav.dat").is_file():
            return song_dir
    raise AssertionError(f"ninguna canción con lgptsav.dat en "
                         f"{DEFAULT_SONGS}")


def _unitarios(tmp: Path):
    """compact_sequencer y compact_instruments sobre proyectos sintéticos."""
    tmp.mkdir(exist_ok=True)
    # --- compact_sequencer ----------------------------------------------
    p = _make_project(tmp)
    p.song[0] = 0x05                    # fila 0, canal 0 -> chain 5 (usada)
    for s in range(CHAIN_LEN):
        p.chains[0x05 * CHAIN_LEN + s] = 0x10 + s   # steps -> phrases 10..1F
        p.transposes[0x05 * CHAIN_LEN + s] = s
    p.notes[0x10 * PHRASE_LEN] = 60                 # phrase 10 con contenido
    p.instruments[0x10 * PHRASE_LEN] = 0x01
    p.cmd1[0x11 * PHRASE_LEN] = "VOLM"              # phrase 11 con fx
    p.param1[0x11 * PHRASE_LEN] = 5
    # chain 7: contenido pero NO en la song -> se vacía
    p.chains[0x07 * CHAIN_LEN] = 0x20               # step 0 -> phrase 20
    p.transposes[0x07 * CHAIN_LEN] = 3
    p.notes[0x20 * PHRASE_LEN] = 61                 # phrase 20: solo de chain 7
    p.instruments[0x20 * PHRASE_LEN] = 0x02
    # phrase 30: sin referencia -> se vacía
    p.notes[0x30 * PHRASE_LEN] = 62
    p.cmd2[0x30 * PHRASE_LEN] = "KILL"
    p.param2[0x30 * PHRASE_LEN] = 9
    # phrase 31: ya vacía -> no cuenta

    n_c, n_p = compact_sequencer(p)
    assert (n_c, n_p) == (1, 2), (n_c, n_p)
    # chain 5 (usada) intacta
    assert p.chains[0x05 * CHAIN_LEN] == 0x10
    assert p.transposes[0x05 * CHAIN_LEN] == 0
    # chain 7 vaciada
    assert p.chains[0x07 * CHAIN_LEN:0x07 * CHAIN_LEN + CHAIN_LEN] == \
        bytes([EMPTY]) * CHAIN_LEN
    assert p.transposes[0x07 * CHAIN_LEN:0x07 * CHAIN_LEN + CHAIN_LEN] == \
        bytes(CHAIN_LEN)
    # phrases 10/11 (usadas por chain 5) intactas
    assert p.notes[0x10 * PHRASE_LEN] == 60
    assert p.cmd1[0x11 * PHRASE_LEN] == "VOLM"
    assert p.param1[0x11 * PHRASE_LEN] == 5
    # phrases 20 (solo de chain no usada) y 30 (huérfana) vaciadas
    i = 0x20 * PHRASE_LEN
    assert p.notes[i:i + PHRASE_LEN] == bytes([EMPTY]) * PHRASE_LEN
    assert p.instruments[i:i + PHRASE_LEN] == bytes([EMPTY]) * PHRASE_LEN
    i = 0x30 * PHRASE_LEN
    assert p.notes[i:i + PHRASE_LEN] == bytes([EMPTY]) * PHRASE_LEN
    assert p.cmd2[i] == FX_EMPTY and p.param2[i] == 0
    print("  compact_sequencer unitario OK")

    # --- compact_instruments --------------------------------------------
    p = _make_project(tmp)
    (tmp / "samples").mkdir(exist_ok=True)
    for name in ("a.wav", "b.wav", "c.wav", "zzz.wav"):
        (tmp / "samples" / name).write_bytes(b"RIFF dummy")
    p.song[0] = 0x00                    # chain 0 usada -> phrase 0
    p.chains[0] = 0x00
    p.notes[0 * PHRASE_LEN] = 60
    p.instruments[0 * PHRASE_LEN] = 0x01
    # frase de chain NO usada: su instrumento cuenta igual (fiel al original)
    p.chains[0x08 * CHAIN_LEN] = 0x09   # chain 8 no está en la song
    p.notes[0x09 * PHRASE_LEN] = 61
    p.instruments[0x09 * PHRASE_LEN] = 0x02
    p.instrument_bank = {
        0x01: {"type": "Sample", "params": {"sample": "a.wav", "volume": "128"}},
        0x02: {"type": "Sample", "params": {"sample": "b.wav", "volume": "100"}},
        0x03: {"type": "Sample", "params": {"sample": "c.wav", "volume": "90"}},
        0x81: {"type": "Midi", "params": {"channel": "3"}},
        ROBOT_INSTR: {"type": "Midi", "params": {"channel": "8"}},
    }
    n, unused = compact_instruments(p)
    assert n == 2, n                    # 0x03 y 0x81, no ROBOT_INSTR
    assert 0x01 in p.instrument_bank and 0x02 in p.instrument_bank
    assert 0x03 not in p.instrument_bank
    assert 0x81 not in p.instrument_bank
    assert ROBOT_INSTR in p.instrument_bank
    # a.wav/b.wav referenciados por los Sample restantes; c/zzz no
    assert unused == ["c.wav", "zzz.wav"], unused
    # ROBOT_INSTR sin referencias tampoco se popea (guarda de robotracker2)
    p.instruments[:] = bytes([EMPTY]) * len(p.instruments)
    n, _ = compact_instruments(p)
    assert ROBOT_INSTR in p.instrument_bank
    print("  compact_instruments unitario OK")

    # --- samples/ ausente: no rompe -------------------------------------
    p2 = _make_project(tmp / "sin_samples")
    p2.instrument_bank = {0x01: {"type": "Sample",
                                 "params": {"sample": "a.wav"}}}
    n, unused = compact_instruments(p2)
    assert n == 1 and unused == [], (n, unused)
    print("  compact_instruments sin samples/ OK")


def _e2e(app, song):
    from robotracker2 import Robotracker2App  # noqa: E402

    assert isinstance(app, Robotracker2App)
    app._midi_ctrl.close()      # sin puertos reales en los tests
    app._request_load(song)
    assert app.editor_screen.current == "song"
    p = app.editor_screen.project

    # inyectar un instrumento Sample sin referencia + su wav huérfano
    x = next(i for i in range(0x80) if i not in p.instrument_bank)
    p.instrument_bank[x] = {"type": "Sample",
                            "params": {"sample": "zzz_unused.wav"}}
    zzz = song / "samples" / "zzz_unused.wav"
    zzz.write_bytes(b"RIFF dummy")
    robot_ya = ROBOT_INSTR in p.instrument_bank

    # contenido en una chain NO usada (la borrará Compact Sequencer)
    used_c = {b for b in p.song if b != EMPTY}
    c = next(i for i in range(0x40, 0x80) if i not in used_c)
    used_ph = {b for b in p.chains if b != EMPTY}
    ph = next(i for i in range(0x20, 0xF0) if i not in used_ph)
    p.chains[c * CHAIN_LEN] = ph
    p.transposes[c * CHAIN_LEN] = 1
    p.notes[ph * PHRASE_LEN] = 60
    p.cmd1[ph * PHRASE_LEN] = "VOLM"
    p.param1[ph * PHRASE_LEN] = 5
    u = p.song[0]
    assert u != EMPTY, "la fila 0 debe usar una chain"
    u_snap = (bytes(p.chains[u * CHAIN_LEN:u * CHAIN_LEN + CHAIN_LEN]),
              bytes(p.transposes[u * CHAIN_LEN:u * CHAIN_LEN + CHAIN_LEN]))

    # --- play y navegación a PROJECT ------------------------------------
    app._dispatch(START, {START})
    assert app.player.engine.playing
    app._dispatch(UP, {UP, L2})         # SONG -> PROJECT
    assert app.editor_screen.current == "project"
    menu = app.editor_screen.project_menu
    assert menu.index == 0              # tempo (set_project resetea)
    print("  play + SONG -> PROJECT OK")

    # --- Compact Sequencer (A sobre la acción) ---------------------------
    app._dispatch(DOWN, {DOWN})         # tempo -> master
    app._dispatch(DOWN, {DOWN})         # master -> compact_seq (salta gap)
    assert menu.index == 3, menu.index
    app._dispatch(A, {A})
    app._release(A)
    # chain no usada vaciada, usada intacta, player parado, dirty
    assert p.chains[c * CHAIN_LEN:c * CHAIN_LEN + CHAIN_LEN] == \
        bytes([EMPTY]) * CHAIN_LEN
    assert p.transposes[c * CHAIN_LEN] == 0
    assert p.notes[ph * PHRASE_LEN] == EMPTY
    assert p.cmd1[ph * PHRASE_LEN] == FX_EMPTY and p.param1[ph * PHRASE_LEN] == 0
    assert (bytes(p.chains[u * CHAIN_LEN:u * CHAIN_LEN + CHAIN_LEN]),
            bytes(p.transposes[u * CHAIN_LEN:u * CHAIN_LEN + CHAIN_LEN])) \
        == u_snap, "la chain usada queda intacta"
    app.player.engine._drain_events()   # el "stop" viaja por eventos
    assert not app.player.engine.playing
    assert app.dirty
    print("  Compact Sequencer (A) OK")

    # --- Compact Instruments: pop + diálogo, "No" por defecto ------------
    app._dispatch(DOWN, {DOWN})         # compact_seq -> compact_instr
    assert menu.index == 4, menu.index
    app._dispatch(A, {A})
    app._release(A)
    assert x not in p.instrument_bank, "instrumento sin uso popedo"
    if robot_ya:
        assert ROBOT_INSTR in p.instrument_bank, "0x80 nunca se popea"
    assert x not in app.editor_screen.instrument_menu.instr_ids
    assert app.dialog is not None, "wav huérfano -> diálogo Sí/No"
    assert app.dialog.index == 1        # "No" por defecto (opción segura)
    app._dispatch(A, {A})               # elegir "No"
    assert app.dialog is None
    assert zzz.exists(), "No: el wav sigue en el disco"
    print("  Compact Instruments + No (no borra) OK")

    # --- "Sí" borra el wav del disco -------------------------------------
    p.instrument_bank[x] = {"type": "Sample",
                            "params": {"sample": "zzz_unused.wav"}}
    app._dispatch(A, {A})               # re-compactar
    app._release(A)
    assert app.dialog is not None
    app._dispatch(LEFT, {LEFT})         # No -> Sí
    app._dispatch(A, {A})
    assert app.dialog is None
    assert not zzz.exists(), "Sí: el wav se borra del disco"
    print("  Compact Instruments + Sí (borra) OK")

    # --- B cierra el diálogo sin borrar ----------------------------------
    zzz.write_bytes(b"RIFF dummy")
    p.instrument_bank[x] = {"type": "Sample",
                            "params": {"sample": "zzz_unused.wav"}}
    app._dispatch(A, {A})
    app._release(A)
    assert app.dialog is not None
    app._dispatch(B, {B})               # cancelar
    assert app.dialog is None
    assert zzz.exists(), "B: el wav sigue en el disco"
    print("  B cierra el diálogo sin borrar OK")

    # --- roundtrip: guardar + recargar no resucita los popeados ----------
    r = next(i for i in p.instrument_bank if i != ROBOT_INSTR)
    del p.instrument_bank[r]
    app._save()
    assert not app.dirty
    reloaded = load_project(song)
    assert r not in reloaded.instrument_bank, "el writer quita el nodo"
    assert x not in reloaded.instrument_bank
    if robot_ya:
        assert ROBOT_INSTR in reloaded.instrument_bank
    print("  roundtrip: los instrumentos popeados no vuelven OK")


def main():
    from robotracker2 import Robotracker2App  # noqa: E402

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _unitarios(tmp / "sintetico")

        songs_dir = tmp / "songs"
        songs_dir.mkdir()
        song = songs_dir / "lgpt_compact"
        shutil.copytree(_cancion_origen(), song)
        # samples/ controlado: solo el wav huérfano del test (nada de
        # huérfanos previos de la canción real que ensucien el Sí/No)
        samples = song / "samples"
        if samples.is_dir():
            for f in samples.glob("*.wav"):
                f.unlink()
        samples.mkdir(exist_ok=True)

        app = Robotracker2App(songs_dir=songs_dir, samples_dir=tmp)

        def _go(_dt):
            try:
                _e2e(app, song)
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
