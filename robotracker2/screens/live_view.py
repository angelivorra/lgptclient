"""Pantalla LIVE: preview de lo que suena en el canal robot (solo lectura).

Muestra la imagen de SCREEN sostenida (último MDCC) y tres pads de batería
(BOMBO / CAJA1 / CAJA2) que destellan al golpear. No edita la canción: la
navegación es L+dpad; START/STOP siguen siendo globales.
"""

from kivy.core.image import Image as CoreImage
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from robots import (HIT_PADS, ayuda_preview_path, hit_label, hit_pad_notes,
                    screen_label)
from screens.hit_icons import draw_kick, draw_snare
from theme import (COLOR_BG, COLOR_BORDER, COLOR_EMPTY, COLOR_HEADER_TXT,
                   COLOR_HIT, COLOR_MUTE_OVERLAY, COLOR_SCREEN, core_label)

PAD_H = dp(120)
GAP = dp(16)
FONT = dp(18)
FONT_SMALL = dp(14)
_PAD_DRAW = {62: lambda cx, cy, s, c: draw_kick(cx, cy, s, c),
             63: lambda cx, cy, s, c: draw_snare(cx, cy, s, c, hoop=False),
             65: lambda cx, cy, s, c: draw_snare(cx, cy, s, c, hoop=True)}
_PAD_NAME = {62: "BOMBO", 63: "CAJA1", 65: "CAJA2"}


class LiveGrid(Widget):
    def __init__(self, ayuda_dir=None, **kw):
        super().__init__(**kw)
        self.ayuda_dir = ayuda_dir
        self.cc = None
        self.value = None
        self.note = None
        self.playing = False
        self.muted = False
        self.pulse = {n: 0.0 for n in HIT_PADS}
        self._tex = {}
        self._img_cache = {}
        self._preview_path = None
        self._preview_tex = None
        self._loaded = (None, None)
        self.bind(pos=self._redraw, size=self._redraw)

    def reset(self):
        self.cc = None
        self.value = None
        self.note = None
        self.playing = False
        self.muted = False
        for n in HIT_PADS:
            self.pulse[n] = 0.0
        self._preview_path = None
        self._preview_tex = None
        self._loaded = (None, None)
        self._redraw()

    def set_from(self, pb):
        """Copia RobotPlayback; destella pads si hay hit_note este tick."""
        screen = (pb.cc, pb.value)
        changed = ((self.cc, self.value) != screen
                   or self.muted != pb.muted
                   or self.note != pb.note
                   or self.playing != pb.playing)
        self.cc, self.value = pb.cc, pb.value
        self.note = pb.note
        self.playing = pb.playing
        self.muted = pb.muted
        if screen != self._loaded:
            self._load_preview()
            changed = True
        if pb.hit_note is not None:
            self.hit(pb.hit_note)
            changed = True
        if changed:
            self._redraw()

    def _load_preview(self):
        self._loaded = (self.cc, self.value)
        path = None
        if self.cc is not None and self.value is not None:
            path = ayuda_preview_path(self.ayuda_dir, self.cc, self.value)
        if path == self._preview_path:
            return
        self._preview_path = path
        self._preview_tex = None
        if path is None:
            return
        key = str(path)
        if key not in self._img_cache:
            tex = None
            if path.exists():
                try:
                    tex = CoreImage(key).texture
                except Exception:               # noqa: BLE001
                    tex = None
            self._img_cache[key] = tex
        self._preview_tex = self._img_cache[key]

    def hit(self, note):
        for n in hit_pad_notes(note):
            self.pulse[n] = 1.0

    def tick_pulse(self, dt):
        decay = dt * 4.0
        alive = False
        for n in HIT_PADS:
            if self.pulse[n] > 0:
                self.pulse[n] = max(0.0, self.pulse[n] - decay)
                alive = True
        if alive:
            self._redraw()

    def _texture(self, text, font_size=FONT):
        key = (text, font_size)
        tex = self._tex.get(key)
        if tex is None:
            tex = core_label(text, font_size).texture
            self._tex[key] = tex
        return tex

    def _text_center(self, x, y, w, text, color, h, font_size=FONT):
        tex = self._texture(text, font_size)
        tw, th = tex.size
        Color(*color)
        Rectangle(texture=tex, size=(tw, th),
                  pos=(x + (w - tw) / 2, y + (h - th) / 2))

    def _redraw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(*COLOR_BG)
            Rectangle(pos=self.pos, size=self.size)
            pad_y = self.y + GAP
            preview_bottom = pad_y + PAD_H + GAP
            avail_h = self.height - (preview_bottom - self.y) - GAP * 2 - dp(28)
            avail_w = self.width - GAP * 2
            size = max(dp(1), min(avail_w, avail_h))
            px = self.x + (self.width - size) / 2
            py = preview_bottom + GAP + dp(28)
            self._draw_preview(px, py, size)
            tag = "----"
            if self.cc is not None and self.value is not None:
                tag = screen_label(self.cc, self.value)
            ink = COLOR_SCREEN if not self.muted else COLOR_EMPTY
            self._text_center(px, py - dp(28), size, tag, ink,
                              h=dp(28), font_size=FONT)
            hit_txt = hit_label(self.note) if self.note is not None else "----"
            self._draw_pads(pad_y, hit_txt)

    def _draw_preview(self, px, py, size):
        Color(0.09, 0.10, 0.13, 1)
        Rectangle(pos=(px, py), size=(size, size))
        if self._preview_tex is not None:
            tw, th = self._preview_tex.size
            scale = min(size / tw, size / th) if tw and th else 1
            dw, dh = tw * scale, th * scale
            Color(1, 1, 1, 1)
            Rectangle(texture=self._preview_tex, size=(dw, dh),
                      pos=(px + (size - dw) / 2, py + (size - dh) / 2))
        if self.muted:
            Color(*COLOR_MUTE_OVERLAY)
            Rectangle(pos=(px, py), size=(size, size))
        Color(*COLOR_BORDER)
        Line(rectangle=(px, py, size, size), width=1.2)

    def _draw_pads(self, y, hit_txt):
        w = min(self.width - GAP * 2, dp(720))
        x0 = self.x + (self.width - w) / 2
        cell = (w - GAP * 2) / 3
        for i, note in enumerate(HIT_PADS):
            x = x0 + i * (cell + GAP)
            a = self.pulse[note]
            r, g, b, _a = COLOR_HIT
            Color(r, g, b, a * 0.35 + 0.08)
            RoundedRectangle(pos=(x, y), size=(cell, PAD_H), radius=[dp(10)])
            Color(*COLOR_BORDER)
            Line(rectangle=(x, y, cell, PAD_H), width=1.2)
            ink = tuple(min(1, c + (1 - c) * a) for c in COLOR_HIT[:3]) + (1,)
            draw = _PAD_DRAW[note]
            draw(x + cell / 2, y + PAD_H * 0.58, min(cell, PAD_H) * 0.42, ink)
            self._text_center(x, y + dp(8), cell, _PAD_NAME[note],
                              ink if a > 0.05 else COLOR_HEADER_TXT,
                              h=dp(24), font_size=FONT_SMALL)
        self._text_center(x0, y + PAD_H + dp(2), w, hit_txt,
                          COLOR_HIT if self.note is not None else COLOR_EMPTY,
                          h=dp(22), font_size=FONT_SMALL)
