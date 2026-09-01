"""Pantalla INSTRUMENT: parámetros del instrumento, layout por secciones.

Estilo LGPT: el dpad solo mueve el foco (arr/abj = fila, izq/dcha = pareja);
los valores se editan manteniendo A — A+arr/abj = paso grande, A+izq/dcha =
paso fino. Los instrumentos MIDI (type="Midi") muestran sus campos propios
(channel, note length, volume, table). Se muestran solo los parámetros que el
engine implementa; el resto (print fx, effect amount, feedback mix, ...) se
conservan en el XML al guardar (writer actualiza VALUE en sitio). El
instrumento se elige en el primer campo (o viene del step de PHRASE); en
"Sample", A abre el navegador de samples.
"""

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, LEFT, RIGHT, UP
from sinte_bridge import note_byte_to_name
from theme import COLOR_ACCENT, COLOR_BG

FONT = dp(22)
FONT_HDR = dp(15)
ITEM_H = dp(38)
HDR_H = dp(26)
PAD_TOP = dp(30)

COLOR_LABEL = (0.87, 0.89, 0.92, 1)
COLOR_VALUE = (0.55, 0.82, 0.55, 1)
COLOR_HDR = (0.45, 0.46, 0.52, 1)

# Valores de los campos enum (se conserva el actual si no está en la lista).
ENUMS = {
    "filter mode": ["original", "bassy", "scream"],
    "loopmode": ["none", "loop"],
}

# Layout por secciones. Cada item: ("hdr", texto) o ("row", [slots]).
# slot = (clave, etiqueta, tipo, *args). tipos:
#   instr | sample | note | enum | int(min,max) | hex | midich
SAMPLE_LAYOUT = [
    ("row", [("__instr__", "Instrument", "instr")]),
    ("hdr", "SAMPLE"),
    ("row", [("sample", "Sample", "sample")]),
    ("hdr", "AMP"),
    ("row", [("volume", "Volume", "int", 0, 255)]),
    ("row", [("pan", "Pan", "int", 0, 255)]),
    ("hdr", "TUNE"),
    ("row", [("root note", "Root note", "note")]),
    ("row", [("fine tune", "Fine tune", "int", 0, 255)]),
    ("hdr", "CRUSH"),
    ("row", [("crush", "Crush", "int", 1, 16),
             ("crushdrive", "Drive", "int", 0, 255)]),
    ("row", [("downsample", "Downsample", "int", 0, 16)]),
    ("hdr", "FILTER"),
    ("row", [("filter cut", "Cut", "int", 0, 255),
             ("filter res", "Res", "int", 0, 255)]),
    ("row", [("filter type", "Type", "int", 0, 255)]),
    ("row", [("filter mode", "Mode", "enum")]),
    ("row", [("attenuate", "Attenuate", "int", 1, 255)]),
    ("hdr", "LOOP"),
    ("row", [("loopmode", "Loop mode", "enum")]),
    ("row", [("start", "Start", "hex")]),
    ("row", [("end", "End", "hex")]),
    ("hdr", "TABLE"),
    ("row", [("table", "Table", "int", -1, 0x7F)]),
]

MIDI_LAYOUT = [
    ("row", [("__instr__", "Instrument", "instr")]),
    ("hdr", "MIDI"),
    ("row", [("channel", "Channel", "midich")]),
    ("row", [("note length", "Note length", "int", 0, 255)]),
    ("row", [("volume", "Volume", "int", 0, 255)]),
    ("hdr", "TABLE"),
    ("row", [("table", "Table", "int", -1, 0x7F)]),
]


