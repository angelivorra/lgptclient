"""Test de los gatillos L2/R2 por ejes del joystick nativo (Odin 2).

En la Odin los gatillos son ejes analógicos (no botones): llegan por
on_joy_axis. Antes solo los traducía gptokeyb a Ctrl por teclado — si SDL no
reconocía el mando como gamecontroller no llegaba nada y L2/R2 no funcionaban.
Ahora el perfil nativo los lee directamente de los ejes (controls.py:
GAMEPAD_TRIGGER_AXES) con un umbral de pulsación.

En ROCKNIX, InputPlumber oculta el mando a SDL, así que el joystick
nativo no ve nada: la app usa el GamepadReader evdev
(ROBOTRACKER2_EVDEV_GAMEPAD) sobre el DualSense virtual de InputPlumber, y
toda la entrada (cruceta, stick, botones, gatillos) entra por
_on_evdev_button.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from controls import (A, B, BACK, DOWN, L2, LEFT, R2, RIGHT, START, UP,  # noqa: E402
                      TRIGGER_AXIS_THRESHOLD, trigger_axis_buttons)
from songs import DEFAULT_SONGS  # noqa: E402


def test_axis_mapping():
    """trigger_axis_buttons: solo los ejes de gatillo por encima del umbral."""
    assert trigger_axis_buttons(2, TRIGGER_AXIS_THRESHOLD) == frozenset()
    assert trigger_axis_buttons(2, TRIGGER_AXIS_THRESHOLD + 1) == {L2}
    assert trigger_axis_buttons(2, 32767) == {L2}
    assert trigger_axis_buttons(5, 32767) == {R2}
    assert trigger_axis_buttons(5, 0) == frozenset()
    # los ejes de los sticks (0/1/3/4) no mapean nunca
    for axis in (0, 1, 3, 4):
        assert trigger_axis_buttons(axis, 32767) == frozenset()
    print("  mapeo de ejes de gatillo OK")


def test_reader_events():
    """GamepadReader: cruceta/stick/botones/gatillos -> transiciones."""
    from evdev_triggers import GamepadReader

    events = []
    r = GamepadReader(on_event=lambda b, p: events.append((b, p)))

    # cruceta (hat): -1/0/1
    r._ingest(3, 17, -1); r._ingest(3, 17, 0)   # arriba
    r._ingest(3, 17, 1);  r._ingest(3, 17, 0)   # abajo
    r._ingest(3, 16, -1); r._ingest(3, 16, 0)   # izquierda
    r._ingest(3, 16, 1);  r._ingest(3, 16, 0)   # derecha
    # stick izquierdo (0..255, centro 128): lo mismo que la cruceta
    r._ingest(3, 0, 20);  r._ingest(3, 0, 128)  # izquierda
    r._ingest(3, 0, 250); r._ingest(3, 0, 128)  # derecha
    r._ingest(3, 1, 20);  r._ingest(3, 1, 128)  # arriba
    r._ingest(3, 1, 250); r._ingest(3, 1, 128)  # abajo
    # botones físicos de la Odin
    r._ingest(1, 308, 1); r._ingest(1, 308, 0)  # X -> A
    r._ingest(1, 305, 1); r._ingest(1, 305, 0)  # B -> B
    r._ingest(1, 315, 1); r._ingest(1, 315, 0)  # Start
    r._ingest(1, 314, 1); r._ingest(1, 314, 0)  # Back
    # bumpers y gatillos (L1/R1 valen como L2/R2, más los ejes analógicos)
    r._ingest(1, 310, 1); r._ingest(1, 310, 0)  # L1 -> L2
    r._ingest(1, 311, 1); r._ingest(1, 311, 0)  # R1 -> R2
    r._ingest(3, 2, 250); r._ingest(3, 2, 0)    # L2
    r._ingest(3, 5, 250); r._ingest(3, 5, 0)    # R2
    # histéresis del gatillo: a medio camino (80) no suelta
    r._ingest(3, 2, 250)
    r._ingest(3, 2, 80)
    r._ingest(3, 2, 30)
    assert events == [
        (UP, True), (UP, False), (DOWN, True), (DOWN, False),
        (LEFT, True), (LEFT, False), (RIGHT, True), (RIGHT, False),
        (LEFT, True), (LEFT, False), (RIGHT, True), (RIGHT, False),
        (UP, True), (UP, False), (DOWN, True), (DOWN, False),
        (A, True), (A, False), (B, True), (B, False),
        (START, True), (START, False), (BACK, True), (BACK, False),
        (L2, True), (L2, False), (R2, True), (R2, False),
        (L2, True), (L2, False), (R2, True), (R2, False),
        (L2, True), (L2, False)]
    print("  máquina de estados del GamepadReader OK")


def _run(app):
    from robotracker2 import Robotracker2App  # noqa: E402

    assert isinstance(app, Robotracker2App)
    songs = app.load_screen.songs
    assert songs, "debe haber canciones"
    app._request_load(songs[0])
    assert app.editor_screen.current == "song"

    # --- gatillo L2 (eje 2): press al superar el umbral, release al bajar --
    assert L2 not in app.held
    app._on_joy_axis(None, 0, 2, 32767)
    assert L2 in app.held, "eje 2 a fondo debe pulsar L2"

    # L2+dpad navega de SONG a CONFIG (como con el teclado: Ctrl+abajo)
    app._dispatch(DOWN, {DOWN, L2})
    assert app.editor_screen.current == "config", \
        f"L2+abajo debe navegar a config, no {app.editor_screen.current}"

    app._on_joy_axis(None, 0, 2, 0)
    assert L2 not in app.held, "eje 2 a 0 debe soltar L2"

    # --- gatillo R2 (eje 5) -------------------------------------------------
    app._on_joy_axis(None, 0, 5, 32767)
    assert R2 in app.held, "eje 5 a fondo debe pulsar R2"
    app._on_joy_axis(None, 0, 5, 0)
    assert R2 not in app.held, "eje 5 a 0 debe soltar R2"

    # --- los ejes de los sticks se ignoran (no pulsan nada) -----------------
    app._on_joy_axis(None, 0, 0, 32767)
    app._on_joy_axis(None, 0, 1, -32768)
    assert not app.held, f"los sticks no deben pulsar nada: {app.held}"
    print("  gatillos por ejes en la app OK")

    # --- entrada por evdev (GamepadReader, modo Odin/ROCKNIX) ----------------
    app._on_evdev_button(L2, True)
    assert L2 in app.held, "press evdev de L2 debe pulsarlo"
    app._on_evdev_button(L2, False)
    assert L2 not in app.held, "release evdev de L2 debe soltarlo"
    app._on_evdev_button(R2, True)
    assert R2 in app.held, "press evdev de R2 debe pulsarlo"
    app._on_evdev_button(R2, False)
    assert R2 not in app.held, "release evdev de R2 debe soltarlo"
    print("  entrada evdev en la app OK")


def main():
    from robotracker2 import Robotracker2App  # noqa: E402

    test_axis_mapping()
    test_reader_events()

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
