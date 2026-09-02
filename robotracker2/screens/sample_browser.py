"""Navegador de samples estilo LGPT: navegar la carpeta, escuchar e importar.

Todo centrado. Abajo, dos acciones como en ImageBrowser: Elegir / Cancelar.
Arr/abj mueve; al pasar por un .wav se **previsualiza**; **A** (`activate()`)
entra en la carpeta o **carga** el sample (copia a la canción y lo asigna);
**B/Cancelar** sube de carpeta (o cierra en la raíz). Las flechas izq/dcha
van **atrás/adelante por el historial de carpetas** con memoria, recordando
la posición del cursor en cada carpeta. Si falla la preview, `on_toast`
muestra el error (la app pasa el toast del editor).
"""

from pathlib import Path

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, LEFT, RIGHT, UP
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

ACTIONS = [("A", "Elegir"), ("B", "Cancelar")]


class SampleBrowser(Widget):
    def __init__(self, root, on_load=None, on_close=None, on_toast=None, **kw):
        super().__init__(**kw)
        self.root = Path(root)
        self.cwd = self.root
        self.on_load = on_load
        self.on_close = on_close
        self.on_toast = on_toast
        self.entries = []
        self.index = 0
        self.top_idx = 0
        self._back = []     # historial hacia atrás: (cwd, index, top_idx)
        self._fwd = []      # historial hacia delante (para la flecha dcha)
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
        self._preview_selection()
        self._redraw()

    def selected(self):
        return self.entries[self.index] if self.entries else None

    # -- historial de carpetas (flechas izq/dcha) ----------------------
    def _remember(self, stack):
        stack.append((self.cwd, self.index, self.top_idx))

    def _restore(self, entry):
        path, index, top_idx = entry
        self.cwd = path
        self._scan()
        self.index = min(index, max(0, len(self.entries) - 1))
        self.top_idx = max(0, min(top_idx, max(0, len(self.entries) - 1)))
        self._ensure_visible()
        self._preview_selection()
        self._redraw()

    def go_back(self):
        """Flecha atrás: vuelve por el historial de carpetas recordando la
        posición del cursor en cada una (dos niveles y los que haya)."""
        if not self._back:
            return
        self._remember(self._fwd)
        self._restore(self._back.pop())

    def go_forward(self):
        """Flecha adelante: rehace el historial de carpetas."""
        if not self._fwd:
            return
        self._remember(self._back)
        self._restore(self._fwd.pop())

    def move(self, button):
        if not self.entries:
            return
        if button == UP:
            self.index = max(0, self.index - 1)
        elif button == DOWN:
            self.index = min(len(self.entries) - 1, self.index + 1)
        self._ensure_visible()
        self._preview_selection()
        self._redraw()

    def activate(self):
        """A: entra en carpeta, o carga el sample (la preview es al moverse)."""
        sel = self.selected()
        if sel is None:
            return
        if sel.is_dir():
            self._remember(self._back)
            self._fwd.clear()          # rama nueva: el historial muere aquí
            self.cwd = sel
            self._scan()
            return
        self.import_current()

    def cleanup(self):
        """Al cerrar el navegador: parar audio de la preview."""
        self.stop_preview()

    def _preview_selection(self):
        sel = self.selected()
        if sel is None or sel.is_dir():
            self.stop_preview()
            return
        self.preview_current()

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
        except Exception as exc:                    # noqa: BLE001
            if self.on_toast:
                self.on_toast(f"Preview: {exc}")

    def import_current(self):
        sel = self.selected()
        if sel is not None and sel.is_file() and self.on_load:
            self.on_load(sel)

    def back(self):
        if self.cwd != self.root and self.root in self.cwd.parents:
            self._remember(self._fwd)  # la flecha dcha puede volver a bajar
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