class InstrumentMenu(Widget):
    def __init__(self, on_change=None, on_nav=None, on_pick_sample=None, **kw):
        super().__init__(**kw)
        self.project = None
        self.instr_ids = []
        self.pos_in_ids = 0
        self.row_idx = 0                 # item del layout con el foco
        self.slot = 0                    # slot activo dentro de la fila (0/1)
        self.top_idx = 0                 # primer item visible (scroll)
        self.on_change = on_change
        self.on_nav = on_nav
        self.on_pick_sample = on_pick_sample
        self._tex = {}
        self.bind(pos=self._redraw, size=self._redraw)

    def set_project(self, project):
        self.project = project
        self.instr_ids = sorted(project.instrument_bank)
        self.pos_in_ids = 0
        self._reset_cursor()
        self._redraw()

    @property
    def instr_id(self):
        return self.instr_ids[self.pos_in_ids] if self.instr_ids else 0

    def instr_label(self):
        return f"{self.instr_id:02X}" if self.instr_ids else "--"

    def select_instrument(self, iid):
        if iid in self.instr_ids:
            self.pos_in_ids = self.instr_ids.index(iid)
            self._reset_cursor()
            self._redraw()

    def field_key(self):
        return self._layout()[self.row_idx][1][self.slot][0]

    def _params(self):
        if not self.instr_ids:
            return {}
        return self.project.instrument_bank[self.instr_id]["params"]

    def _is_midi(self):
        if not self.instr_ids:
            return False
        return (self.project.instrument_bank[self.instr_id].get("type")
                == "Midi")

    def _layout(self):
        return MIDI_LAYOUT if self._is_midi() else SAMPLE_LAYOUT

    def _reset_cursor(self):
        layout = self._layout()
        self.row_idx = next(i for i, it in enumerate(layout)
                            if it[0] == "row")
        self.slot = 0
        self.top_idx = 0

    # -- navegación / edición ------------------------------------------
    # El dpad solo mueve el foco; los valores se editan con A mantenido.
    def move(self, button):
        layout = self._layout()
        if button in (UP, DOWN):
            rows = [i for i, it in enumerate(layout) if it[0] == "row"]
            cur = rows.index(self.row_idx)
            nxt = rows[max(0, min(len(rows) - 1, cur + (1 if button == DOWN
                                                        else -1)))]
            self.slot = min(self.slot, len(layout[nxt][1]) - 1)
            self.row_idx = nxt
        elif button in (LEFT, RIGHT):
            if len(layout[self.row_idx][1]) == 2:
                self.slot = 1 - self.slot
        self._ensure_visible()
        self._redraw()

    def edit(self, button):
        """A+dir: A+izq/dcha = paso fino, A+arr/abj = paso grande."""
        if button in (LEFT, RIGHT, UP, DOWN):
            self._adjust(1 if button in (RIGHT, UP) else -1,
                         coarse=button in (UP, DOWN))
            self._redraw()

    def _adjust(self, d, coarse):
        key, _label, typ, *args = self._layout()[self.row_idx][1][self.slot]
        if typ == "instr":
            if self.instr_ids:
                step = 16 if coarse else 1
                self.pos_in_ids = (self.pos_in_ids + d * step) % len(
                    self.instr_ids)
                self._reset_cursor()
                if self.on_nav:
                    self.on_nav()
            return
        if typ == "sample":
            return                                   # el sample se elige con A
        params = self._params()
        if not params:
            return
        if typ == "enum":
            base = ENUMS.get(key, [])
            cur = params.get(key, base[0] if base else "")
            lst = base if cur in base else ([cur] + base)
            params[key] = lst[(lst.index(cur) + d) % len(lst)]
        elif typ == "note":
            cur = int(params.get(key, "60") or 0)
            params[key] = str(max(0, min(127, cur + d * (12 if coarse else 1))))
        elif typ == "hex":
            cur = int(params.get(key, "0") or 0)
            params[key] = str(max(0, min(0xFFFFFF,
                                         cur + d * (0x1000 if coarse else 1))))
        elif typ == "midich":
            cur = int(params.get(key, "0") or 0)
            params[key] = str(max(0, min(15, cur + d * (4 if coarse else 1))))
        else:                                        # int
            lo, hi = args[0], args[1]
            cur = int(params.get(key, str(lo)) or 0)
            params[key] = str(max(lo, min(hi, cur + d * (16 if coarse else 1))))
        if self.on_change:
            self.on_change()

    def activate(self):
        # A sobre el campo Sample abre el navegador de samples.
        if self.field_key() == "sample" and self.on_pick_sample:
            self.on_pick_sample()

    def set_sample(self, name):
        params = self._params()
        if params:
            params["sample"] = name
            if self.on_change:
                self.on_change()
            self._redraw()

    # -- scroll ---------------------------------------------------------
    def _visible(self):
        # nº de items (filas + cabeceras) que caben desde top_idx
        layout = self._layout()
        y = self.height - PAD_TOP
        n = 0
        for i in range(self.top_idx, len(layout)):
            h = ITEM_H if layout[i][0] == "row" else HDR_H
            if y - h < self.y:
                break
            y -= h
            n += 1
        return max(1, n)

    def _ensure_visible(self):
        if self.row_idx < self.top_idx:
            self.top_idx = self.row_idx
        else:
            for _ in range(len(self._layout())):
                if self.row_idx < self.top_idx + self._visible():
                    break
                self.top_idx += 1
        self.top_idx = max(0, min(self.top_idx, len(self._layout()) - 1))

    # -- dibujo ---------------------------------------------------------
    def _value_text(self, slot):
        key, _label, typ = slot[0], slot[1], slot[2]
        if typ == "instr":
            return self.instr_label()
        params = self._params()
        if typ == "sample":
            s = params.get("sample", "--")
            return s if len(s) <= 24 else s[:23] + "…"
        if typ == "note":
            try:
                return note_byte_to_name(int(params.get(key, "60")))
            except (ValueError, TypeError):
                return params.get(key, "--")
        if typ == "hex":
            try:
                return f"{int(params.get(key, '0') or 0):07X}"
            except ValueError:
                return "0000000"
        return params.get(key, "--")

    def _texture(self, text, font_size=FONT):
        key = (text, font_size)
        tex = self._tex.get(key)
        if tex is None:
            lbl = CoreLabel(text=text, font_size=font_size, bold=True)
            lbl.refresh()
            tex = lbl.texture
            self._tex[key] = tex
        return tex

    def _redraw(self, *_):
        self.canvas.clear()
        if self.project is None:
            return
        layout = self._layout()
        label_w = max(self._texture(sl[1]).size[0]
                      for _kind, payload in layout if _kind == "row"
                      for sl in payload)
        val_w = dp(220)
        gap = dp(24)
        pair_gap = dp(40)
        block_w = label_w + val_w + gap + (label_w + val_w + pair_gap)
        x0 = self.center_x - block_w / 2
        n = self._visible()
        with self.canvas:
            Color(*COLOR_BG)
            Rectangle(pos=self.pos, size=self.size)
            y = self.y + self.height - PAD_TOP
            for i in range(self.top_idx, min(self.top_idx + n, len(layout))):
                kind, payload = layout[i]
                if kind == "hdr":
                    tex = self._texture(payload, FONT_HDR)
                    Color(*COLOR_HDR)
                    Rectangle(texture=tex, size=tex.size,
                              pos=(x0, y + (HDR_H - tex.size[1]) / 2))
                    y -= HDR_H
                    continue
                n_slots = len(payload)
                for s, slot in enumerate(payload):
                    sx = x0 if s == 0 else x0 + label_w + val_w + pair_gap
                    active = (i == self.row_idx and s == self.slot)
                    if active:
                        Color(*COLOR_ACCENT)
                        RoundedRectangle(pos=(sx - dp(12), y - dp(4)),
                                         size=(label_w + val_w + dp(24),
                                               ITEM_H - dp(6)),
                                         radius=[dp(8)])
                    lab_c = COLOR_BG if active else COLOR_LABEL
                    val_c = COLOR_BG if active else COLOR_VALUE
                    self._draw(sx, y, slot[1], lab_c)
                    self._draw(sx + label_w + gap, y,
                               self._value_text(slot), val_c)
                y -= ITEM_H

    def _draw(self, x, y, text, color):
        tex = self._texture(text)
        Color(*color)
        Rectangle(texture=tex, size=tex.size,
                  pos=(x, y + (ITEM_H - tex.size[1]) / 2 - dp(3)))
