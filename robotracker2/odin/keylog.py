#!/usr/bin/env python3
"""Keylogger de diagnóstico para robotracker2 (Odin).

Muestra en pantalla (scrolling) y registra en un fichero (KEYLOG_FILE o
/storage/robotracker2/keylog.txt) todos los eventos de TECLADO (Kivy), de
JOYSTICK nativo (Kivy) y — además — la LECTURA CRUDA de dos dispositivos
evdev:

  - el mando AYN (InputPlumber lo oculta a SDL: se lee del nodo privado
    /dev/inputplumber/sources/event3) — se muestran los ejes L2/R2 (ABS 2/5)
    y si el dispositivo está agarrado (grab) por InputPlumber.
  - el teclado virtual de InputPlumber (/dev/input/event6) y el de gptokeyb
    (/dev/input/event13) — cada tecla que emiten, con nombre Linux (p.ej.
    KEY_END=107, KEY_HOME=102, KEY_LEFTCTRL=29), para ver exactamente qué
    traduce InputPlumber al pulsar L2/R2.

Ojo: los ejes de los sticks escriben una línea por movimiento (solo se
registran; en pantalla se muestran las últimas 18 líneas).

Uso (en la Odin, lanzado por keylog_test.sh):
    python3 keylog.py [--fullscreen]
"""

import fcntl
import os
import select
import struct
import sys
import threading
import time
from collections import deque
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

from kivy.config import Config  # noqa: E402

Config.set("graphics", "width", "1280")
Config.set("graphics", "height", "720")

from kivy.app import App  # noqa: E402
from kivy.core.window import Window  # noqa: E402
from kivy.uix.label import Label  # noqa: E402

LOG_PATH = Path(os.environ.get("KEYLOG_FILE",
                               "/storage/robotracker2/keylog.txt"))
_start = time.monotonic()

EVIOCGRAB = 0x40044590  # _IOW('E', 0x90, int)

KEY_NAMES = {29: "KEY_LEFTCTRL", 97: "KEY_RIGHTCTRL", 42: "KEY_LEFTSHIFT",
             54: "KEY_RIGHTSHIFT", 56: "KEY_LEFTALT", 100: "KEY_RIGHTALT",
             103: "KEY_UP", 105: "KEY_LEFT", 106: "KEY_RIGHT",
             108: "KEY_DOWN", 57: "KEY_SPACE", 28: "KEY_ENTER", 1: "KEY_ESC",
             15: "KEY_TAB", 30: "KEY_A", 31: "KEY_S", 32: "KEY_D",
             17: "KEY_W", 45: "KEY_X", 44: "KEY_Z", 46: "KEY_C",
             47: "KEY_V", 59: "KEY_F1", 194: "KEY_F24", 102: "KEY_HOME",
             107: "KEY_END", 304: "BTN_SOUTH", 305: "BTN_EAST", 306: "BTN_C",
             307: "BTN_NORTH", 308: "BTN_WEST", 309: "BTN_Z", 310: "BTN_TL",
             311: "BTN_TR"}


def _log(msg):
    line = f"[{time.monotonic() - _start:8.3f}] {msg}"
    try:
        with LOG_PATH.open("a") as f:
            f.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


