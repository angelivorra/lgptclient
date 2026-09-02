"""Pantalla EFECTOS: configuración por canción de los knobs del controlador.

Una fila por knob configurable (POT 1, 2, 5 y 6 — los CC del LPD8; entre
corchetes, el CC físico). Por cada knob, tres columnas editables:

- CANAL: canal al que afecta (1-8; en el robotraca.json se guarda 0-7).
  Si el JSON trae varios ("1,2:acid"), se muestra el primero y al editar
  queda en uno solo.
- EFECTO: "off" + los de EFFECT_PRESETS (valve/bass_drive/acid/acid_lfo/
  delay/metal/bode/overdrive/crossover/trance_gate). "off" deja el knob
  sin target.
- %: mezcla dry/wet del efecto en ese canal (clave "fx_mix" del
  robotraca.json, como el slider mix del mixer; 100 = sin fx_mix).

La configuración vive en memoria (cfg de MidiControl) hasta guardar: la
fila GUARDAR de abajo (A sobre ella) o Guardar de la canción la persisten
en el robotraca.json (claves "pots" y "fx_mix"); NO toca el flag de
"canción sucia" del editor. Los cambios se aplican en vivo: la lista de
targets del callback MIDI se reconstruye al momento y el fx_mix entra al
engine por push_event.

Solo dibuja: el estado y la persistencia viven en MidiControl
(set_state/pots_state/set_pot_canal/set_pot_efecto_nombre/set_pot_mix/
save). Controles (los resuelve la app en _dispatch_pots), estilo tracker:

- arr/abj: knob (y bajar a GUARDAR); izq/dcha: columna CANAL / EFECTO / %
- la celda y la cabecera de columna dicen qué cambia A+dirección
- CANAL: A+dir cicla 1-8
- EFECTO: A+dir cicla el preset; A abre la LISTA (arr/abj, A elige, B cierra)
- %: A+izq/dcha ±1 · A+arr/abj ±10
- A sobre GUARDAR: guarda; select no hace nada aquí
"""

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, UP
from sinte_bridge import EFFECT_PRESETS
from theme import (COLOR_ACCENT, COLOR_BG, COLOR_BORDER, COLOR_EMPTY,
                   COLOR_HEADER_TXT, COLOR_HINT, COLOR_HINT_BG, COLOR_NAME,
                   COLOR_OK, COLOR_ROW_CURSOR, COLOR_VOL)

POT_NOS = [1, 2, 5, 6]              # knobs configurables del controlador
EFFECT_CYCLE = ["off", *EFFECT_PRESETS]     # lista del picker de efectos
COL_HEADERS = ("CANAL", "EFECTO", "%")
COL_HINTS = (
    "A+dir: cambia CANAL (1–8)",
    "A+dir: cambia EFECTO · A: lista",
    "A+izq/dcha: % ±1 · A+arr/abj: % ±10",
)
ROW_H = dp(76)
GUTTER = dp(170)                    # columna "POT n"
COL_W = (dp(120), dp(240), dp(110))  # canal / efecto / %
FONT = dp(20)
FONT_SMALL = dp(16)
PICK_ROW_H = dp(48)                 # fila de la lista de efectos (overlay)
HINT_H = dp(36)


