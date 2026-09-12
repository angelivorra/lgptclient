"""Pantalla INSTRUMENT: parámetros del instrumento, layout por secciones.

Estilo LGPT: el dpad solo mueve el foco (arr/abj = fila, izq/dcha = pareja);
los valores se editan manteniendo A — A+arr/abj = paso grande, A+izq/dcha =
paso fino. A la derecha, la **onda del sample** con marcas de loop
(start/end). Los instrumentos MIDI no tienen onda.
"""

from pathlib import Path

import numpy as np
import soundfile as sf
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, LEFT, RIGHT, UP
from lgpt_model import ensure_instrument
from sinte_bridge import (FILTER_MODES, cut_label, field_help, mode_label,
                          note_byte_to_name, res_label, type_label)
from theme import (COLOR_ACCENT, COLOR_BG, COLOR_BORDER, COLOR_HDR, COLOR_HINT,
                   COLOR_HINT_BG, COLOR_LABEL, COLOR_OK, COLOR_VALUE,
                   core_label)

FONT = dp(22)
FONT_HDR = dp(15)
FONT_HINT = dp(14)
ITEM_H = dp(38)
HDR_H = dp(26)
HINT_H = dp(40)
PAD_TOP = dp(30)
WAVE_W = dp(300)
WAVE_H = dp(180)
WAVE_BINS = 220

# Valores de los campos enum (se conserva el actual si no está en la lista).
ENUMS = {
    "filter mode": list(FILTER_MODES),
    "loopmode": ["none", "loop"],
}

