"""Pantalla PHRASE: los 16 steps del phrase del step de CHAIN donde estás.

Como LGPT, por step: NOTA · INSTRUMENTO · FX1 (cmd+param) · FX2 (cmd+param).
La phrase es la del canal (track) en el step de la chain desde el que se entró.
Cursor: arr/abj = step, izq/dcha = campo (nota, instr, fx1cmd, fx1prm, fx2cmd,
fx2prm). A+dir edita el campo; A copia/pega/valor por defecto; B borra el campo.
Editar un hueco crea la chain y la phrase (estilo Piggy), reutilizando
`PhraseView` del modelo. Portapapeles propio (por campo).
"""

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, LEFT, RIGHT, UP
from lgpt_model import EMPTY, FX_EMPTY, PHRASE_LEN, PhraseView, note_name_to_byte
from sinte_bridge import note_byte_to_name
from theme import COLOR_ACCENT, COLOR_BG

ROW_H = dp(30)
TOP_PAD = dp(20)
LM = dp(36)
STEP_W = dp(52)
FONT = dp(17)
MAX_NOTE = 131                     # (9+2)*12 - 1

# Comandos FX que se pueden ciclar: solo los que se usan en las canciones de
# songs/ (no usamos más). Todos de 4 chars (requisito de set_fx_cmd).
FX_USED = ["VOLM", "KILL", "DLAY", "LEGA", "TABL", "STOP", "MDCC", "MDPG",
           "PTCH", "RTRG"]

# (kind, ancho_px)
COLS = [("note", dp(70)), ("instr", dp(52)),
        ("fx1cmd", dp(74)), ("fx1prm", dp(74)),
        ("fx2cmd", dp(74)), ("fx2prm", dp(74))]

COLOR_NOTE = (0.87, 0.89, 0.92, 1)
COLOR_INSTR = (0.55, 0.82, 0.55, 1)
COLOR_FX1 = (0.85, 0.58, 0.75, 1)
COLOR_FX2 = (0.65, 0.55, 0.85, 1)
COLOR_EMPTY = (0.30, 0.31, 0.36, 1)
COLOR_LINENUM = (0.45, 0.46, 0.52, 1)
COLOR_LINENUM_CUR = (1.0, 0.85, 0.40, 1)
COLOR_BEAT = (0.13, 0.14, 0.18, 1)
COLOR_ROW_CURSOR = (0.19, 0.21, 0.27, 1)
COLOR_PLAY = (0.16, 0.42, 0.24, 1)

_COL_COLOR = {"note": COLOR_NOTE, "instr": COLOR_INSTR,
              "fx1cmd": COLOR_FX1, "fx1prm": COLOR_FX1,
              "fx2cmd": COLOR_FX2, "fx2prm": COLOR_FX2}
_KIND = {"note": "note", "instr": "instr", "fx1cmd": "cmd", "fx2cmd": "cmd",
         "fx1prm": "prm", "fx2prm": "prm"}
_WHICH = {"fx1cmd": 1, "fx1prm": 1, "fx2cmd": 2, "fx2prm": 2}


