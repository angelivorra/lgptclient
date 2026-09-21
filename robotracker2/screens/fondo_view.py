"""Pantalla FONDO: slideshow de imágenes de fondo por canción.

Configura la clave "fondo" del robotraca.json:
  - images: lista de pares [cc, value] a mostrar en ciclo
  - interval: segundos por imagen (0.5–30)
  - transition: "cut" (instantáneo) o "fade" (crossfade)
  - fade_s: duración del fade en segundos (0.1–2.0)

La configuración vive en memoria hasta guardar (fila GUARDAR o Guardar
canción). Controles resueltos por _dispatch_fondo en robotracker2.py:

- arr/abj: moverse por la lista
- A sobre imagen: abre el navegador de imágenes para cambiarla
- B sobre imagen: elimina esa imagen
- A sobre AÑADIR: abre el navegador para agregar una imagen
- A+izq/dcha sobre INTERVALO: ±0.5 s (izq/dcha solos también)
- izq/dcha sobre TRANSICIÓN: alterna cut/fade
- A+izq/dcha sobre FADE: ±0.1 s (izq/dcha solos también)
- A sobre GUARDAR: persiste al robotraca.json
"""

from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, UP
from screens.icons import draw_icon
from theme import (COLOR_ACCENT, COLOR_BG,
                   COLOR_HINT, COLOR_NAME, COLOR_OK, core_label)

_CARD = (0.14, 0.14, 0.15, 1)
_CHIP = (0.10, 0.10, 0.11, 1)
_FADE_COLOR = (0.30, 0.55, 0.90, 1)   # azul: indica modo fade

ROW_H = dp(52)
IMG_ROW_H = dp(48)
FONT = dp(18)
FONT_SMALL = dp(15)
HINT_H = dp(36)

INTERVAL_STEP = 0.5
INTERVAL_MIN = 0.5
INTERVAL_MAX = 30.0
FADE_STEP = 0.1
FADE_MIN = 0.1
FADE_MAX = 2.0


