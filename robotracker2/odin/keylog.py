#!/usr/bin/env python3
"""Keylogger de diagnóstico para robotracker2 (Odin).

Muestra en pantalla (scrolling) y registra en un fichero (KEYLOG_FILE o
/storage/robotracker2/keylog.txt) todos los eventos de TECLADO (los que
traduce gptokeyb desde el mando) y de JOYSTICK nativo (si Kivy/SDL llega a
ver el mando) con marca de tiempo. Sirve para ver exactamente qué llega al
pulsar L2/R2/dpad/A/B/Start en la Odin.

Uso (en la Odin, lanzado por keylog_test.sh):
    python3 keylog.py [--fullscreen]
"""

import os
import sys
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
                    on_joy_hat=self.jh)
        self._show("== keylog iniciado ==")
        self._show("pulsa L2 / R2 / dpad / A / B / Start...")
        return self.lab

    def _show(self, msg):
        _log(msg)
        self.events.append(msg)
        self.lab.text = "\n".join(self.events)

    # -- teclado (viene de gptokeyb) ------------------------------------
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


if __name__ == "__main__":
    KeylogApp().run()
