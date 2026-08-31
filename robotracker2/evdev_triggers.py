"""Lector evdev de la entrada del mando (Odin 2 con ROCKNIX).

En la Odin, InputPlumber (gestor de entrada del sistema) agarra el mando AYN
integrado y lo oculta a SDL: ni gptokeyb ni el joystick nativo de Kivy pueden
verlo. Lo que InputPlumber expone es un DualSense VIRTUAL (uhid, "Sony
Interactive Entertainment DualSense Wireless Controller") que recibe TODA la
entrada traducida del mando: cruceta (hat), sticks (ejes), botones (BTN_*) y
gatillos (ABS_Z/ABS_RZ). Con el perfil por defecto de InputPlumber su teclado
virtual no emite nada, así que este módulo lee el DualSense virtual por evdev
crudo y notifica las transiciones.

Uso:
    reader = GamepadReader(on_event=callback)  # callback(boton, pulsado)
    reader.start()
    reader.stop()

El callback se llama desde el hilo lector: la app debe pasar a su hilo
principal con Clock.schedule_once. En el escritorio (sin DualSense virtual)
no hay nada que leer: el lector no hace nada.

Mapeo (Odin 2 Portal -> botón lógico de controls.py):
    cruceta (hat) y stick izquierdo -> UP/DOWN/LEFT/RIGHT
    X físico (BTN_WEST) -> A; B físico (BTN_EAST) -> B
    L1/R1 (BTN_TL/BTN_TR) -> L2/R2 (como en el perfil anterior)
    Start (BTN_START) -> START; Back (BTN_SELECT) -> BACK
    gatillos L2/R2 (ABS_Z/ABS_RZ) -> L2/R2
"""

import os
import select
import struct
import threading

from controls import A, B, BACK, DOWN, L2, LEFT, R2, RIGHT, START, UP

# Nombre del dispositivo a leer (DualSense virtual de InputPlumber; un
# DualSense real conectado por BT también valdría).
DEVICE_NAME = "Sony Interactive Entertainment DualSense Wireless Controller"

# Botones del DualSense -> botón lógico. BTN_WEST es la X física de la Odin,
# BTN_EAST la B. Los bumpers L1/R1 hacen de L2/R2 (así venía del perfil
# anterior). BTN_SOUTH/NORTH (A/Y) no se usan de momento.
BUTTON_MAP = {308: A,       # BTN_WEST (X físico)
              305: B,       # BTN_EAST (B físico)
              315: START,   # BTN_START
              314: BACK,    # BTN_SELECT
              310: L2,      # BTN_TL (L1)
              311: R2}      # BTN_TR (R1)

# Gatillos analógicos: ejes ABS_Z/ABS_RZ, valores crudos 0..255.
TRIGGER_AXES = {2: L2, 5: R2}
PRESS_THRESHOLD = 100
RELEASE_THRESHOLD = 60

# Cruceta (hat) del DualSense: ABS_HAT0X/ABS_HAT0Y con -1/0/1.
HAT_AXES = {16: (LEFT, RIGHT), 17: (UP, DOWN)}

# Stick izquierdo: ABS_X/ABS_Y, 0..255 con centro en 128. Misma función que
# la cruceta (navegación), con zona muerta e histéresis.
STICK_AXES = {0: (LEFT, RIGHT), 1: (UP, DOWN)}
STICK_CENTER = 128
STICK_ON = 64      # distancia al centro para pulsar
STICK_OFF = 32     # distancia al centro para soltar


def find_trigger_devices():
    """Devuelve los paths de los event nodes de los DualSense del sistema."""
    paths = []
    current_name = None
    try:
        with open("/proc/bus/input/devices") as f:
            for line in f:
                if line.startswith("N:"):
                    current_name = line.split('Name="', 1)[1].rsplit('"', 1)[0]
                elif line.startswith("H:") and current_name == DEVICE_NAME:
                    for part in line.split()[2:]:
                        if part.startswith("event"):
                            paths.append(f"/dev/input/{part}")
                    current_name = None
    except OSError:
        pass
    return paths


class GamepadReader(threading.Thread):
    """Hilo que lee la entrada del DualSense y notifica transiciones."""

    def __init__(self, on_event):
        super().__init__(daemon=True, name="evdev-gamepad")
        self._on_event = on_event
        self._stop = threading.Event()
        # Estado por fuente de entrada, para emitir solo las transiciones.
        self._buttons = {code: False for code in BUTTON_MAP}
        self._hat = {code: 0 for code in HAT_AXES}
        self._stick = {code: STICK_CENTER for code in STICK_AXES}
        self._stick_dir = {code: 0 for code in STICK_AXES}
        self._trig_pressed = {code: False for code in TRIGGER_AXES}
        self._active = set()   # botones lógicos emitidos ahora

    def stop(self):
        self._stop.set()

    def run(self):
        paths = find_trigger_devices()
        if not paths:
            return
        fds = []
        for p in paths:
            try:
                fds.append(os.open(p, os.O_RDONLY | os.O_NONBLOCK))
            except OSError:
                continue
        if not fds:
            return
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select(fds, [], [], 1.0)
            except OSError:
                return
            for fd in ready:
                try:
                    data = os.read(fd, 4096)
                except OSError:
                    continue
                for i in range(0, len(data) // 24 * 24, 24):
                    _sec, _usec, typ, code, val = struct.unpack(
                        "llHHi", data[i:i + 24])
                    self._ingest(typ, code, val)
        for fd in fds:
            try:
                os.close(fd)
            except OSError:
                pass

    def _ingest(self, typ, code, val):
        # Actualiza la fuente del evento y reemite si algo cambió.
        # (No se llama _handle: en Python 3.13 Thread._handle ya existe.)
        if typ == 1 and code in BUTTON_MAP:
            self._buttons[code] = val > 0
        elif typ == 3 and code in HAT_AXES:
            self._hat[code] = val
        elif typ == 3 and code in STICK_AXES:
            self._stick[code] = val
        elif typ == 3 and code in TRIGGER_AXES:
            if not self._trig_pressed[code] and val >= PRESS_THRESHOLD:
                self._trig_pressed[code] = True
            elif self._trig_pressed[code] and val <= RELEASE_THRESHOLD:
                self._trig_pressed[code] = False
            else:
                return
        else:
            return
        self._emit()

    def _emit(self):
        # Recalcula el conjunto de botones lógicos pulsados desde todas las
        # fuentes y notifica solo lo añadido/quitado (press/release).
        new = set()
        for code, v in self._buttons.items():
            if v:
                new.add(BUTTON_MAP[code])
        for code, (neg, pos) in HAT_AXES.items():
            v = self._hat[code]
            if v < 0:
                new.add(neg)
            elif v > 0:
                new.add(pos)
        for code, (neg, pos) in STICK_AXES.items():
            d = self._stick[code] - STICK_CENTER
            dir_ = self._stick_dir[code]
            if dir_ <= 0 and d <= -STICK_ON:
                dir_ = -1
            elif dir_ >= 0 and d >= STICK_ON:
                dir_ = 1
            elif dir_ < 0 and d >= -STICK_OFF:
                dir_ = 0
            elif dir_ > 0 and d <= STICK_OFF:
                dir_ = 0
            self._stick_dir[code] = dir_
            if dir_ < 0:
                new.add(neg)
            elif dir_ > 0:
                new.add(pos)
        for code, button in TRIGGER_AXES.items():
            if self._trig_pressed[code]:
                new.add(button)
        for b in new - self._active:
            self._on_event(b, True)
        for b in self._active - new:
            self._on_event(b, False)
        self._active = new
