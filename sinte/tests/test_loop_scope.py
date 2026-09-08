"""Test del loop de chain/phrase del Engine (play desde CHAIN/PHRASE).

Verifica que:
  - En modo chain, solo suena el canal objetivo y la chain se repite en
    bucle (no se detiene al terminar).
  - El play desde CHAIN arranca en `from_step` (el cursor), no siempre en 00.
  - En modo phrase, solo suena el canal objetivo y la phrase se repite en
    bucle.
  - El resto de canales quedan en silencio.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lgpt_engine import Engine, CHANNEL_COUNT  # noqa: E402

SONGS = Path(__file__).resolve().parent.parent / "songs"
PROJECT = SONGS / "lgpt_AACC"


def _find_playable(engine, track):
    """Devuelve (chain, phrase) reproducibles del canal `track` que tengan
    al menos una nota (para que el loop suene de verdad)."""
    for pos in range(256):
        chain = engine.project.song[pos * CHANNEL_COUNT + track]
        if chain == 0xFF:
            continue
        for step in range(16):
            phrase = engine.project.chains[chain * 16 + step]
            if phrase == 0xFF:
                continue
            row = phrase * 16
            if any(engine.project.notes[row + s] != 0xFF
                   for s in range(16)):
                return chain, phrase
    return None, None



def _render_seconds(engine, seconds, block=512):
    total = int(seconds * engine.sr / block)
    peak = 0.0
    for _ in range(total):
        out = engine.render(block)
        if not engine.playing:
            break
        peak = max(peak, float(abs(out).max()))
    return peak


def test_chain_loop():
    engine = Engine(PROJECT)
    track = 0
    chain, _phrase = _find_playable(engine, track)
    assert chain is not None, "no hay chain reproducible en el canal 0"
    engine.loop_scope = ("chain", track, chain)
    engine.start()
    assert engine.playing
    # Solo el canal objetivo debe estar sonando
    active = [c.playing for c in engine.channels]
    assert active[track], "el canal objetivo no está sonando"
    assert sum(active) == 1, f"debería sonar solo 1 canal, sonando {sum(active)}"
    # Renderiza ~3s: la chain debe seguir en bucle (no pararse)
    peak = _render_seconds(engine, 3.0)
    assert engine.playing, "la chain en bucle se detuvo"
    assert peak > 0.0, "no hay audio en el loop de chain"
    print(f"  chain loop OK: chain={chain:02X} pico={peak:.3f} "
          f"chain_pos={engine.channels[track].chain_pos}")
    engine.close() if hasattr(engine, "close") else None




def test_phrase_loop():
    engine = Engine(PROJECT)
    track = 1
    _chain, phrase = _find_playable(engine, track)
    assert phrase is not None, "no hay phrase reproducible en el canal 1"
    engine.loop_scope = ("phrase", track, phrase)
    engine.start()
    assert engine.playing
    active = [c.playing for c in engine.channels]
    assert active[track], "el canal objetivo no está sonando"
    assert sum(active) == 1, f"debería sonar solo 1 canal, sonando {sum(active)}"
    peak = _render_seconds(engine, 3.0)
    assert engine.playing, "la phrase en bucle se detuvo"
    assert peak > 0.0, "no hay audio en el loop de phrase"
    print(f"  phrase loop OK: phrase={phrase:02X} pico={peak:.3f} "
          f"phrase_pos={engine.channels[track].phrase_pos}")


def test_chain_loop_restores_song():
    """Tras un loop de chain, play_from vuelve a la canción completa."""
    engine = Engine(PROJECT)
    track = 0
    chain, _ = _find_playable(engine, track)
    engine.loop_scope = ("chain", track, chain)
    engine.start()
    _render_seconds(engine, 0.5)
    # play_from resetea loop_scope y arranca la canción completa
    engine.loop_scope = None
    engine.start()
    active = sum(c.playing for c in engine.channels)
    assert active > 1, f"play_from debería arrancar varios canales, activos={active}"
    print(f"  restore song OK: {active} canales activos")


def test_chain_loop_from_step():
    """Play desde CHAIN arranca en from_step, no siempre en 00."""
    engine = Engine(PROJECT)
    track = 0
    chain, phrase = _find_playable(engine, track)
    assert chain is not None
    # Asegura phrase en el step 4 (puede coincidir con el 0: da igual,
    # lo que se comprueba es chain_pos al arrancar).
    engine.project.chains[chain * 16 + 4] = phrase
    engine.loop_scope = ("chain", track, chain)
    engine.start(from_step=4)
    assert engine.playing
    assert engine.channels[track].playing
    assert engine.channels[track].chain_pos == 4, \
        f"debería arrancar en step 4, chain_pos=" \
        f"{engine.channels[track].chain_pos}"
    assert engine.channels[track].phrase == phrase
    print(f"  chain loop from step 4 OK: chain={chain:02X}")
    engine.start(from_step=0)
    assert engine.channels[track].chain_pos == 0
    print("  chain loop from step 0 sigue en 00 OK")


def test_chain_loop_from_empty_scans_forward():
    """Si el cursor cae en un step vacío, arranca en el siguiente con phrase."""
    engine = Engine(PROJECT)
    track = 0
    chain, phrase = _find_playable(engine, track)
    assert chain is not None
    engine.project.chains[chain * 16 + 3] = 0xFF
    engine.project.chains[chain * 16 + 4] = phrase
    engine.loop_scope = ("chain", track, chain)
    engine.start(from_step=3)
    assert engine.channels[track].chain_pos == 4, \
        f"step vacío 3 debería saltar a 4, chain_pos=" \
        f"{engine.channels[track].chain_pos}"
    print("  chain loop from empty step scans forward OK")


if __name__ == "__main__":
    print("test_chain_loop:")
    test_chain_loop()
    print("test_phrase_loop:")
    test_phrase_loop()
    print("test_chain_loop_restores_song:")
    test_chain_loop_restores_song()
    print("test_chain_loop_from_step:")
    test_chain_loop_from_step()
    print("test_chain_loop_from_empty_scans_forward:")
    test_chain_loop_from_empty_scans_forward()
    print("TODOS LOS TESTS OK")
