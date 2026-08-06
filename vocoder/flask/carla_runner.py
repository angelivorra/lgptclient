#!/usr/bin/env python3
"""Launcher de Carla headless con OSC TCP/UDP forzado en el puerto 22752.

Carla 2.5.10 lanzado simplemente con `carla -n <project>` no abre el listener
OSC en este sistema (Qt offscreen + headless), aunque QSettings lo declare
habilitado. La opción oficial `--osc-gui=PORT` haría fork() y rompería el
seguimiento por subprocess.Popen del servicio Flask.

Este wrapper reproduce manualmente la inicialización que hace
`/usr/share/carla/carla`, pero sin pasar por `handleInitialCommandLineArguments`
(donde está el fork), y forzando el puerto OSC via `gCarla.nogui = OSC_PORT`
antes de llamar a `runHostWithoutUI`, que ya está preparado para usar ese
entero como `oscPort` explícito (`carla_host.py:3547-3548`).

También lanza aquí (no en `tcp_client.py`, que es otro proceso) el cliente
TCP que recibe los acordes de la pista de voz (evento `ACRD` de
`sinte/event_server.py`) y los toca en el sintetizador "Noize Mak3r"
(pluginId=7 del rack, el carrier del plugin Vocoder).

Probado primero con `host.send_midi_note()` (llamada directa de la
librería de Carla): no sonaba nada, mientras que un controlador MIDI
físico conectado a `Carla:events-in` sí funcionaba perfectamente. En vez
de seguir con esa vía, se emula la entrada física de verdad: un cliente
JACK propio con un puerto de salida MIDI, conectado por `jack_connect` al
mismo `Carla:events-in` al que llega el controlador (visto con
`jack_lsp -c` en el device: motor de Carla = JACK, único puerto de
entrada MIDI de todo el rack). Así Carla recibe las notas exactamente
por el mismo camino que ya se sabe que funciona.
"""

from __future__ import annotations

import os
import queue
import socket
import sys
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/usr/share/carla")

import jack  # noqa: E402

from carla_shared import gCarla  # noqa: E402
from carla_host import (  # noqa: E402
    CarlaApplication,
    initHost,
    loadHostSettings,
    runHostWithoutUI,
    setUpSignals,
)

OSC_PORT = 22752

# app.py lanza este script con stdout/stderr a DEVNULL, así que print() no
# sirve para depurar: log a fichero propio, solo mientras se investiga por
# qué no suena el acorde inyectado por TCP aunque el teclado MIDI sí suena.
_LOG_PATH = "/tmp/acrd_debug.log"


def _log(msg: str) -> None:
    try:
        with open(_LOG_PATH, "a") as f:
            f.write(f"{time.time():.3f} {msg}\n")
    except OSError:
        pass

# Cliente TCP de acordes -> Carla. Mismo host:puerto y backoff que
# flask/tcp_client.py (proceso hermano, pero este necesita estar en el
# proceso de Carla — ver docstring del módulo).
SERVER_HOST = "192.168.0.2"
SERVER_PORT = 8888
_BACKOFF_INITIAL = 2
_BACKOFF_MAX = 30

# Único puerto MIDI de entrada de todo el rack de Carla (ver docstring):
# ahí es donde llega también el controlador físico.
JACK_CLIENT_NAME = "sinte-acrd"
CARLA_MIDI_IN = "Carla:events-in"
CHORD_MIDI_CHANNEL = 0

# Mismo valor por defecto que usa event_server.py (`ev.get("delay", 1000)`
# en lgpt_player.py): el evento ya lleva `ts = audible - CLIENT_DELAY_MS`,
# así que hay que esperar ese margen antes de disparar la nota, comparando
# el timestamp absoluto del servidor contra el reloj de pared local (igual
# que `bin/cliente_final/event_orchestrator.py`). Para que esto sea válido
# el reloj del vocoder tiene que estar ajustado al del sinte: lo hace
# `tcp_client.py` (`_sync_clock_to_server`, vía SYNC), en otro proceso.
CLIENT_DELAY_MS = 1000


