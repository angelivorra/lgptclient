"""Navegador visual de `images/` para elegir el evento de pantalla (MDCC).

Dos niveles: elegir la carpeta "control" (imágenes estáticas, animación o
texto sincronizado) y luego el valor dentro de ella. La vista previa usa la
miniatura YA renderizada en `ayuda_imagenes/` (mismo fondo+icono/glow/frame
que ve el dispositivo real; ver `robots.ayuda_preview_path`) y se actualiza
sola al moverse — a diferencia del navegador de samples, aquí no hace falta
un gesto para "escuchar": **A** entra en la carpeta o **elige** el valor
resaltado (inmediato, sin doble-tap), **B/Cancelar** vuelve atrás o cierra.
Misma interfaz que `SampleBrowser` (move/activate/back/cleanup). Sobre y
bajo la lista hay dos indicadores de poco alto (triángulos) que se
encienden si se puede navegar hacia arriba/abajo en esa dirección.
"""

from pathlib import Path

from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle, Triangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, UP
from robots import CC_LABELS, ayuda_preview_path, classify_folder, lyric_lines
from theme import COLOR_ACCENT, COLOR_BG, COLOR_BTN

ROW_H = dp(30)
TOP_PAD = dp(70)
BOTTOM_H = dp(76)
FONT = dp(18)
LIST_FRAC = 0.42                # fracción de ancho para la lista (resto: preview)

COLOR_ITEM = (0.87, 0.89, 0.92, 1)
COLOR_HEADER = (0.95, 0.75, 0.20, 1)
COLOR_SCRIM = (0.03, 0.03, 0.05, 0.97)
COLOR_ACTION = (0.75, 0.77, 0.82, 1)
COLOR_PREVIEW_BG = (0.10, 0.10, 0.13, 1)
COLOR_PREVIEW_BORDER = (0.36, 0.38, 0.46, 1)

_KIND_TXT = {"images": "Imágenes", "anim": "Animaciones", "lyric": "Texto"}

ACTIONS = [("A", "Elegir"), ("B", "Cancelar")]


