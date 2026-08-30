"""Test de la funcionalidad Ctrl+A (R2+A) con selección: duplicar chain/phrase.

En SONG, con una celda seleccionada que referencia una chain, R2+A busca la
primera chain libre con índice MAYOR, copia el contenido de la chain a la
nueva, y apunta la celda a la copia. En CHAIN, lo mismo con phrases.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from controls import A, B, R2  # noqa: E402
from lgpt_model import (CHAIN_LEN, EMPTY, PHRASE_LEN, duplicate_chain,
                        duplicate_phrase)  # noqa: E402
from songs import DEFAULT_SONGS  # noqa: E402


def _run(app):
    from robotracker2 import Robotracker2App  # noqa: E402

    songs = app.load_screen.songs
    assert songs, "debe haber canciones"
    app._request_load(songs[0])
    assert app.editor_screen.current == "song"

    g = app.editor_screen.song_grid
    p = g.view.project

    # --- test unitario: duplicate_chain ---
    # ponemos una chain en la celda (0,0) y rellenamos su contenido
    g.view.set_value(0, 0, 0x05)
    for s in range(CHAIN_LEN):
        p.chains[0x05 * CHAIN_LEN + s] = 0x10 + s
        p.transposes[0x05 * CHAIN_LEN + s] = s
    # aseguramos que 0x06 está libre (no referenciada en la song)
    assert 0x06 not in {b for b in p.song if b != EMPTY}, "0x06 debe estar libre"
    dst = duplicate_chain(p, 0x05)
    assert dst == 0x06, f"debe duplicar a 0x06, obtuvo {dst}"
    for s in range(CHAIN_LEN):
        assert p.chains[0x06 * CHAIN_LEN + s] == 0x10 + s, "chain copiada"
        assert p.transposes[0x06 * CHAIN_LEN + s] == s, "transpose copiado"
    print("  duplicate_chain unitario OK")

    # --- test unitario: wrap-around de chain (bug de abduccion) ---
    # AACC usa la chain FE; antes, duplicar una chain sin hueco libre por
    # encima no encontraba nada y la celda se quedaba clavada (en abduccion
    # la fila 0 usa FC/FD/FE, así que duplicar no hacía nada). Ahora la
    # búsqueda da la vuelta y coge la primera libre desde 00.
    g.view.set_value(0, 1, 0xFE)                  # celda (0,1) -> chain FE
    for s in range(CHAIN_LEN):
        p.chains[0xFE * CHAIN_LEN + s] = 0x20 + s
        p.transposes[0xFE * CHAIN_LEN + s] = s
    assert 0x00 not in {b for b in p.song if b != EMPTY}, "0x00 debe estar libre"
    dst = duplicate_chain(p, 0xFE)
    assert dst == 0x00, f"FE debe envolver a 00, obtuvo {dst:02X}"
    for s in range(CHAIN_LEN):
        assert p.chains[0x00 * CHAIN_LEN + s] == 0x20 + s, "chain copiada (wrap)"
        assert p.transposes[0x00 * CHAIN_LEN + s] == s, "transpose copiado (wrap)"
    print("  duplicate_chain wrap-around OK")

    # --- test unitario: wrap-around de phrase ---
    for s in range(PHRASE_LEN):
        p.notes[0xFE * PHRASE_LEN + s] = 0x50 + s
        p.instruments[0xFE * PHRASE_LEN + s] = 0x02
    assert 0x00 not in {b for b in p.chains if b != EMPTY}, "phrase 00 libre"
    dst = duplicate_phrase(p, 0xFE)
    assert dst == 0x00, f"phrase FE debe envolver a 00, obtuvo {dst:02X}"
    for s in range(PHRASE_LEN):
        assert p.notes[0x00 * PHRASE_LEN + s] == 0x50 + s, "notas copiadas (wrap)"
        assert p.instruments[0x00 * PHRASE_LEN + s] == 0x02, "instr copiado (wrap)"
    print("  duplicate_phrase wrap-around OK")

    # --- test e2e: R2+A en SONG duplica la chain ---
    # celda (0,0) -> chain 0x05 (ya la pusimos antes); 0x06 libre
    g.cursor_row, g.cursor_track = 0, 0
    g.cycle_selection()                    # activar selección
    assert g.has_selection
    app._dispatch(A, {A, R2})              # Ctrl+A: duplicar
    app._release(A)
    assert g.view.chain_at(0, 0) == 0x06, \
        f"la celda debe apuntar a 0x06, obtuvo {g.view.chain_at(0, 0):02X}"
    assert not g.has_selection, "la selección debe cancelarse"
    print("  R2+A en SONG duplica chain OK")

    # --- test e2e: R2+A en CHAIN duplica la phrase ---
    # navegamos a CHAIN (L2+RIGHT desde SONG)
    from controls import L2, RIGHT
    app._dispatch(RIGHT, {RIGHT, L2})
    assert app.editor_screen.current == "chain", "debe estar en CHAIN"

    cg = app.editor_screen.chain_grid
    # buscamos una phrase libre para usarla como origen (y la siguiente libre)
    used_ph = {b for b in p.chains if b != EMPTY}
    src_ph = next(i for i in range(256) if i not in used_ph)
    dst_ph = next(i for i in range(src_ph + 1, 256) if i not in used_ph)
    # la chain de la celda (0,0) ahora es 0x06; ponemos phrase src_ph en step 0
    cg.cursor_step, cg.cursor_col = 0, 0
    cg._set(0, 0, src_ph)                  # step 0 -> phrase src_ph
    for s in range(PHRASE_LEN):
        p.notes[src_ph * PHRASE_LEN + s] = 0x30 + s
        p.instruments[src_ph * PHRASE_LEN + s] = 0x01
    cg.cycle_selection()                   # activar selección
    assert cg.has_selection
    app._dispatch(A, {A, R2})              # Ctrl+A: duplicar phrase
    app._release(A)
    assert cg._get(0, 0) == dst_ph, \
        f"el step debe apuntar a {dst_ph:02X}, obtuvo {cg._get(0, 0):02X}"
    assert not cg.has_selection, "la selección debe cancelarse"
    for s in range(PHRASE_LEN):
        assert p.notes[dst_ph * PHRASE_LEN + s] == 0x30 + s, "notas copiadas"
        assert p.instruments[dst_ph * PHRASE_LEN + s] == 0x01, "instr copiado"
    print("  R2+A en CHAIN duplica phrase OK")




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
