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
(pluginId=7 del rack, el carrier del plugin Vocoder): `host.send_midi_note`
es una llamada directa de la librería de Carla cargada en este proceso, no
algo alcanzable por red, así que tiene que vivir en el mismo proceso que
`host`.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, "/usr/share/carla")

from carla_shared import gCarla  # noqa: E402
from carla_host import (  # noqa: E402
    CarlaApplication,
    initHost,
    loadHostSettings,
    runHostWithoutUI,
    setUpSignals,
)

OSC_PORT = 22752

# Cliente TCP de acordes -> Carla. Mismo host:puerto y backoff que
# flask/tcp_client.py (proceso hermano, pero este necesita estar en el
# proceso de Carla — ver docstring del módulo).
SERVER_HOST = "192.168.0.2"
SERVER_PORT = 8888
_BACKOFF_INITIAL = 2
_BACKOFF_MAX = 30

# "Noize Mak3r" (TAL NoiseMaker) en prod/template01.carxp: pluginId=7, el
# último del rack, carrier del plugin Vocoder (pluginId=2).
CHORD_PLUGIN_ID = 7
CHORD_MIDI_CHANNEL = 0

# Mismo valor por defecto que usa event_server.py (`ev.get("delay", 1000)`
# en lgpt_player.py): el evento ya lleva `ts = audible - CLIENT_DELAY_MS`,
# así que hay que esperar ese margen antes de disparar la nota. Sin
# calibración de reloj por SYNC: se compara contra el reloj de pared
# directamente, igual que ya hace `bin/cliente_final/event_orchestrator.py`
# (`execution_time_ms = server_ts_ms + delay_ms`, `delta = execution_time_ms
# - now_ms`) — ambos equipos están en la misma red local.
CLIENT_DELAY_MS = 1000


class _ChordClient:
    """Recibe `ACRD,<ts_ms>,<canal>,<velocidad>,<nota1>,...` y dispara cada
    nota en Carla en el instante en que debe sonar. Sin nota "off" explícita
    (el protocolo no la lleva, ver `event_server.py`): cada acorde nuevo
    del mismo canal se entiende como que corta al anterior, monofónico,
    igual que hace el propio motor de sinte con este canal."""

    def __init__(self, host) -> None:
        self._host = host

    def _fire_chord(self, notes: list[int], velocity: int) -> None:
        try:
            for note in notes:
                self._host.send_midi_note(
                    CHORD_PLUGIN_ID, CHORD_MIDI_CHANNEL, note, velocity)
        except Exception as exc:
            # Carla puede estar reiniciándose; no tirar el hilo por esto.
            print(f"[acrd] send_midi_note falló: {exc}", flush=True)

    def _handle_line(self, line: str) -> None:
        if not line:
            return
        parts = line.split(",")
        if parts[0] != "ACRD" or len(parts) < 5:
            return
        try:
            ts_ms = int(parts[1])
            velocity = int(parts[3])
            notes = [int(p) for p in parts[4:]]
        except ValueError:
            return
        execution_ms = ts_ms + CLIENT_DELAY_MS
        delay_s = (execution_ms - int(time.time() * 1000)) / 1000.0
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
    chord_client = _ChordClient(host)
    threading.Thread(target=chord_client.run, daemon=True,
                      name="acrd-chord-client").start()

    # Forzar OSC: con nogui = int, runHostWithoutUI usa ese valor como oscPort
    # y se lo pasa a setEngineSettings, que activa ENGINE_OPTION_OSC_ENABLED y
    # fija los puertos TCP/UDP antes de engine_init.
    gCarla.nogui = OSC_PORT
    runHostWithoutUI(host)  # bloquea hasta el cierre del engine


if __name__ == "__main__":
    main()