class ImageBrowser(Widget):
    def __init__(self, root, ayuda_dir=None, on_load=None, on_close=None, **kw):
        super().__init__(**kw)
        self.root = Path(root)
        self.ayuda_dir = Path(ayuda_dir) if ayuda_dir else None
        self.on_load = on_load
        self.on_close = on_close
        self.level = 0                  # 0 = carpeta control, 1 = valor
        self.cc = None
        self.entries = []
        self.index = 0
        self.top_idx = 0
        self._tex = {}
        self._preview_path = None
        self._preview_tex = None
        self.bind(pos=self._redraw, size=self._redraw)
        self._scan_root()

    # -- niveles ----------------------------------------------------------
    def _scan_root(self):
        self.level = 0
        self.cc = None
        entries = []
        if self.root.is_dir():
            for p in sorted(self.root.iterdir(), key=lambda p: p.name):
                if not (p.is_dir() and p.name.isdigit()):
                    continue
                kind = classify_folder(p)
                if kind not in ("images", "anim", "lyric"):
                    continue
                cc = int(p.name)
                tag = CC_LABELS.get(cc, kind.upper())
                entries.append({"label": f"{p.name}  {tag} ({_KIND_TXT[kind]})",
                                "cc": cc, "kind": kind, "leaf": False})
        self._set_entries(entries)

    def _scan_value(self, cc_entry):
        self.level = 1
        self.cc = cc_entry["cc"]
        kind = cc_entry["kind"]
        base = self.root / f"{self.cc:03d}"
        entries = []
        if kind == "images":
            for p in sorted((base / "png").glob("*.png"), key=lambda p: p.name):
                try:
                    value = int(p.stem)
                except ValueError:
                    continue
                entries.append({"label": p.stem, "cc": self.cc,
                                "value": value, "leaf": True})
        elif kind == "anim":
            for p in sorted(base.iterdir(), key=lambda p: p.name):
                if not (p.is_dir() and p.name.isdigit()):
                    continue
                entries.append({"label": p.name, "cc": self.cc,
                                "value": int(p.name), "leaf": True})
        else:                                       # lyric: líneas de textos
            for value, line in enumerate(lyric_lines(self.root)):
                entries.append({"label": f"{value:03d}  {line}", "cc": self.cc,
                                "value": value, "leaf": True})
        self._set_entries(entries)

    def _set_entries(self, entries):
        self.entries = entries
        self.index = 0
        self.top_idx = 0
        self._update_preview()
        self._redraw()

    def selected(self):
        return self.entries[self.index] if self.entries else None

    # -- navegación ---------------------------------------------------------
    def move(self, button):
        if not self.entries:
            return
        if button == UP:
            self.index = max(0, self.index - 1)
        elif button == DOWN:
            self.index = min(len(self.entries) - 1, self.index + 1)
        self._ensure_visible()
        self._update_preview()
        self._redraw()

    def activate(self):
        sel = self.selected()
        if sel is None:
            return
        if sel["leaf"]:
            if self.on_load:
                self.on_load(sel["cc"], sel["value"])
        else:
            self._scan_value(sel)

    def back(self):
        if self.level == 1:
            self._scan_root()
        elif self.on_close:
            self.on_close()

    def cleanup(self):
        pass                                        # sin audio que parar

    # -- vista previa ---------------------------------------------------
    def _update_preview(self):
        sel = self.selected()
        path = ayuda_preview_path(self.ayuda_dir, sel["cc"], sel["value"]) \
            if sel and sel["leaf"] else None
        if path == self._preview_path:
            return
        self._preview_path = path
        self._preview_tex = None
        if path is not None and path.exists():
            try:
                self._preview_tex = CoreImage(str(path)).texture
            except Exception:                       # noqa: BLE001
                self._preview_tex = None

    # -- scroll / dibujo -----------------------------------------------
    def _visible(self):
        return max(1, int((self.height - TOP_PAD - BOTTOM_H) // ROW_H))

    def _ensure_visible(self):
        n = self._visible()
        if self.index < self.top_idx:
            self.top_idx = self.index
        elif self.index >= self.top_idx + n:
            self.top_idx = self.index - n + 1

    def _scroll_flags(self):
        """(hay más arriba, hay más abajo) de la ventana visible de la
        lista: encienden/apagan los indicadores de scroll."""
        n = self._visible()
        return self.top_idx > 0, self.top_idx + n < len(self.entries)

    def _texture(self, text):
        tex = self._tex.get(text)
        if tex is None:
            lbl = CoreLabel(text=text, font_size=FONT, bold=True)
            lbl.refresh()
            tex = lbl.texture
            self._tex[text] = tex
        return tex

    def _text_left(self, x, y, text, color):
        tex = self._texture(text)
        Color(*color)
        Rectangle(texture=tex, size=tex.size,
                  pos=(x, y + (ROW_H - tex.size[1]) / 2))

    def _text_centered(self, cx, y, text, color):
        tex = self._texture(text)
        Color(*color)
        Rectangle(texture=tex, size=tex.size,
                  pos=(cx - tex.size[0] / 2, y + (ROW_H - tex.size[1]) / 2))

    def _redraw(self, *_):
        self.canvas.clear()
        n = self._visible()
        list_w = self.width * LIST_FRAC
        lx = self.x + dp(24)
        path_txt = "images/" if self.level == 0 else f"images/{self.cc:03d}"
        with self.canvas:
            Color(*COLOR_SCRIM)
            Rectangle(pos=self.pos, size=self.size)
            self._text_centered(self.center_x, self.y + self.height - dp(48),
                                 path_txt, COLOR_HEADER)
            # lista (izquierda)
            for i in range(self.top_idx, min(self.top_idx + n, len(self.entries))):
                e = self.entries[i]
                y = self.y + self.height - TOP_PAD - (i - self.top_idx + 1) * ROW_H
                if i == self.index:
                    Color(*COLOR_ACCENT)
                    RoundedRectangle(pos=(lx - dp(8), y + dp(2)),
                                     size=(list_w, ROW_H - dp(4)), radius=[dp(6)])
                    color = COLOR_BG
                else:
                    color = COLOR_ITEM
                self._text_left(lx, y, e["label"], color)
            # indicadores de scroll: encendidos si hay más lista en esa
            # dirección, atenuados si no se puede navegar hacia allí
            cx_list = lx + list_w / 2
            can_up, can_down = self._scroll_flags()
            self._draw_scroll_indicator(
                cx_list, self.y + self.height - TOP_PAD + dp(4),
                up=True, on=can_up)
            self._draw_scroll_indicator(
                cx_list,
                self.y + self.height - TOP_PAD - n * ROW_H - dp(10),
                up=False, on=can_down)
            # preview (derecha)
            self._draw_preview(lx + list_w + dp(24), n)
            self._draw_actions(self.center_x)

    def _draw_scroll_indicator(self, cx, y, up, on):
        """Triángulo pequeño (poco alto) que indica si hay contenido
        arriba/abajo de la ventana visible de la lista."""
        w, h = dp(9), dp(6)
        if up:
            pts = [cx - w, y, cx + w, y, cx, y + h]
        else:
            pts = [cx - w, y + h, cx + w, y + h, cx, y]
        Color(*(COLOR_ACCENT if on else (0.30, 0.31, 0.38, 1)))
        Triangle(points=pts)

    def _draw_preview(self, px, n):
        pw = self.width - px - dp(24)
        ph = min(pw, n * ROW_H) if n else pw
        py = self.y + self.height - TOP_PAD - ph
        Color(*COLOR_PREVIEW_BG)
        Rectangle(pos=(px, py), size=(pw, ph))
        if self._preview_tex is not None:
            tw, th = self._preview_tex.size
            scale = min(pw / tw, ph / th)
            dw, dh = tw * scale, th * scale
            Color(1, 1, 1, 1)
            Rectangle(texture=self._preview_tex, size=(dw, dh),
                      pos=(px + (pw - dw) / 2, py + (ph - dh) / 2))
        Color(*COLOR_PREVIEW_BORDER)
        Line(rectangle=(px, py, pw, ph), width=1.2)

    def _draw_actions(self, cx):
        bw, bh, gap = dp(180), dp(48), dp(16)
        total = len(ACTIONS) * bw + (len(ACTIONS) - 1) * gap
        x = cx - total / 2
        y = self.y + dp(16)
        for key, label in ACTIONS:
            Color(*COLOR_BTN)
            RoundedRectangle(pos=(x, y), size=(bw, bh), radius=[dp(10)])
            tex = self._texture(f"{key}  {label}")
            Color(*COLOR_ACTION)
            Rectangle(texture=tex, size=tex.size,
                      pos=(x + (bw - tex.size[0]) / 2,
                           y + (bh - tex.size[1]) / 2))
            x += bw + gap