class FondoGrid(Widget):
    """Lista de imágenes del slideshow + parámetros + GUARDAR.

    El SAVE_ROW es dinámico (depende del número de imágenes); la app lo
    consulta via `g.SAVE_ROW` antes de comparar con `g.cursor`.
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self.images = []          # [[cc, value], ...]
        self.interval = 6.0
        self.transition = "cut"   # "cut" | "fade"
        self.fade_s = 0.5
        self.cursor = 0
        self._tex = {}
        self.bind(pos=self._redraw, size=self._redraw)

    # -- filas dinámicas -----------------------------------------------

    @property
    def _add_row(self):
        return len(self.images)

    @property
    def _row_interval(self):
        return len(self.images) + 1

    @property
    def _row_transition(self):
        return len(self.images) + 2

    @property
    def _row_fade(self):
        return len(self.images) + 3

    @property
    def SAVE_ROW(self):
        # Con "cut", la fila FADE no se muestra: GUARDAR ocupa su posición.
        if self.transition == "cut":
            return len(self.images) + 3
        return len(self.images) + 4

    # -- estado --------------------------------------------------------

    def set_state(self, fondo):
        """Inyecta dict con images/interval/transition/fade_s."""
        self.images = [list(img) for img in fondo.get("images", [])]
        self.interval = float(fondo.get("interval", 6.0))
        self.transition = fondo.get("transition", "cut")
        self.fade_s = float(fondo.get("fade_s", 0.5))
        self.cursor = min(self.cursor, self.SAVE_ROW)
        self._redraw()

    def get_state(self):
        """Dict listo para persistir en robotraca.json["fondo"]."""
        state = {
            "images": [list(img) for img in self.images],
            "interval": round(self.interval, 1),
            "transition": self.transition,
        }
        if self.transition == "fade":
            state["fade_s"] = round(self.fade_s, 1)
        return state

    # -- cursor --------------------------------------------------------

    def move(self, button):
        if button == UP:
            self.cursor = max(0, self.cursor - 1)
        elif button == DOWN:
            self.cursor = min(self.SAVE_ROW, self.cursor + 1)
        self._redraw()

    def is_image_row(self):
        return 0 <= self.cursor < len(self.images)

    def is_add_row(self):
        return self.cursor == self._add_row

    def is_interval_row(self):
        return self.cursor == self._row_interval

    def is_transition_row(self):
        return self.cursor == self._row_transition

    def is_fade_row(self):
        return self.transition == "fade" and self.cursor == self._row_fade

    # -- dibujo --------------------------------------------------------

    def _texture(self, text, font_size=FONT):
        key = (text, font_size)
        tex = self._tex.get(key)
        if tex is None:
            tex = core_label(text, font_size).texture
            self._tex[key] = tex
        return tex

    def _text_left(self, x, y, w, text, color, h=ROW_H, font_size=FONT):
        tex = self._texture(text, font_size)
        tw, th = tex.size
        Color(*color)
        Rectangle(texture=tex, size=(tw, th), pos=(x, y + (h - th) / 2))

    def _text_center(self, x, y, w, text, color, h=ROW_H, font_size=FONT):
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

            w = min(self.width - dp(48), dp(640))
            x0 = self.x + (self.width - w) / 2
            top = self.y + self.height - dp(16)

            # Cabecera
            head_y = top - ROW_H
            draw_icon(x0 + dp(16), head_y + ROW_H / 2, dp(24),
                      "pads", COLOR_ACCENT)
            self._text_left(x0 + dp(40), head_y, w,
                            "FONDO", COLOR_ACCENT, h=ROW_H)

            # Hint
            hint = ("A: elegir · B: quitar · A+izq/dcha: editar valores · "
                    "arr/abj: mover")
            self._text_left(x0 + dp(8), self.y + dp(8), w, hint,
                            COLOR_HINT, h=HINT_H, font_size=FONT_SMALL)

            content_top = head_y - dp(4)

            # ---- imágenes ----
            row_y = content_top
            for i, (cc, value) in enumerate(self.images):
                row_y -= IMG_ROW_H
                self._draw_image_row(i, cc, value, x0, row_y, w, IMG_ROW_H)

            # ---- AÑADIR ----
            row_y -= ROW_H
            self._draw_add_row(x0, row_y, w, ROW_H)

            # ---- separador ----
            row_y -= dp(10)
            Color(*_CHIP)
            Rectangle(pos=(x0, row_y), size=(w, dp(1)))
            row_y -= dp(10)

            # ---- INTERVALO ----
            row_y -= ROW_H
            self._draw_param_row(
                "INTERVALO", f"{self.interval:.1f} s",
                x0, row_y, w, ROW_H,
                self.cursor == self._row_interval,
            )

            # ---- TRANSICIÓN ----
            row_y -= ROW_H
            self._draw_transition_row(x0, row_y, w, ROW_H)

            # ---- FADE (solo si transición=fade) ----
            if self.transition == "fade":
                row_y -= ROW_H
                self._draw_param_row(
                    "FADE", f"{self.fade_s:.1f} s",
                    x0, row_y, w, ROW_H,
                    self.cursor == self._row_fade,
                )

            # ---- GUARDAR (anclado abajo) ----
            save_h = dp(52)
            save_y = self.y + dp(8) + HINT_H + dp(8)
            self._draw_save(x0, save_y, w, save_h - dp(6))

    def _draw_image_row(self, i, cc, value, x, y, w, h):
        selected = i == self.cursor
        Color(*(COLOR_ACCENT if selected else _CARD))
        RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(10)])
        if selected:
            Color(*_CARD)
            RoundedRectangle(pos=(x + dp(3), y + dp(3)),
                             size=(w - dp(6), h - dp(6)), radius=[dp(8)])
        ink = COLOR_ACCENT if selected else COLOR_NAME
        dim = COLOR_HINT if not selected else COLOR_HINT
        # número de posición
        self._text_left(x + dp(12), y, dp(32), f"{i + 1}.",
                        dim, h=h, font_size=FONT_SMALL)
        # icono + CC/VAL
        draw_icon(x + dp(46), y + h / 2, dp(16), "pads",
                  COLOR_ACCENT if selected else COLOR_HINT)
        label = f"CC {cc:03d}   VAL {value:03d}"
        self._text_left(x + dp(66), y, w - dp(80), label,
                        ink, h=h, font_size=FONT)

    def _draw_add_row(self, x, y, w, h):
        selected = self.cursor == self._add_row
        Color(*(COLOR_OK if selected else _CHIP))
        RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(10)])
        ink = COLOR_BG if selected else COLOR_HINT
        draw_icon(x + w / 2 - dp(64), y + h / 2, dp(20), "empty", ink)
        self._text_center(x + dp(12), y, w, "AÑADIR IMAGEN", ink, h=h)

    def _draw_param_row(self, label, value_str, x, y, w, h, selected):
        Color(*(COLOR_ACCENT if selected else _CARD))
        RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(10)])
        if selected:
            Color(*_CARD)
            RoundedRectangle(pos=(x + dp(3), y + dp(3)),
                             size=(w - dp(6), h - dp(6)), radius=[dp(8)])
        ink = COLOR_ACCENT if selected else COLOR_NAME
        self._text_left(x + dp(16), y, w / 2, label, ink, h=h)
        chip_w = dp(80)
        cx = x + w - chip_w - dp(12)
        cy = y + (h - dp(28)) / 2
        Color(*_CHIP)
        RoundedRectangle(pos=(cx, cy), size=(chip_w, dp(28)), radius=[dp(8)])
        self._text_center(cx, cy, chip_w, value_str,
                          COLOR_ACCENT if selected else COLOR_HINT,
                          h=dp(28), font_size=FONT_SMALL)

    def _draw_transition_row(self, x, y, w, h):
        selected = self.cursor == self._row_transition
        Color(*(COLOR_ACCENT if selected else _CARD))
        RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(10)])
        if selected:
            Color(*_CARD)
            RoundedRectangle(pos=(x + dp(3), y + dp(3)),
                             size=(w - dp(6), h - dp(6)), radius=[dp(8)])
        ink = COLOR_ACCENT if selected else COLOR_NAME
        self._text_left(x + dp(16), y, w / 2, "TRANSICIÓN", ink, h=h)
        chip_w = dp(72)
        cx = x + w - chip_w - dp(12)
        cy = y + (h - dp(28)) / 2
        is_fade = self.transition == "fade"
        Color(*(_FADE_COLOR if is_fade else _CHIP))
        RoundedRectangle(pos=(cx, cy), size=(chip_w, dp(28)), radius=[dp(8)])
        self._text_center(
            cx, cy, chip_w,
            "FADE" if is_fade else "CUT",
            COLOR_BG if is_fade else (COLOR_ACCENT if selected else COLOR_HINT),
            h=dp(28), font_size=FONT_SMALL,
        )

    def _draw_save(self, x, y, w, h):
        selected = self.cursor == self.SAVE_ROW
        Color(*(COLOR_OK if selected else _CARD))
        RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(12)])
        ink = COLOR_BG if selected else COLOR_HINT
        draw_icon(x + w / 2 - dp(52), y + h / 2, dp(22), "save", ink)
        self._text_center(x + dp(16), y, w, "GUARDAR", ink, h=h)
