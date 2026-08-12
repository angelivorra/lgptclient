"""Editor de phrases estilo LGPT/Piggy, dibujado en canvas.

Un solo widget sin hijos para que siga siendo rápido. Navegación: flechas,
Tab/Shift-Tab (canal), Home/End. Táctil: tap = mover cursor, arrastre =
scroll suave por píxeles con inercia, rueda de ratón = scroll. Las columnas
se estiran para llenar el ancho cuando caben los 8 canales; si no, hay
scroll horizontal.

El modelo es cualquier objeto con `length`, `num_tracks`, `cell(row, track)`
y opcionalmente `track_label(track)` (ver lgpt_model.PhraseView).
`play_rows` es un conjunto de filas a resaltar como playhead.

Eventos: `on_enter_cell` se dispara cuando se hace tap sobre la celda que
ya estaba seleccionada (la app abre ahí el popup de la celda).
"""

from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle, ScissorPop, ScissorPush
from kivy.metrics import dp
from kivy.properties import NumericProperty, ObjectProperty
from kivy.uix.widget import Widget

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
COLOR_BG = (0.10, 0.10, 0.12, 1)
COLOR_ROW_BEAT = (0.14, 0.15, 0.18, 1)
COLOR_ROW_BAR = (0.17, 0.19, 0.24, 1)
COLOR_ROW_CURSOR = (0.20, 0.22, 0.28, 1)
COLOR_ROW_PLAY = (0.13, 0.24, 0.16, 1)
COLOR_HEADER_BG = (0.06, 0.06, 0.08, 1)
COLOR_HEADER_TEXT = (0.85, 0.65, 0.25, 1)
COLOR_LINE_NUM = (0.45, 0.45, 0.50, 1)
COLOR_LINE_NUM_CURSOR = (1.0, 0.85, 0.40, 1)
COLOR_CELL_EMPTY = (0.32, 0.32, 0.36, 1)
COLOR_TRACK_SEP = (0.28, 0.30, 0.36, 1)

CELL_COLORS = {
    "note": (0.87, 0.89, 0.92, 1),
    "instr": (0.55, 0.82, 0.55, 1),
    "fx1": (0.85, 0.58, 0.75, 1),
    "fx2": (0.65, 0.55, 0.85, 1),
}
COLOR_CURSOR_BG = (0.95, 0.75, 0.20, 1)
COLOR_TEXT_ON_CURSOR = (0.08, 0.08, 0.10, 1)

FONT = "RobotoMono-Regular"
FONT_SIZE = dp(14)

# Columns inside each track: (cell field, width in characters)
TRACK_COLUMNS = [
    ("note", 4),
    ("instr", 3),
    ("fx1", 9),
    ("fx2", 9),
]

EMPTY_TEXT = {"note": "---", "instr": "..", "fx1": "---- ....", "fx2": "---- ...."}

KINETIC_FRICTION = 0.94        # per-frame velocity decay while flinging
KINETIC_MIN_SPEED = dp(20)     # px/s below which the fling stops


def _measure_char() -> tuple[float, float]:
    lbl = CoreLabel(text="0", font_name=FONT, font_size=FONT_SIZE)
    lbl.refresh()
    return lbl.texture.size