class _ChordClient:
    """Recibe `ACRD,<ts_ms>,<canal>,<velocidad>,<nota1>,...` y dispara cada
    nota en Carla, por un puerto MIDI JACK propio conectado a
    `Carla:events-in` (ver docstring del módulo).

    El acorde nuevo apaga primero las notas del acorde anterior de este
    mismo canal (monofónico, igual que hace el propio motor de sinte):
    con MIDI de verdad, a diferencia del protocolo NOTA original, sí hace
    falta un "note off" explícito o la nota queda sonando para siempre."""

    def __init__(self) -> None:
        _log("=== _ChordClient arrancando ===")
        self._jack = jack.Client(JACK_CLIENT_NAME)
        self._midi_out = self._jack.midi_outports.register("acrd")
        self._pending: queue.SimpleQueue = queue.SimpleQueue()
        self._sounding: list[int] = []
        self._jack.set_process_callback(self._process)
        self._jack.activate()
        self._last_connect_attempt = 0.0

    def _process(self, frames: int) -> None:
        # Callback de tiempo real de JACK: nada de I/O ni locks que
        # puedan bloquear, solo vaciar la cola a la salida MIDI.
        self._midi_out.clear_buffer()
        while True:
            try:
                event = self._pending.get_nowait()
            except queue.Empty:
                break
            try:
                self._midi_out.write_midi_event(0, event)
            except jack.JackError as exc:
                _log(f"write_midi_event fallo: {exc} event={event!r}")

    def _ensure_connected(self) -> None:
        """Reintenta la conexión a Carla:events-in cada pocos segundos (no
        en cada nota): Carla puede no haber arrancado aún, o haberse
        reiniciado y vuelto a crear el puerto con el mismo nombre."""
        now = time.monotonic()
        if now - self._last_connect_attempt < 3.0:
            return
        self._last_connect_attempt = now
        try:
            if not self._midi_out.is_connected_to(CARLA_MIDI_IN):
                self._jack.connect(self._midi_out, CARLA_MIDI_IN)
                _log("conectado a Carla:events-in")
        except jack.JackError as exc:
            _log(f"conexion fallida: {exc}")

    def run_reconnect_loop(self) -> None:
        """Bucle en su propio hilo: sin esto, `_ensure_connected` solo se
        llama al disparar un acorde, así que si no suena nada desde el
        arranque el puerto JACK se queda creado pero sin conectar nunca."""
        while True:
            self._ensure_connected()
            time.sleep(3.0)

    def _fire_chord(self, notes: list[int], velocity: int) -> None:
        self._ensure_connected()
        _log(f"_fire_chord notes={notes} vel={velocity} "
             f"conectado={self._midi_out.is_connected_to(CARLA_MIDI_IN)} "
             f"sounding_prev={self._sounding}")
        for note in self._sounding:
            self._pending.put(bytes((0x80 | CHORD_MIDI_CHANNEL, note, 0)))
        self._sounding = list(notes)
        for note in notes:
            self._pending.put(
                bytes((0x90 | CHORD_MIDI_CHANNEL, note, velocity)))

    def _handle_line(self, line: str) -> None:
        if not line:
            return
        parts = line.split(",")
        if parts[0] != "ACRD":
            return
        _log(f"linea recibida: {line!r}")
        if len(parts) < 5:
            return
        try:
            ts_ms = int(parts[1])
            velocity = int(parts[3])
            notes = [int(p) for p in parts[4:]]
        except ValueError:
            return
        execution_ms = ts_ms + CLIENT_DELAY_MS
        delay_s = (execution_ms - int(time.time() * 1000)) / 1000.0
        _log(f"programado en {delay_s:.3f}s notes={notes} vel={velocity}")
        timer = threading.Timer(
            max(0.0, delay_s), self._fire_chord, args=(notes, velocity))
        timer.daemon = True
        timer.start()

    def _connect_and_read(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((SERVER_HOST, SERVER_PORT))
            sock.settimeout(300)   # 5 min: detecta conexiones muertas
            print(f"[acrd] conectado a {SERVER_HOST}:{SERVER_PORT}")
            buf = ""
            while True:
                chunk = sock.recv(1024).decode("utf-8", errors="replace")
                if not chunk:
                    break
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    self._handle_line(line.strip())

    def run(self) -> None:
        backoff = _BACKOFF_INITIAL
        while True:
            t_start = time.monotonic()
            try:
                self._connect_and_read()
            except Exception as exc:
                print(f"[acrd] desconectado: {exc}")
            if time.monotonic() - t_start > 10:
                backoff = _BACKOFF_INITIAL
            time.sleep(backoff)
            backoff = min(backoff * 2, _BACKOFF_MAX)


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Uso: {sys.argv[0]} <proyecto.carxp>", file=sys.stderr)
        sys.exit(2)

    project = sys.argv[1]
    if not os.path.isfile(project):
        print(f"Proyecto no encontrado: {project}", file=sys.stderr)
        sys.exit(1)

    gCarla.initialProjectFile = project
    gCarla.cnprefix = ""

    CarlaApplication("Carla2", "/usr")
    setUpSignals()
    host = initHost("carla", "/usr", False, False, True)

    # Cargar el resto de settings sin disparar el auto-launch del engine
    # que loadHostSettings hace cuando ve gCarla.nogui truthy.
    gCarla.nogui = False
    loadHostSettings(host)

    # Cliente de acordes: hilo daemon, antes de bloquear en runHostWithoutUI.
    # El cliente JACK propio no depende de `host` (ver docstring de la
    # clase): solo necesita que el servidor JACK esté arriba, que ya lo
    # está siempre como servidor de audio del sistema.
    chord_client = _ChordClient()
    threading.Thread(target=chord_client.run, daemon=True,
                      name="acrd-chord-client").start()
    threading.Thread(target=chord_client.run_reconnect_loop, daemon=True,
                      name="acrd-jack-reconnect").start()

    # Forzar OSC: con nogui = int, runHostWithoutUI usa ese valor como oscPort
    # y se lo pasa a setEngineSettings, que activa ENGINE_OPTION_OSC_ENABLED y
    # fija los puertos TCP/UDP antes de engine_init.
    gCarla.nogui = OSC_PORT
    runHostWithoutUI(host)  # bloquea hasta el cierre del engine


if __name__ == "__main__":
    main()