class KeylogApp(App):
    title = "KEYLOG"

    def build(self):
        if "--fullscreen" in sys.argv:
            Window.fullscreen = "auto"
        self.events = deque(maxlen=18)
        self.lab = Label(font_size=22, halign="left", valign="bottom",
                         text_size=(Window.width - 30, Window.height - 30))
        Window.bind(on_key_down=self.kd, on_key_up=self.ku,
                    on_joy_button_down=self.jd, on_joy_button_up=self.ju,
                    on_joy_hat=self.jh, on_joy_axis=self.ja)
        self._show("== keylog iniciado ==")
        self._show("pulsa L2 / R2 / dpad / A / B / Start...")
        threading.Thread(target=self._reader_pad, daemon=True).start()
        threading.Thread(target=self._reader_ds5, daemon=True).start()
        threading.Thread(target=self._reader_rawkeys,
                         args=("/dev/input/event6", "IP-KB"),
                         daemon=True).start()
        threading.Thread(target=self._reader_rawkeys,
                         args=("/dev/input/event13", "GPTK"),
                         daemon=True).start()
        return self.lab

    def _show(self, msg):
        _log(msg)
        self.events.append(msg)
        self.lab.text = "\n".join(self.events)

    # -- teclado (Kivy, viene del teclado virtual de InputPlumber) ------
    def kd(self, win, key, scancode, codepoint, mods):
        self._show(f"KEY_DOWN key={key} scancode={scancode} "
                   f"codepoint={codepoint!r} mods={mods}")

    def ku(self, win, key, *rest):
        self._show(f"KEY_UP   key={key} rest={rest}")

    # -- joystick nativo (si Kivy/SDL ve el mando) ----------------------
    def jd(self, win, stick, buttonid):
        self._show(f"JOY_DOWN stick={stick} buttonid={buttonid}")

    def ju(self, win, stick, buttonid):
        self._show(f"JOY_UP   stick={stick} buttonid={buttonid}")

    def jh(self, win, stick, hatid, value):
        self._show(f"JOY_HAT  stick={stick} hatid={hatid} value={value}")

    def ja(self, win, stick, axisid, value):
        self._show(f"JOY_AXIS stick={stick} axisid={axisid} value={value}")

    # -- mando AYN por evdev crudo (nodo privado de InputPlumber) -------
    def _reader_pad(self):
        from kivy.clock import Clock

        def show(msg):
            Clock.schedule_once(lambda _dt: self._show(msg), 0)

        candidates = ["/dev/inputplumber/sources/event3",
                      "/dev/inputplumber/by-hidden/event3",
                      "/dev/input/event3"]
        fd = None
        for p in candidates:
            try:
                fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK)
                break
            except OSError:
                continue
        if fd is None:
            show("PAD: mando AYN no encontrado")
            return
        # ¿está agarrado (grab) por InputPlumber?
        try:
            fcntl.ioctl(fd, EVIOCGRAB, 1)
            fcntl.ioctl(fd, EVIOCGRAB, 0)
            show(f"PAD: leyendo {p} sin grab (ejes L2=2 R2=5)")
        except OSError as exc:
            show(f"PAD: {p} GRABEADO por otro proceso "
                 f"({exc.errno}) — no llegan eventos")
        last = {}
        while True:
            r, _, _ = select.select([fd], [], [], 1.0)
            if not r:
                continue
            try:
                data = os.read(fd, 4096)
            except OSError:
                continue
            for i in range(0, len(data) // 24 * 24, 24):
                _sec, _usec, typ, code, val = struct.unpack(
                    "llHHi", data[i:i + 24])
                if typ == 3 and code in (2, 5) and last.get(code) != val:
                    last[code] = val
                    name = "L2" if code == 2 else "R2"
                    show(f"PAD {name} value={val}")

    # -- DualSense virtual de InputPlumber (event7): ejes L2/R2 crudos ----
    def _reader_ds5(self):
        from kivy.clock import Clock

        def show(msg):
            Clock.schedule_once(lambda _dt: self._show(msg), 0)

        try:
            fd = os.open("/dev/input/event7", os.O_RDONLY | os.O_NONBLOCK)
        except OSError as exc:
            show(f"DS5: no se puede abrir /dev/input/event7 ({exc})")
            return
        show("DS5: leyendo /dev/input/event7 (ejes L2=2 R2=5)")
        last = {}
        while True:
            r, _, _ = select.select([fd], [], [], 1.0)
            if not r:
                continue
            try:
                data = os.read(fd, 4096)
            except OSError:
                continue
            for i in range(0, len(data) // 24 * 24, 24):
                _sec, _usec, typ, code, val = struct.unpack(
                    "llHHi", data[i:i + 24])
                if typ == 3 and code in (2, 5) and last.get(code) != val:
                    last[code] = val
                    name = "L2" if code == 2 else "R2"
                    show(f"DS5 {name} value={val}")

    # -- teclados virtuales (InputPlumber / gptokeyb) en crudo -----------
    def _reader_rawkeys(self, path, label):
        from kivy.clock import Clock

        def show(msg):
            Clock.schedule_once(lambda _dt: self._show(msg), 0)

        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as exc:
            show(f"{label}: no se puede abrir {path} ({exc})")
            return
        show(f"{label}: leyendo {path}")
        while True:
            r, _, _ = select.select([fd], [], [], 1.0)
            if not r:
                continue
            try:
                data = os.read(fd, 4096)
            except OSError:
                continue
            for i in range(0, len(data) // 24 * 24, 24):
                _sec, _usec, typ, code, val = struct.unpack(
                    "llHHi", data[i:i + 24])
                if typ == 1:  # EV_KEY
                    name = KEY_NAMES.get(code, f"code{code}")
                    show(f"{label} {name} {val}")


if __name__ == "__main__":
    KeylogApp().run()