class PotsGrid(Widget):
    """4 filas (POT 1/2/5/6) + fila GUARDAR; cursor de fila y de columna
    (0=canal, 1=efecto, 2=%). `picker` no-None = lista de efectos abierta
    (cursor dentro de EFFECT_CYCLE), dibujada encima como overlay."""

    SAVE_ROW = 4                    # fila GUARDAR (última del cursor)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.pots = [(None, None, 100)] * 4   # (canal, efecto, pct)
        self.cursor = 0
        self.col = 0
        self.picker = None          # índice en EFFECT_CYCLE o None (cerrada)
        self._tex = {}
        self.bind(pos=self._redraw, size=self._redraw)

    def set_state(self, pots):
        """Inyecta [(canal_o_None, efecto_o_None, pct)] de los knobs 1/2/5/6
        (MidiControl.pots_state)."""
        if pots != self.pots:
            self.pots = pots
            self._redraw()

    def move(self, button):
        if button == UP:
            self.cursor = max(0, self.cursor - 1)
        elif button == DOWN:
            self.cursor = min(self.SAVE_ROW, self.cursor + 1)
        self._redraw()

    def move_col(self, delta):
        self.col = (self.col + delta) % 3
        self._redraw()

    # -- lista de efectos (overlay) --------------------------------------
    def open_picker(self):
        """Abre la lista de efectos (estilo tracker) con el cursor sobre el
        efecto actual del knob seleccionado."""
        efe = self.pots[self.cursor][1]
        self.picker = EFFECT_CYCLE.index(efe) if efe in EFFECT_CYCLE else 0
        self._redraw()

    def picker_move(self, delta):
        if self.picker is not None:
            self.picker = max(0, min(len(EFFECT_CYCLE) - 1,
                                     self.picker + delta))
            self._redraw()

    def picker_selected(self):
        """Nombre del efecto bajo el cursor de la lista (None si cerrada)."""
        return EFFECT_CYCLE[self.picker] if self.picker is not None else None

    def close_picker(self):
        self.picker = None
        self._redraw()

    # -- dibujo ---------------------------------------------------------
    def _texture(self, text, font_size=FONT):
        key = (text, font_size)
        tex = self._tex.get(key)
        if tex is None:
            lbl = CoreLabel(text=text, font_size=font_size, bold=True)
            lbl.refresh()
            tex = lbl.texture
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
            w = min(self.width - dp(60), dp(640))
            x0 = self.x + (self.width - w) / 2
            top = self.y + self.height - dp(30)
            # título + cabeceras de columna (qué campo edita A+dir)
            self._text_left(x0, top - ROW_H / 2, w, "EFECTOS",
                            COLOR_ACCENT, h=ROW_H)
            y_hdr = top - ROW_H - dp(4)
            for c, header in enumerate(COL_HEADERS):
                x = x0 + GUTTER + sum(COL_W[:c])
                hdr_on = (self.cursor != self.SAVE_ROW and c == self.col
                          and self.picker is None)
                self._text_left(x + dp(8), y_hdr, COL_W[c], header,
                                COLOR_ACCENT if hdr_on else COLOR_HEADER_TXT,
                                h=dp(28), font_size=FONT_SMALL)
            for i in range(4):
                y = top - (i + 2) * ROW_H
                sel = i == self.cursor
                if sel:
                    Color(*COLOR_ROW_CURSOR)
                    Rectangle(pos=(x0, y), size=(w, ROW_H - dp(8)))
                self._text_left(x0 + dp(16), y, GUTTER,
                                f"POT {POT_NOS[i]}",
                                COLOR_ACCENT if sel else COLOR_BORDER,
                                font_size=FONT_SMALL)
                canal, efecto, pct = self.pots[i]
                col = [f"C {canal}" if canal else "—",
                       efecto if efecto else "—",
                       f"{pct}%" if efecto else "—"]
                for c in range(3):
                    x = x0 + GUTTER + sum(COL_W[:c])
                    cell = sel and c == self.col
                    if cell:
                        Color(*COLOR_ACCENT)
                        RoundedRectangle(pos=(x + dp(2), y + dp(6)),
                                         size=(COL_W[c] - dp(6),
                                               ROW_H - dp(20)),
                                         radius=[dp(4)])
                        Color(*COLOR_ROW_CURSOR)
                        RoundedRectangle(pos=(x + dp(6), y + dp(10)),
                                         size=(COL_W[c] - dp(14),
                                               ROW_H - dp(28)),
                                         radius=[dp(3)])
                    if cell:
                        color = COLOR_ACCENT
                    elif col[c] == "—":
                        color = COLOR_EMPTY
                    elif c == 2:
                        color = COLOR_VOL
                    else:
                        color = COLOR_NAME
                    self._text_left(x + dp(8), y, COL_W[c], col[c], color)
            # fila GUARDAR (cursor 4): botón de abajo para persistir; en
            # verde (acción) cuando está seleccionada, gris si no.
            y = top - 6 * ROW_H
            if self.cursor == self.SAVE_ROW:
                Color(*COLOR_ROW_CURSOR)
                Rectangle(pos=(x0, y), size=(w, ROW_H - dp(8)))
                Color(*COLOR_OK)
                RoundedRectangle(pos=(x0 + dp(3), y + dp(3)),
                                 size=(w - dp(6), ROW_H - dp(14)),
                                 radius=[dp(6)])
                Color(*COLOR_ROW_CURSOR)
                RoundedRectangle(pos=(x0 + dp(7), y + dp(7)),
                                 size=(w - dp(14), ROW_H - dp(22)),
                                 radius=[dp(4)])
                self._text_center(x0, y, w, "GUARDAR", COLOR_OK, h=ROW_H)
            else:
                self._text_center(x0, y, w, "GUARDAR", COLOR_HINT, h=ROW_H)
            self._draw_hint(x0, w)
            if self.picker is not None:
                self._draw_picker()

    def _draw_hint(self, x0, w):
        """Franja inferior: cruceta mueve; A+dir edita el campo de la celda."""
        y = self.y + dp(8)
        Color(*COLOR_HINT_BG)
        Rectangle(pos=(x0, y), size=(w, HINT_H))
        if self.picker is not None:
            hint = "lista EFECTO · arr/abj mueve · A elige · B cierra"
        elif self.cursor == self.SAVE_ROW:
            hint = "A: guardar en la canción"
        else:
            hint = ("cruceta: knob / columna · "
                    + COL_HINTS[self.col])
        self._text_left(x0 + dp(12), y, w - dp(24), hint, COLOR_ACCENT,
                        h=HINT_H, font_size=FONT_SMALL)

    def _draw_picker(self):
        """Overlay centrado con EFFECT_CYCLE (off + presets); el cursor es
        `self.picker`. Se dibuja dentro del canvas de _redraw."""
        n = len(EFFECT_CYCLE)
        pw = dp(460)
        ph = (n + 2) * PICK_ROW_H           # título + filas + hint
        px = self.x + (self.width - pw) / 2
        py = self.y + (self.height - ph) / 2
        # oscurece el fondo
        Color(0, 0, 0, 0.55)
        Rectangle(pos=self.pos, size=self.size)
        # panel con borde de acento
        Color(*COLOR_ROW_CURSOR)
        Rectangle(pos=(px, py), size=(pw, ph))
        Color(*COLOR_ACCENT)
        RoundedRectangle(pos=(px + dp(3), py + dp(3)),
                         size=(pw - dp(6), ph - dp(6)), radius=[dp(8)])
        Color(*COLOR_ROW_CURSOR)
        RoundedRectangle(pos=(px + dp(7), py + dp(7)),
                         size=(pw - dp(14), ph - dp(14)), radius=[dp(6)])
        self._text_center(px, py + (n + 1) * PICK_ROW_H, pw, "EFECTO",
                          COLOR_ACCENT, h=PICK_ROW_H)
        for i, nombre in enumerate(EFFECT_CYCLE):
            # índice 0 arriba: la lista se lee de arriba a abajo y
            # ARRIBA/ABAJO mueven el cursor en la dirección esperada
            y = py + (n - i) * PICK_ROW_H
            if i == self.picker:
                Color(*COLOR_ROW_CURSOR)
                Rectangle(pos=(px + dp(10), y + dp(3)),
                          size=(pw - dp(20), PICK_ROW_H - dp(6)))
                Color(*COLOR_ACCENT)
                RoundedRectangle(pos=(px + dp(12), y + dp(5)),
                                 size=(pw - dp(24), PICK_ROW_H - dp(10)),
                                 radius=[dp(4)])
                color = COLOR_ACCENT
            else:
                color = COLOR_NAME
            self._text_left(px + dp(40), y, pw - dp(80), nombre, color,
                            h=PICK_ROW_H, font_size=FONT)
        self._text_center(px, py, pw, "A: elegir · B: cancelar", COLOR_HINT,
                          h=PICK_ROW_H, font_size=FONT_SMALL)
