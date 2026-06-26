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
"""

from __future__ import annotations

import os
import sys

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

    # Forzar OSC: con nogui = int, runHostWithoutUI usa ese valor como oscPort
    # y se lo pasa a setEngineSettings, que activa ENGINE_OPTION_OSC_ENABLED y
    # fija los puertos TCP/UDP antes de engine_init.
    gCarla.nogui = OSC_PORT
    runHostWithoutUI(host)  # bloquea hasta el cierre del engine


if __name__ == "__main__":
    main()