class PatternEditor(Widget):
    pattern = ObjectProperty(None, allownone=True)
    lines_per_beat = NumericProperty(4)
    cursor_row = NumericProperty(0)
    cursor_track = NumericProperty(0)
    cursor_col = NumericProperty(0)
    scroll_x = NumericProperty(0)   # pixels scrolled horizontally
    scroll_y = NumericProperty(0)   # pixels scrolled vertically

    def __init__(self, **kwargs):
        self.register_event_type("on_enter_cell")
        super().__init__(**kwargs)
        self._char_w, self._char_h = _measure_char()
        self._row_h = self._char_h + dp(10)
        self._header_h = dp(26)
        self._line_num_w = self._char_w * 3 + dp(14)
        self._track_w = self._char_w * sum(w for _, w in TRACK_COLUMNS) + dp(14)
        self._touch_start = (0, 0)
        self._touch_dragged = False
        self._velocity = [0.0, 0.0]
        self._last_move_time = 0.0
        self.play_rows = frozenset()  # filas resaltadas como playhead
        self.selection = None  # (r0, t0, r1, t1) o None
        for prop in ("pattern", "cursor_row", "cursor_track", "cursor_col",
                     "scroll_x", "scroll_y", "size", "pos"):
            self.bind(**{prop: lambda *a: self.redraw()})

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------
    def _track_stride(self) -> float:
        """Horizontal space per track: stretches to fill the window when all
        tracks fit; otherwise the natural width and horizontal scrolling."""
        avail = self.width - dp(8) - self._line_num_w
        natural = self.pattern.num_tracks * self._track_w
        return avail / self.pattern.num_tracks if avail > natural else self._track_w

    def _max_scroll_x(self) -> float:
        avail = self.width - dp(8) - self._line_num_w
        return max(0, self.pattern.num_tracks * self._track_stride() - avail)

    def _max_scroll_y(self) -> float:
        avail = self.height - self._header_h
        return max(0, self.pattern.length * self._row_h - avail)

    def _clamp_scroll(self):
        self.scroll_x = max(0.0, min(self._max_scroll_x(), self.scroll_x))
        self.scroll_y = max(0.0, min(self._max_scroll_y(), self.scroll_y))

    def _geometry(self) -> tuple[float, float]:
        """Returns (x0, top_y); the grid is always left-aligned."""
        return self.x + dp(4), self.top - self._header_h

    # ------------------------------------------------------------------
    # Navigation (called by the app's keyboard handler)
    # ------------------------------------------------------------------
    def move(self, drow=0, dcol=0, dtrack=0):
        if dcol:
            n = self.cursor_col + dcol
            if n < 0:
                dtrack, n = -1, len(TRACK_COLUMNS) - 1
            elif n >= len(TRACK_COLUMNS):
                dtrack, n = 1, 0
            self.cursor_col = n
        if dtrack:
            t = max(0, min(self.pattern.num_tracks - 1, self.cursor_track + dtrack))
            if t != self.cursor_track:
                self.cursor_track = t
                self.cursor_col = 0 if dtrack > 0 else len(TRACK_COLUMNS) - 1
        if drow:
            self.cursor_row = max(0, min(self.pattern.length - 1,
                                         self.cursor_row + drow))
        self._ensure_cursor_visible()

    def _ensure_cursor_visible(self):
        row_top = self.cursor_row * self._row_h
        view_h = self.height - self._header_h
        if row_top < self.scroll_y:
            self.scroll_y = row_top
        elif row_top + self._row_h > self.scroll_y + view_h:
            self.scroll_y = row_top + self._row_h - view_h

        track_left = self.cursor_track * self._track_stride()
        view_w = self.width - dp(8) - self._line_num_w
        if track_left < self.scroll_x:
            self.scroll_x = track_left
        elif track_left + self._track_stride() > self.scroll_x + view_w:
            self.scroll_x = track_left + self._track_stride() - view_w
        self._clamp_scroll()

    # ------------------------------------------------------------------
    # Touch: tap = move cursor, drag = smooth scroll + kinetic fling
    # ------------------------------------------------------------------
    def on_touch_down(self, touch):
        if self.pattern is None or not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        if touch.is_mouse_scrolling:
            vstep = self._row_h * 3
            hstep = self._track_stride()
            if touch.button == "scrollup":
                self.scroll_y -= vstep
            elif touch.button == "scrolldown":
                self.scroll_y += vstep
            elif touch.button == "scrollleft":
                self.scroll_x -= hstep
            elif touch.button == "scrollright":
                self.scroll_x += hstep
            self._clamp_scroll()
            return True
        touch.grab(self)
        Clock.unschedule(self._kinetic_step)
        self._touch_start = touch.pos
        self._touch_dragged = False
        self._velocity = [0.0, 0.0]
        self._last_move_time = touch.time_start
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return super().on_touch_move(touch)
        if not self._touch_dragged:
            sx, sy = self._touch_start
            if abs(touch.x - sx) + abs(touch.y - sy) > dp(10):
                self._touch_dragged = True
        if self._touch_dragged:
            # Content follows the finger.
            self.scroll_x -= touch.dx
            self.scroll_y += touch.dy
            self._clamp_scroll()
            dt = max(1e-4, touch.time_update - self._last_move_time)
            self._last_move_time = touch.time_update
            alpha = 0.3  # smooth the velocity estimate a bit
            self._velocity[0] = ((1 - alpha) * self._velocity[0]
                                 + alpha * (touch.dx / dt))
            self._velocity[1] = ((1 - alpha) * self._velocity[1]
                                 + alpha * (touch.dy / dt))
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return super().on_touch_up(touch)
        touch.ungrab(self)
        if not self._touch_dragged:
            x0, top_y = self._geometry()
            if touch.y > top_y:
                # tap en la cabecera: saltar el cursor a ese canal
                track = self._track_from_x(touch.x)
                if track is not None:
                    self.cursor_track = track
                    self.cursor_col = 0
                    self._ensure_cursor_visible()
            else:
                row, track = self._row_track_from_pos(*touch.pos)
                already = (row == self.cursor_row
                           and track == self.cursor_track)
                self._cursor_from_pos(*touch.pos)
                if already:
                    # segundo tap sobre la celda seleccionada = entrar
                    self.dispatch("on_enter_cell")
        elif max(abs(self._velocity[0]), abs(self._velocity[1])) > KINETIC_MIN_SPEED:
            Clock.schedule_interval(self._kinetic_step, 1 / 60)
        return True

    def on_enter_cell(self):
        """Hook: segundo tap sobre la celda seleccionada."""

    def _kinetic_step(self, dt):
        vx, vy = self._velocity
        self.scroll_x -= vx * dt
        self.scroll_y += vy * dt
        self._clamp_scroll()
        # Kill the component pressing against an edge so it stops bouncing.
        if self.scroll_x in (0.0, self._max_scroll_x()):
            vx = 0.0
        if self.scroll_y in (0.0, self._max_scroll_y()):
            vy = 0.0
        vx *= KINETIC_FRICTION
        vy *= KINETIC_FRICTION
        self._velocity = [vx, vy]
        if max(abs(vx), abs(vy)) <= KINETIC_MIN_SPEED:
            return False  # unschedule
        return True

    def _track_from_x(self, x) -> int | None:
        """Canal bajo la coordenada x, o None si cae en el margen/números."""
        if self.pattern is None:
            return None
        x0, _top_y = self._geometry()
        tx = x - x0 - self._line_num_w - dp(6) + self.scroll_x
        if tx < 0:
            return None
        return max(0, min(self.pattern.num_tracks - 1,
                          int(tx // self._track_stride())))

    def _row_track_from_pos(self, x, y) -> tuple[int, int]:
        """Fila y canal bajo el punto, ya clampeados a la parrilla."""
        pattern = self.pattern
        x0, top_y = self._geometry()
        row = int((self.scroll_y + top_y - y) // self._row_h)
        row = max(0, min(pattern.length - 1, row))
        track = self._track_from_x(x)
        return row, (self.cursor_track if track is None else track)

    def _cursor_from_pos(self, x, y):
        pattern = self.pattern
        x0, top_y = self._geometry()

        row = int((self.scroll_y + top_y - y) // self._row_h)
        self.cursor_row = max(0, min(pattern.length - 1, row))

        tx = x - x0 - self._line_num_w - dp(6) + self.scroll_x
        if tx < 0:
            return  # tap on the line-number gutter: only move the row
        stride = self._track_stride()
        self.cursor_track = max(0, min(pattern.num_tracks - 1,
                                       int(tx // stride)))

        col_x = tx % stride
        acc = 0.0
        col = len(TRACK_COLUMNS) - 1
        for c, (_key, w) in enumerate(TRACK_COLUMNS):
            acc += self._char_w * w
            if col_x < acc:
                col = c
                break
        self.cursor_col = col

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def redraw(self, *args):
        if self.pattern is None:
            return
        pattern = self.pattern
        cw, row_h = self._char_w, self._row_h
        header_h, line_num_w = self._header_h, self._line_num_w
        track_w = self._track_stride()
        x0, top_y = self._geometry()

        first_row = int(self.scroll_y // row_h)
        frac_y = self.scroll_y % row_h
        first_track = int(self.scroll_x // track_w)
        frac_x = self.scroll_x % track_w

        content_right = min(self.right - dp(4),
                            x0 + line_num_w + track_w * pattern.num_tracks)
        tracks_x = x0 + line_num_w + dp(6) - frac_x
        grid_bottom = self.y

        track_label = getattr(pattern, "track_label", None)

        self.canvas.clear()
        with self.canvas:
            Color(*COLOR_BG)
            Rectangle(pos=self.pos, size=self.size)

            # --- rows --------------------------------------------------
            i = 0
            while True:
                row = first_row + i
                y = top_y + frac_y - (i + 1) * row_h
                if y + row_h <= grid_bottom or row >= pattern.length:
                    break
                if row == self.cursor_row:
                    bg = COLOR_ROW_CURSOR
                elif row in self.play_rows:
                    bg = COLOR_ROW_PLAY
                elif row % 16 == 0:
                    bg = COLOR_ROW_BAR
                elif row % self.lines_per_beat == 0:
                    bg = COLOR_ROW_BEAT
                else:
                    bg = None
                if bg:
                    Color(*bg)
                    Rectangle(pos=(x0, y), size=(content_right - x0, row_h))

                num_color = (COLOR_LINE_NUM_CURSOR if row == self.cursor_row
                             else COLOR_LINE_NUM)
                self._text(x0 + dp(6), y, f"{row:02d}", num_color)

                # --- cells (clipped so partial tracks cut cleanly) -----
                ScissorPush(x=int(x0 + line_num_w), y=int(grid_bottom),
                            width=int(content_right - x0 - line_num_w),
                            height=int(top_y - grid_bottom))
                x = tracks_x
                for t in range(first_track, pattern.num_tracks):
                    if x >= content_right:
                        break
                    Color(*COLOR_TRACK_SEP)
                    Line(points=[x - dp(3), grid_bottom, x - dp(3), top_y])
                    cell = pattern.cell(row, t)
                    cx = x
                    for c, (key, w) in enumerate(TRACK_COLUMNS):
                        value = getattr(cell, key)
                        text = value if value else EMPTY_TEXT[key]
                        on_cursor = (row == self.cursor_row
                                     and t == self.cursor_track
                                     and c == self.cursor_col)
                        if on_cursor:
                            Color(*COLOR_CURSOR_BG)
                            Rectangle(pos=(cx, y),
                                      size=(cw * (w - 0.2), row_h))
                            color = COLOR_TEXT_ON_CURSOR
                        else:
                            color = CELL_COLORS[key] if value else COLOR_CELL_EMPTY
                        self._text(cx, y, text, color)
                        cx += cw * w
                    x += track_w
                ScissorPop()
                i += 1

            # --- selección (bloque del portapapeles, estilo LGPT) -------
            if self.selection:
                r0, t0, r1, t1 = self.selection
                sx = tracks_x + (t0 - first_track) * track_w
                ex = tracks_x + (t1 - first_track + 1) * track_w
                sy_top = top_y + frac_y - (r0 - first_row) * row_h
                sy_bot = sy_top - (r1 - r0 + 1) * row_h
                ScissorPush(x=int(x0 + line_num_w), y=int(grid_bottom),
                            width=int(content_right - x0 - line_num_w),
                            height=int(top_y - grid_bottom))
                Color(0.95, 0.75, 0.20, 0.16)
                Rectangle(pos=(sx, sy_bot), size=(ex - sx, sy_top - sy_bot))
                Color(*COLOR_CURSOR_BG)
                Line(rectangle=(sx, sy_bot, ex - sx, sy_top - sy_bot),
                     width=1.2)
                ScissorPop()

            # --- header (drawn last: covers rows peeking above top_y) ---
            Color(*COLOR_HEADER_BG)
            Rectangle(pos=(x0, top_y), size=(content_right - x0, header_h))
            ScissorPush(x=int(x0 + line_num_w), y=int(top_y),
                        width=int(content_right - x0 - line_num_w),
                        height=int(header_h))
            x = tracks_x
            for t in range(first_track, pattern.num_tracks):
                if x >= content_right:
                    break
                label = (track_label(t) if track_label
                         else f"Track {t + 1:02d}")
                self._text(x, top_y, label, COLOR_HEADER_TEXT, header=True)
                x += track_w
            ScissorPop()

    def _text(self, x, y, text, color, header=False):
        lbl = CoreLabel(text=text, font_name=FONT, font_size=FONT_SIZE,
                        color=color)
        lbl.refresh()
        tex = lbl.texture
        if header:
            ty = self.top - self._header_h + (self._header_h - tex.height) / 2
        else:
            ty = y + (self._row_h - tex.height) / 2
        Color(1, 1, 1, 1)
        Rectangle(texture=tex, pos=(x, ty), size=tex.size)