# Layout por secciones. Cada item: ("hdr", texto) o ("row", [slots]).
# slot = (clave, etiqueta, tipo, *args). tipos:
#   instr | sample | note | enum | int(min,max) | hex | midich
# hex (start/end del loop): el máximo es el final del sample, no 0xFFFFFF.
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
    ("row", [("filter cut", "Corte", "int", 0, 255),
             ("filter res", "Canto", "int", 0, 255)]),
    ("row", [("filter type", "Mezcla", "int", 0, 255)]),
    ("row", [("filter mode", "Tipo", "enum")]),
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
        self._wave_key = None
        self._wave = None          # (lo, hi, n_samp) o None
        self.bind(pos=self._redraw, size=self._redraw)

    def set_project(self, project):
        self.project = project
        self.instr_ids = sorted(project.instrument_bank)
        self.pos_in_ids = 0
        self._reset_cursor()
        self._wave_key = None
        self._wave = None
        self._redraw()

    @property
    def instr_id(self):
        return self.instr_ids[self.pos_in_ids] if self.instr_ids else 0

    def instr_label(self):
        return f"{self.instr_id:02X}" if self.instr_ids else "--"

    def select_instrument(self, iid):
        """Abre `iid`. Si no está en el banco, lo crea (Sample vacío o
        Midi en 80–8F) para poder cargarle un sample desde PHRASE."""
        if self.project is None:
            return
        try:
            iid = int(iid)
        except (TypeError, ValueError):
            return
        created = ensure_instrument(self.project, iid)
        self.instr_ids = sorted(self.project.instrument_bank)
        if iid not in self.instr_ids:
            return
        self.pos_in_ids = self.instr_ids.index(iid)
        self._reset_cursor()
        self._wave_key = None
        self._redraw()
        if created and self.on_change:
            self.on_change()

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
        if self.on_nav:
            self.on_nav()
        self._redraw()

    def edit(self, button):
        """A+dir: A+izq/dcha = paso fino, A+arr/abj = paso grande."""
        if button in (LEFT, RIGHT, UP, DOWN):
            self._adjust(1 if button in (RIGHT, UP) else -1,
                         coarse=button in (UP, DOWN))
            self._redraw()

    def cycle_instrument(self, d, coarse=False):
        """Cambia al instrumento vecino del banco (wrap).

        `d` es el signo (+1 / -1); con `coarse` el paso es 16, si no 1.
        Conserva el campo con el foco si existe en el layout nuevo
        (Sample vs Midi); si no, vuelve al selector de instrumento.
        """
        if not self.instr_ids:
            return
        keep = None
        try:
            keep = self.field_key()
        except (IndexError, TypeError):
            pass
        step = 16 if coarse else 1
        self.pos_in_ids = (self.pos_in_ids + d * step) % len(self.instr_ids)
        self._wave_key = None
        layout = self._layout()
        found = False
        if keep is not None:
            for i, it in enumerate(layout):
                if it[0] != "row":
                    continue
                for s, sl in enumerate(it[1]):
                    if sl[0] == keep:
                        self.row_idx, self.slot = i, s
                        found = True
                        break
                if found:
                    break
        if not found:
            self._reset_cursor()
        self._ensure_visible()
        if self.on_nav:
            self.on_nav()
        self._redraw()

    def _adjust(self, d, coarse):
        key, _label, typ, *args = self._layout()[self.row_idx][1][self.slot]
        if typ == "instr":
            self.cycle_instrument(d, coarse)
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
            hi = self._sample_n()
            if hi is None:
                hi = 0xFFFFFF
            params[key] = str(max(0, min(hi,
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
            params["loopmode"] = "none"
            params["start"] = "0"
            self._wave_key = None
            n = self._sample_n()
            params["end"] = str(n if n is not None else 0)
            if self.on_change:
                self.on_change()
            self._redraw()

    # -- scroll ---------------------------------------------------------
    def _filter_mode(self):
        return self._params().get("filter mode", "original")

    def _hint_text(self):
        if self._is_midi() or not self.instr_ids:
            return ""
        try:
            key = self.field_key()
        except (IndexError, TypeError):
            return ""
        return field_help(key, self._filter_mode())

    def _visible(self):
        # nº de items (filas + cabeceras) que caben desde top_idx
        layout = self._layout()
        y = self.height - PAD_TOP
        floor = self.y + (HINT_H if self._hint_text() else 0)
        n = 0
        for i in range(self.top_idx, len(layout)):
            h = ITEM_H if layout[i][0] == "row" else HDR_H
            if y - h < floor:
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
        if key == "filter cut":
            return cut_label(params.get(key, "255"),
                             params.get("filter mode", "original"))
        if key == "filter res":
            return res_label(params.get(key, "0"))
        if key == "filter type":
            return type_label(params.get(key, "0"))
        if key == "filter mode":
            return mode_label(params.get(key, "original"), long=True)
        return params.get(key, "--")

    def _texture(self, text, font_size=FONT):
        key = (text, font_size)
        tex = self._tex.get(key)
        if tex is None:
            tex = core_label(text, font_size).texture
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
        val_w = dp(260)
        gap = dp(24)
        pair_gap = dp(40)
        block_w = label_w + val_w + gap + (label_w + val_w + pair_gap)
        show_wave = not self._is_midi()
        if show_wave:
            x0 = self.x + dp(24)
        else:
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
            if show_wave:
                self._ensure_wave()
                self._draw_wave(self.x + self.width - WAVE_W - dp(20),
                                self.y + self.height - PAD_TOP - WAVE_H,
                                WAVE_W, WAVE_H)
            hint = self._hint_text()
            if hint:
                Color(*COLOR_HINT_BG)
                Rectangle(pos=(self.x, self.y), size=(self.width, HINT_H))
                Color(*COLOR_ACCENT)
                Line(points=[self.x, self.y + HINT_H,
                             self.x + self.width, self.y + HINT_H], width=1)
                tex = self._texture(hint, FONT_HINT)
                Color(*COLOR_HINT)
                Rectangle(texture=tex, size=tex.size,
                          pos=(self.x + dp(16),
                               self.y + (HINT_H - tex.size[1]) / 2))

    def _draw(self, x, y, text, color):
        tex = self._texture(text)
        Color(*color)
        Rectangle(texture=tex, size=tex.size,
                  pos=(x, y + (ITEM_H - tex.size[1]) / 2 - dp(3)))

    def _int_param(self, key, default=0):
        try:
            return int(self._params().get(key, default) or default)
        except (TypeError, ValueError):
            return default

    def _sample_n(self):
        """Frames del WAV del instrumento, o None si no hay sample legible.

        El máximo de start/end del loop es este valor (el final del sample),
        no 0xFFFFFF.
        """
        if self._is_midi() or not self.instr_ids or self.project is None:
            return None
        name = self._params().get("sample") or ""
        if not name:
            return None
        key = (str(self.project.dir), name)
        if key == self._wave_key and self._wave is not None:
            return int(self._wave[2])
        path = Path(self.project.dir) / "samples" / name
        if not path.is_file():
            return None
        try:
            return int(sf.info(str(path)).frames)
        except Exception:                          # noqa: BLE001
            return None

    def _ensure_wave(self):
        if self._is_midi() or not self.instr_ids:
            self._wave = None
            return
        name = self._params().get("sample") or ""
        key = (str(self.project.dir), name)
        if key == self._wave_key:
            return
        self._wave_key = key
        self._wave = None
        if not name:
            return
        path = Path(self.project.dir) / "samples" / name
        if not path.is_file():
            return
        try:
            data, _sr = sf.read(str(path), dtype="float32", always_2d=True)
        except Exception:                          # noqa: BLE001
            return
        mono = data.mean(axis=1)
        n = int(mono.shape[0])
        if n < 2:
            return
        bins = min(WAVE_BINS, n)
        bucket = max(1, n // bins)
        usable = (n // bucket) * bucket
        chunk = mono[:usable].reshape(-1, bucket)
        lo = chunk.min(axis=1)
        hi = chunk.max(axis=1)
        peak = float(max(np.max(np.abs(lo)), np.max(np.abs(hi)), 1e-6))
        self._wave = (lo / peak, hi / peak, n)

    def _draw_wave(self, x, y, w, h):
        Color(0.08, 0.09, 0.10, 1)
        RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(8)])
        Color(*COLOR_BORDER)
        Line(rectangle=(x, y, w, h), width=1)
        if self._wave is None:
            tex = self._texture("sin sample", FONT_HDR)
            Color(*COLOR_HDR)
            Rectangle(texture=tex, size=tex.size,
                      pos=(x + (w - tex.size[0]) / 2,
                           y + (h - tex.size[1]) / 2))
            return
        lo, hi, n_samp = self._wave
        pad = dp(10)
        inner_x, inner_y = x + pad, y + pad
        inner_w, inner_h = w - 2 * pad, h - 2 * pad
        start = self._int_param("start", 0)
        end = self._int_param("end", 0)
        end_f = n_samp if end <= 0 else min(end, n_samp)
        start_f = max(0, min(start, n_samp - 1))
        sx = inner_x + inner_w * (start_f / n_samp)
        ex = inner_x + inner_w * (end_f / n_samp)
        Color(0.32, 0.78, 0.42, 0.16)
        Rectangle(pos=(sx, inner_y), size=(max(dp(2), ex - sx), inner_h))
        mid = inner_y + inner_h / 2
        amp = inner_h * 0.46
        nbin = len(lo)
        dx = max(1.0, inner_w / nbin)
        Color(*COLOR_ACCENT)
        for i in range(nbin):
            y1 = mid + float(lo[i]) * amp
            y2 = mid + float(hi[i]) * amp
            if y2 < y1:
                y1, y2 = y2, y1
            Rectangle(pos=(inner_x + i * dx, y1),
                      size=(dx, max(1.0, y2 - y1)))
        focus = self.field_key() if self.instr_ids else ""
        Color(*(COLOR_OK if focus == "start" else COLOR_BORDER))
        Line(points=[sx, inner_y, sx, inner_y + inner_h], width=1.4)
        Color(*(COLOR_OK if focus == "end" else COLOR_BORDER))
        Line(points=[ex, inner_y, ex, inner_y + inner_h], width=1.4)
