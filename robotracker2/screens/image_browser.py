"""Navegador visual de `images/` para elegir el evento de pantalla (MDCC).

Dos niveles: elegir la carpeta "control" (imágenes estáticas o animación) y
luego el valor dentro de ella. Con vista previa automática (la imagen, o el
primer frame de la animación) al pasar por cada entrada — a diferencia del
navegador de samples, aquí no hace falta un gesto para "escuchar": **A**
entra en la carpeta o **elige** el valor resaltado (inmediato, sin doble-tap:
ver la vista previa ya es gratis al moverse); **B/Cancelar** vuelve atrás o
cierra. Misma interfaz que `SampleBrowser` (move/activate/back/cleanup) para
que la app los trate igual.
"""

from pathlib import Path

from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, UP
from robots import CC_LABELS, classify_folder
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

ACTIONS = [("A", "Elegir"), ("B", "Cancelar")]


class ImageBrowser(Widget):
    def __init__(self, root, on_load=None, on_close=None, **kw):
        super().__init__(**kw)
        self.root = Path(root)
        self.on_load = on_load
        self.on_close = on_close
        self.level = 0                  # 0 = carpeta control, 1 = valor
        self.cc = None
        self.entries = []
        self.index = 0
        self.top_idx = 0
        self._tex = {}
        self._preview_paths = (None, None)
        self._preview_bg_tex = None
        self._preview_fg_tex = None
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
                if kind not in ("images", "anim"):
                    continue                       # "lyric" u otras: fuera de alcance
                cc = int(p.name)
                tag = CC_LABELS.get(cc, kind.upper())
                kind_txt = "Imágenes" if kind == "images" else "Animaciones"
                entries.append({"label": f"{p.name}  {tag} ({kind_txt})",
                                "path": None, "cc": cc, "kind": kind, "leaf": False})
        self._set_entries(entries)

    def _scan_value(self, cc_entry):
        self.level = 1
        self.cc = cc_entry["cc"]
        base = self.root / f"{self.cc:03d}"
        entries = []
        if cc_entry["kind"] == "images":
            bg = base / "fondo.png"
            bg = bg if bg.exists() else None
            for p in sorted((base / "png").glob("*.png"), key=lambda p: p.name):
                try:
                    value = int(p.stem)
                except ValueError:
                    continue
                entries.append({"label": p.stem, "bg": bg, "fg": p, "cc": self.cc,
                                "value": value, "leaf": True})
        else:                                       # animación
            for p in sorted(base.iterdir(), key=lambda p: p.name):
                if not (p.is_dir() and p.name.isdigit()):
                    continue
                entries.append({"label": p.name, "bg": None,
                                "fg": self._first_frame(p),
                                "cc": self.cc, "value": int(p.name), "leaf": True})
        self._set_entries(entries)

    @staticmethod
    def _first_frame(folder):
        frames = sorted(folder.glob("*.png"))
        return frames[0] if frames else None

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
        paths = (sel.get("bg"), sel.get("fg")) if sel else (None, None)
        if paths == self._preview_paths:
            return
        self._preview_paths = paths
        bg, fg = paths
        self._preview_bg_tex = self._load_tex(bg)
        self._preview_fg_tex = self._load_tex(fg)

    @staticmethod
    def _load_tex(path):
        if path is None or not path.exists():
            return None
        try:
            return CoreImage(str(path)).texture
        except Exception:                            # noqa: BLE001
            return None

    # -- scroll / dibujo -----------------------------------------------
    def _visible(self):
        return max(1, int((self.height - TOP_PAD - BOTTOM_H) // ROW_H))

    def _ensure_visible(self):
        n = self._visible()
        if self.index < self.top_idx:
            self.top_idx = self.index
        elif self.index >= self.top_idx + n:
            self.top_idx = self.index - n + 1

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
            # preview (derecha)
            self._draw_preview(lx + list_w + dp(24), n)
            self._draw_actions(self.center_x)

    def _draw_preview(self, px, n):
        pw = self.width - px - dp(24)
        ph = min(pw, n * ROW_H) if n else pw
        py = self.y + self.height - TOP_PAD - ph
        Color(*COLOR_PREVIEW_BG)
        Rectangle(pos=(px, py), size=(pw, ph))
        if self._preview_bg_tex is not None:
            # fondo.png: rellena el panel (el icono se compone encima, igual
            # que bin/genera.py al generar las imágenes reales).
            Color(1, 1, 1, 1)
            Rectangle(texture=self._preview_bg_tex, size=(pw, ph), pos=(px, py))
        if self._preview_fg_tex is not None:
            tw, th = self._preview_fg_tex.size
            max_w, max_h = pw * 0.8, ph * 0.8   # margen 10% por lado (genera.py)
            scale = min(max_w / tw, max_h / th)
            dw, dh = tw * scale, th * scale
            Color(1, 1, 1, 1)
            Rectangle(texture=self._preview_fg_tex, size=(dw, dh),
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
