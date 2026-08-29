"""Navegador de samples estilo LGPT: navegar la carpeta, escuchar e importar.

Todo centrado. Abajo, tres acciones como en LGPT: Escuchar / Import / Cancelar.
Arr/abj mueve; **A** (`activate()`) escucha el sample seleccionado (o entra en
la carpeta); **doble A** importa el sample (lo copia a la canción y lo asigna
al instrumento); **B/Cancelar** sube de carpeta (o cierra en la raíz). El
doble-tap se gestiona dentro del propio widget (ver `activate()`), así la app
solo necesita mover/activar/volver: la misma interfaz que `ImageBrowser`.
"""

from pathlib import Path

from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, UP
from theme import COLOR_ACCENT, COLOR_BG, COLOR_BTN

ROW_H = dp(30)
TOP_PAD = dp(70)
BOTTOM_H = dp(76)
FONT = dp(18)

COLOR_DIR = (0.55, 0.75, 0.95, 1)
COLOR_WAV = (0.87, 0.89, 0.92, 1)
COLOR_HEADER = (0.95, 0.75, 0.20, 1)
COLOR_SCRIM = (0.03, 0.03, 0.05, 0.97)
COLOR_ACTION = (0.75, 0.77, 0.82, 1)

ACTIONS = [("A", "Escuchar"), ("AA", "Import"), ("B", "Cancelar")]


class SampleBrowser(Widget):
    def __init__(self, root, on_load=None, on_close=None, **kw):
        super().__init__(**kw)
        self.root = Path(root)
        self.cwd = self.root
        self.on_load = on_load
        self.on_close = on_close
        self.entries = []
        self.index = 0
        self.top_idx = 0
        self._a_pending = False        # para el doble-tap (escuchar / importar)
        self._tex = {}
        self.bind(pos=self._redraw, size=self._redraw)
        self._scan()

    # -- navegación de carpetas ----------------------------------------
    def _scan(self):
        try:
            items = list(self.cwd.iterdir())
        except OSError:
            items = []
        dirs = sorted((p for p in items if p.is_dir()),
                      key=lambda p: p.name.lower())
        wavs = sorted((p for p in items if p.is_file()
                       and p.suffix.lower() == ".wav"),
                      key=lambda p: p.name.lower())
        self.entries = dirs + wavs
        self.index = 0
        self.top_idx = 0
        self._redraw()

    def selected(self):
        return self.entries[self.index] if self.entries else None

    def move(self, button):
        if not self.entries:
            return
        if button == UP:
            self.index = max(0, self.index - 1)
        elif button == DOWN:
            self.index = min(len(self.entries) - 1, self.index + 1)
        self._ensure_visible()
        self._redraw()

    def activate(self):
        """A: entra en carpeta, o escucha el sample (doble-tap = importar)."""
        sel = self.selected()
        if sel is None:
            return
        if sel.is_dir():
            self.cwd = sel
            self._scan()
            return
        if self._a_pending:
            self._a_pending = False
            Clock.unschedule(self._clear_pending)
            self.import_current()
        else:
            self.preview_current()
            self._a_pending = True
            Clock.schedule_once(self._clear_pending, 0.5)

    def _clear_pending(self, *_):
        self._a_pending = False

    def cleanup(self):
        """Al cerrar el navegador: parar audio y cancelar el doble-tap pendiente."""
        self.stop_preview()
        Clock.unschedule(self._clear_pending)
        self._a_pending = False

    def preview_current(self):
        sel = self.selected()
        if sel is None or sel.is_dir():
            return
        try:
            import sounddevice as sd
            import soundfile as sf
            data, sr = sf.read(str(sel), dtype="float32")
            sd.stop()
            sd.play(data, sr)
        except Exception:                       # noqa: BLE001
            pass

    def import_current(self):
        sel = self.selected()
        if sel is not None and sel.is_file() and self.on_load:
            self.on_load(sel)

    def back(self):
        if self.cwd != self.root and self.root in self.cwd.parents:
            self.cwd = self.cwd.parent
            self._scan()
        elif self.on_close:
            self.on_close()

    @staticmethod
    def stop_preview():
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:                       # noqa: BLE001
            pass

    # -- scroll ---------------------------------------------------------
    def _visible(self):
        return max(1, int((self.height - TOP_PAD - BOTTOM_H) // ROW_H))

    def _ensure_visible(self):
        n = self._visible()
        if self.index < self.top_idx:
            self.top_idx = self.index
        elif self.index >= self.top_idx + n:
            self.top_idx = self.index - n + 1

    # -- dibujo ---------------------------------------------------------
    def _texture(self, text):
        tex = self._tex.get(text)
        if tex is None:
            lbl = CoreLabel(text=text, font_size=FONT, bold=True)
            lbl.refresh()
            tex = lbl.texture
            self._tex[text] = tex
        return tex

    def _text_centered(self, cx, y, text, color):
        tex = self._texture(text)
        Color(*color)
        Rectangle(texture=tex, size=tex.size,
                  pos=(cx - tex.size[0] / 2, y + (ROW_H - tex.size[1]) / 2))

    def _redraw(self, *_):
        self.canvas.clear()
        n = self._visible()
        cx = self.center_x
        hl_w = min(self.width * 0.7, dp(560))
        try:
            rel = self.cwd.relative_to(self.root)
            path_txt = "samples/" + (str(rel) if str(rel) != "." else "")
        except ValueError:
            path_txt = str(self.cwd)
        with self.canvas:
            Color(*COLOR_SCRIM)
            Rectangle(pos=self.pos, size=self.size)
            # cabecera (ruta) centrada
            self._text_centered(cx, self.y + self.height - dp(48),
                                 path_txt, COLOR_HEADER)
            # lista centrada
            for i in range(self.top_idx, min(self.top_idx + n, len(self.entries))):
                p = self.entries[i]
                y = self.y + self.height - TOP_PAD - (i - self.top_idx + 1) * ROW_H
                name = p.name + ("/" if p.is_dir() else "")
                if i == self.index:
                    Color(*COLOR_ACCENT)
                    RoundedRectangle(pos=(cx - hl_w / 2, y + dp(2)),
                                     size=(hl_w, ROW_H - dp(4)), radius=[dp(6)])
                    color = COLOR_BG
                else:
                    color = COLOR_DIR if p.is_dir() else COLOR_WAV
                self._text_centered(cx, y, name, color)
            # barra de acciones (Escuchar / Import / Cancelar) centrada
            self._draw_actions(cx)

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
