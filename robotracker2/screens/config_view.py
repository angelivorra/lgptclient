"""Pantalla CONFIG: selección de interfaces MIDI de entrada.

Dos campos editables (izq/dcha ciclan entre los puertos MIDI de entrada
disponibles, A+izq/dcha salta al primero/último):
  - MIDI Notas   -> interfaz de entrada para notas
  - MIDI Control -> interfaz de entrada para control

No pueden ser la misma interfaz. La selección se persiste en
`robotracker2/config.json` (módulo `config`). Si una interfaz guardada ya no
existe al arrancar, se conserva en el fichero pero se muestra "(no
disponible)" y se avisa con un toast.
"""

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from theme import COLOR_ACCENT, COLOR_BG, COLOR_ERROR, COLOR_ITEM, \
    COLOR_MISSING, COLOR_VALUE

FONT = dp(24)
ITEM_H = dp(46)
GAP = dp(22)
PAD_TOP = dp(48)

# (clave, etiqueta)
FIELDS = [
    ("midi_notes", "MIDI Notas"),
    ("midi_control", "MIDI Control"),
]


class ConfigMenu(Widget):
    def __init__(self, cfg=None, on_change=None, on_toast=None, **kw):
        super().__init__(**kw)
        self.cfg = cfg or {}
        self.on_change = on_change
        self.on_toast = on_toast
        self.index = 0
        self._tex = {}
        self._ports = []          # puertos MIDI de entrada disponibles
        self._missing = set()     # claves cuya interfaz guardada no existe
        self.bind(pos=self._redraw, size=self._redraw)

    # -- estado ---------------------------------------------------------
    def set_config(self, cfg):
        self.cfg = cfg
        self._refresh_ports()
        self._redraw()

    def _refresh_ports(self):
        """Enumera los puertos MIDI de entrada y detecta cuáles de los
        guardados ya no existen."""
        try:
            import mido
            self._ports = mido.get_input_names()
        except Exception:                       # noqa: BLE001
            self._ports = []
        self._missing = set()
        for key, _label in FIELDS:
            saved = self.cfg.get(key)
            if saved and saved not in self._ports:
                self._missing.add(key)

    def _display(self, key, label):
        saved = self.cfg.get(key)
        if not saved:
            return f"{label}: (ninguna)"
        if key in self._missing:
            return f"{label}: {saved}  (no disponible)"
        return f"{label}: {saved}"

    # -- navegación / edición ------------------------------------------
    def move(self, delta):
        self.index = (self.index + delta) % len(FIELDS)
        self._redraw()

    def adjust(self, delta, coarse=False):
        """Cicla la interfaz del campo actual entre los puertos disponibles.
        coarse (A+dir) salta al primero/último."""
        key, _label = FIELDS[self.index]
        if not self._ports:
            if self.on_toast:
                self.on_toast("No hay interfaces MIDI de entrada")
            return
        other_key = "midi_control" if key == "midi_notes" else "midi_notes"
        other = self.cfg.get(other_key)
        if coarse:
            # salta al primero/último puerto que no sea el del otro campo
            candidates = self._ports if delta < 0 else self._ports[::-1]
            chosen = next((p for p in candidates if p != other), None)
        else:
            cur = self.cfg.get(key)
            idx = self._ports.index(cur) if cur in self._ports else -1
            for _ in range(len(self._ports)):
                idx = (idx + delta) % len(self._ports)
                chosen = self._ports[idx]
                if chosen != other:
                    break
            else:
                chosen = None
        if chosen is None:
            if self.on_toast:
                self.on_toast("No puede ser la misma interfaz")
            return
        self.cfg[key] = chosen
        self._missing.discard(key)
        if self.on_change:
            self.on_change()
        self._redraw()


    def clear(self):
        """Pone el campo actual a 'ninguna'."""
        key, _label = FIELDS[self.index]
        self.cfg[key] = None
        self._missing.discard(key)
        if self.on_change:
            self.on_change()
        self._redraw()

    # -- dibujo ---------------------------------------------------------
    def _texture(self, text):
        tex = self._tex.get(text)
        if tex is None:
            lbl = CoreLabel(text=text, font_size=FONT, bold=True)
            lbl.refresh()
            tex = lbl.texture
            self._tex[text] = tex
        return tex

    def _redraw(self, *_):
        self.canvas.clear()
        maxw = dp(1)
        for key, label in FIELDS:
            maxw = max(maxw, self._texture(self._display(key, label)).size[0])
        x0 = self.center_x - maxw / 2
        with self.canvas:
            Color(*COLOR_BG)
            Rectangle(pos=self.pos, size=self.size)
            y = self.y + self.height - PAD_TOP
            for i, (key, label) in enumerate(FIELDS):
                tex = self._texture(self._display(key, label))
                tw, th = tex.size
                selected = (i == self.index)
                if selected:
                    Color(*COLOR_ACCENT)
                    RoundedRectangle(pos=(x0 - dp(12), y - dp(6)),
                                     size=(tw + dp(24), th + dp(12)),
                                     radius=[dp(8)])
                    color = COLOR_BG
                elif key in self._missing:
                    color = COLOR_MISSING
                else:
                    color = COLOR_VALUE
                Color(*color)
                Rectangle(texture=tex, size=(tw, th), pos=(x0, y))
                y -= ITEM_H