class PhraseGrid(Widget):
    def __init__(self, on_change=None, fx_commands=None, on_nav=None, **kw):
        super().__init__(**kw)
        # comandos FX que se pueden ciclar (solo los usados en las canciones)
        self.fx_commands = list(fx_commands) if fx_commands else list(FX_USED)
        self.on_nav = on_nav           # refresca la cabecera al mover el cursor
        self.project = None
        self.pv = None
        self.track = 0
        self.cursor_step = 0
        self.cursor_col = 0            # índice en COLS
        self.octave = 4
        self.clipboard = None          # (kind, value) — portapapeles propio
        self.play_step = None
        self.on_change = on_change
        self._tex = {}
        self.bind(pos=self._redraw, size=self._redraw)

    # -- contexto -------------------------------------------------------
    def set_context(self, project, song_row, track, chain_step):
        self.project = project
        self.pv = PhraseView(project, song_row, chain_step)
        self.track = track
        self.cursor_step = 0
        self.cursor_col = 0
        self.clipboard = None
        self._redraw()

    def phrase_label(self):
        p = self.pv.phrase_of(self.track) if self.pv else None
        return f"{p:02X}" if p is not None else "--"

    def set_play(self, step):
        if step != self.play_step:
            self.play_step = step
            self._redraw()

    # -- valores crudos por campo --------------------------------------
    def _note(self, step):
        i = self.pv._index(step, self.track)
        if i is None or self.project.notes[i] == EMPTY:
            return None
        return self.project.notes[i]

    def _instr(self, step):
        i = self.pv._index(step, self.track)
        if i is None or self.project.instruments[i] == EMPTY:
            return None
        return self.project.instruments[i]

    def _cmd(self, step, which):
        c = self.pv.fx_cmd_at(step, self.track, which)
        return None if c == FX_EMPTY else c

    def _prm(self, step, which):
        if self._cmd(step, which) is None:
            return None
        return self.pv.fx_param_at(step, self.track, which)

    def _get_raw(self, step, col):
        kind = COLS[col][0]
        if kind == "note":
            return self._note(step)
        if kind == "instr":
            return self._instr(step)
        if kind.endswith("cmd"):
            return self._cmd(step, _WHICH[kind])
        return self._prm(step, _WHICH[kind])

    def _set_raw(self, step, col, value):
        kind = COLS[col][0]
        if kind == "note":
            self.pv.set_note(step, self.track, value)
        elif kind == "instr":
            self.pv.set_instr(step, self.track, value)
        elif kind.endswith("cmd"):
            which = _WHICH[kind]
            if value is None:
                self.pv.clear_fx(step, self.track, which)
            else:
                self.pv.set_fx_cmd(step, self.track, which, value)
        else:
            which = _WHICH[kind]
            self.pv.set_fx_param(step, self.track, which,
                                 0 if value is None else value)

    # -- navegación / edición ------------------------------------------
    def move(self, button):
        if button == UP:
            self.cursor_step = max(0, self.cursor_step - 1)
        elif button == DOWN:
            self.cursor_step = min(PHRASE_LEN - 1, self.cursor_step + 1)
        elif button == LEFT:
            self.cursor_col = max(0, self.cursor_col - 1)
        elif button == RIGHT:
            self.cursor_col = min(len(COLS) - 1, self.cursor_col + 1)
        if self.on_nav:
            self.on_nav()              # actualiza cabecera (nombre del sample)
        self._redraw()

    def current_sample_name(self):
        """Nombre del wav del instrumento del step del cursor (o None)."""
        if self.pv is None:
            return None
        iid = self._instr(self.cursor_step)
        if iid is None:
            return None
        data = self.project.instrument_bank.get(iid)
        if not data:
            return None
        return data["params"].get("sample")

    def edit(self, button):
        step, col = self.cursor_step, self.cursor_col
        kind = COLS[col][0]
        big = 12 if kind == "note" else 0x10
        if button in (LEFT, RIGHT):
            delta = 1 if button == RIGHT else -1
        else:
            delta = big if button == UP else -big
        if kind == "note":
            self._edit_note(step, delta)
        elif kind == "instr":
            cur = self._instr(step)
            if cur is None:
                if delta > 0:
                    self.pv.set_instr(step, self.track, 0)
            else:
                self.pv.set_instr(step, self.track, max(0, min(0xFE, cur + delta)))
        elif kind.endswith("cmd"):
            self._edit_cmd(step, _WHICH[kind], delta)
        else:
            which = _WHICH[kind]
            cur = self.pv.fx_param_at(step, self.track, which)
            self.pv.set_fx_param(step, self.track, which,
                                 max(0, min(0xFFFF, cur + delta)))
        self._changed()

    def _edit_note(self, step, delta):
        cur = self._note(step)
        if cur is None:
            if delta > 0:
                self.pv.set_note(step, self.track,
                                 note_name_to_byte(f"C-{self.octave}"))
                if self._instr(step) is None:
                    self.pv.set_instr(step, self.track, 0)
        else:
            self.pv.set_note(step, self.track, max(0, min(MAX_NOTE, cur + delta)))

    def _edit_cmd(self, step, which, delta):
        cur = self._cmd(step, which)
        cmds = self.fx_commands
        d = 1 if delta > 0 else -1              # los comandos ciclan de 1 en 1
        if cur is None or cur not in cmds:
            if delta > 0:
                self.pv.set_fx_cmd(step, self.track, which, cmds[0])
        else:
            self.pv.set_fx_cmd(step, self.track, which,
                               cmds[(cmds.index(cur) + d) % len(cmds)])

    def delete(self):
        self._set_raw(self.cursor_step, self.cursor_col, None)
        self._changed()

    # -- copiar / pegar por campo --------------------------------------
    def a_tap(self):
        step, col = self.cursor_step, self.cursor_col
        val = self._get_raw(step, col)
        kind = _KIND[COLS[col][0]]
        if val is not None:
            self.clipboard = (kind, val)          # copiar
            self._redraw()
        elif self.clipboard is not None and self.clipboard[0] == kind:
            self._set_raw(step, col, self.clipboard[1])   # pegar
            self._changed()
        else:
            self._set_default(step, col)          # valor por defecto
            self._changed()

    def paste_field(self):
        col = self.cursor_col
        if self.clipboard is not None and self.clipboard[0] == _KIND[COLS[col][0]]:
            self._set_raw(self.cursor_step, col, self.clipboard[1])
            self._changed()

    def _set_default(self, step, col):
        kind = COLS[col][0]
        if kind == "note":
            self.pv.set_note(step, self.track,
                             note_name_to_byte(f"C-{self.octave}"))
        elif kind == "instr":
            self.pv.set_instr(step, self.track, 0)
        elif kind.endswith("cmd"):
            self.pv.set_fx_cmd(step, self.track, _WHICH[kind],
                               self.fx_commands[0])
        else:
            self.pv.set_fx_param(step, self.track, _WHICH[kind], 0)

    def _changed(self):
        if self.on_change:
            self.on_change()
        self._redraw()

    # -- dibujo ---------------------------------------------------------
    def _field_text(self, step, col):
        kind = COLS[col][0]
        raw = self._get_raw(step, col)
        if kind == "note":
            return note_byte_to_name(raw) if raw is not None else "---"
        if kind == "instr":
            return f"{raw:02X}" if raw is not None else ".."
        if kind.endswith("cmd"):
            return raw.strip().ljust(4, " ") if raw is not None else "----"
        return f"{raw:04X}" if raw is not None else "...."

    def _texture(self, text):
        tex = self._tex.get(text)
        if tex is None:
            lbl = CoreLabel(text=text, font_size=FONT, bold=True)
            lbl.refresh()
            tex = lbl.texture
            self._tex[text] = tex
        return tex

    def _text(self, x, y, w, text, color):
        tex = self._texture(text)
        tw, th = tex.size
        Color(*color)
        Rectangle(texture=tex, size=(tw, th),
                  pos=(x + (w - tw) / 2, y + (ROW_H - th) / 2))

    def _redraw(self, *_):
        self.canvas.clear()
        if self.pv is None:
            return
        block_w = STEP_W + dp(8) + sum(w for _k, w in COLS)   # centrar bloque
        x_step = self.x + max(dp(8), (self.width - block_w) / 2)
        xs = []
        x = x_step + STEP_W + dp(8)
        for _kind, w in COLS:
            xs.append(x)
            x += w
        with self.canvas:
            Color(*COLOR_BG)
            Rectangle(pos=self.pos, size=self.size)
            for step in range(PHRASE_LEN):
                y = self.y + self.height - TOP_PAD - (step + 1) * ROW_H
                if step == self.cursor_step:
                    Color(*COLOR_ROW_CURSOR)
                    Rectangle(pos=(self.x, y), size=(self.width, ROW_H))
                elif step == self.play_step:
                    Color(*COLOR_PLAY)
                    Rectangle(pos=(x_step, y), size=(x - x_step, ROW_H))
                elif step % 4 == 0:
                    Color(*COLOR_BEAT)
                    Rectangle(pos=(x_step, y), size=(x - x_step, ROW_H))
                num_c = (COLOR_LINENUM_CUR if step == self.cursor_step
                         else COLOR_LINENUM)
                self._text(x_step, y, STEP_W, f"{step:02X}", num_c)
                for col, (kind, w) in enumerate(COLS):
                    cx = xs[col]
                    raw = self._get_raw(step, col)
                    text = self._field_text(step, col)
                    color = _COL_COLOR[kind] if raw is not None else COLOR_EMPTY
                    if step == self.cursor_step and col == self.cursor_col:
                        Color(*COLOR_ACCENT)
                        RoundedRectangle(pos=(cx + dp(2), y + dp(3)),
                                         size=(w - dp(4), ROW_H - dp(6)),
                                         radius=[dp(6)])
                        color = COLOR_BG
                    self._text(cx, y, w, text, color)
