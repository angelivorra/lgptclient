"""Editor de canción: contenedor de las pantallas estilo LGPT.

Navegación entre pantallas con L+dpad (Ctrl+flechas en PC) según `navmap`.
La cabecera muestra a la izquierda el nombre de la pantalla + la canción y a
la derecha la tira fija S C P I con la columna activa resaltada; el color indica
la altura: oro = fila media, cian = fila de arriba (PROJECT/GROOVE), magenta =
fila de abajo (TABLE), mostrando en esa celda su letra (P/G/T).

SONG ya está implementada (rejilla 256×8). El resto son placeholders que se
irán rellenando una a una. Los botones del cursor/edición se delegan a la vista
activa.
"""

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label

from kivy.uix.screenmanager import Screen

from navmap import SCREENS, neighbor
from robots import ROBOT_TRACK
from screens.chain_view import ChainGrid
from screens.config_view import ConfigMenu
from screens.groove_view import GrooveGrid
from screens.instrument_view import InstrumentMenu
from screens.pads_view import PadsGrid
from screens.phrase_view import PhraseGrid
from screens.pots_view import PotsGrid
from screens.project_view import ProjectMenu
from screens.song_view import SongGrid
from screens.table_view import TableGrid
from theme import (COLOR_ACCENT, COLOR_BAR_BG, COLOR_BG, COLOR_BORDER,
                   COLOR_ERROR, COLOR_OK)


BAR_H = dp(52)
NAV_CELL_W = dp(38)

NAV_COLUMNS = ["D", "S", "C", "P", "I"]

ROW_COLORS = {
    1: COLOR_ACCENT,            # fila media (S C P I)
    0: (0.35, 0.75, 0.85, 1),   # fila de arriba (PROJECT, GROOVE) -> cian
    2: (0.82, 0.55, 0.88, 1),   # fila de abajo (TABLE) -> magenta
}


class _NavCell(Label):
    def __init__(self, **kw):
        super().__init__(bold=True, font_size=dp(20), halign="center",
                         valign="middle", size_hint_x=None, width=NAV_CELL_W,
                         **kw)
        with self.canvas.before:
            self._c = Color(0, 0, 0, 0)
            self._r = RoundedRectangle(radius=[dp(6)])
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *_):
        self.text_size = self.size
        self._r.pos = (self.x + dp(2), self.y + dp(6))
        self._r.size = (self.width - dp(4), self.height - dp(12))

    def set(self, letter, bg):
        self.text = letter
        if bg is not None:
            self._c.rgba = bg
            self.color = COLOR_BG
        else:
            self._c.rgba = (0, 0, 0, 0)
            self.color = COLOR_BORDER


class EditorScreen(Screen):
    def __init__(self, on_change=None, on_action=None, on_pick_screen=None,
                 ayuda_dir=None, **kw):
        super().__init__(**kw)
        self.current = "song"
        self.song_name = ""
        self.project = None
        self.config = {}          # configuración global (interfaces MIDI)
        self._config_cb = None    # callback al cambiar la config


        outer = FloatLayout()
        root = BoxLayout(orientation="vertical")
        with root.canvas.before:
            Color(*COLOR_BG)
            self._bg = Rectangle()
        root.bind(pos=self._sync_bg, size=self._sync_bg)

        # --- cabecera ------------------------------------------------
        bar = BoxLayout(size_hint=(1, None), height=BAR_H,
                        padding=(dp(16), 0), spacing=dp(4))
        with bar.canvas.before:
            Color(*COLOR_BAR_BG)
            bar._bg = Rectangle()
        bar.bind(pos=lambda w, *_: setattr(w._bg, "pos", w.pos),
                 size=lambda w, *_: setattr(w._bg, "size", w.size))

        self.header = Label(text="", bold=True, color=COLOR_ACCENT,
                            font_size=dp(22), halign="left", valign="middle")
        self.header.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
        bar.add_widget(self.header)

        # indicador de pintado MIDI en vivo (R2+START); invisible al apagarlo
        self.live_ind = Label(text="", bold=True, font_name="Icons",
                              font_size=dp(22),
                              color=(0, 0, 0, 0), size_hint_x=None,
                              width=dp(52), halign="center", valign="middle")
        self.live_ind.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
        with self.live_ind.canvas.before:
            self._live_chip_color = Color(0.95, 0.45, 0.40, 0.16)
            self._live_chip = RoundedRectangle(radius=[dp(6)])
        self.live_ind.bind(pos=self._sync_live_chip, size=self._sync_live_chip)
        bar.add_widget(self.live_ind)

        # indicador de reproducción (▶ + temporizador); invisible al parar
        self.play_ind = Label(text="", bold=True, font_name="Icons",
                              font_size=dp(22), color=COLOR_OK,
                              size_hint_x=None, width=dp(120),
                              halign="center", valign="middle")
        self.play_ind.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
        with self.play_ind.canvas.before:
            self._play_chip_color = Color(0.45, 0.85, 0.45, 0.14)
            self._play_chip = RoundedRectangle(radius=[dp(6)])
        self.play_ind.bind(pos=self._sync_play_chip, size=self._sync_play_chip)
        bar.add_widget(self.play_ind)

        self.nav_cells = []
        for letter in NAV_COLUMNS:
            cell = _NavCell(text=letter)
            self.nav_cells.append(cell)
            bar.add_widget(cell)
        root.add_widget(bar)

        # --- área de contenido --------------------------------------
        self.content = FloatLayout()
        root.add_widget(self.content)

        self._dirty_cb = on_change
        self.pots_grid = PotsGrid(size_hint=(1, 1),
                                  pos_hint={"x": 0, "y": 0})
        self.pads_grid = PadsGrid(size_hint=(1, 1),
                                  pos_hint={"x": 0, "y": 0})
        self.song_grid = SongGrid(on_change=self._grid_changed,
                                  size_hint=(1, 1),
                                  pos_hint={"x": 0, "y": 0})
        self.chain_grid = ChainGrid(on_change=self._grid_changed,
                                    size_hint=(1, 1),
                                    pos_hint={"x": 0, "y": 0})
        self.phrase_grid = PhraseGrid(on_change=self._grid_changed,
                                      on_nav=self.refresh_header,
                                      on_pick_screen=on_pick_screen,
                                      ayuda_dir=ayuda_dir,
                                      size_hint=(1, 1),
                                      pos_hint={"x": 0, "y": 0})
        self.groove_grid = GrooveGrid(on_change=self._grid_changed,
                                      on_nav=self.refresh_header,
                                      size_hint=(1, 1),
                                      pos_hint={"x": 0, "y": 0})
        self.table_grid = TableGrid(on_change=self._grid_changed,
                                    size_hint=(1, 1),
                                    pos_hint={"x": 0, "y": 0})
        self.instrument_menu = InstrumentMenu(on_change=self._grid_changed,
                                              on_nav=self.refresh_header,
                                              size_hint=(1, 1),
                                              pos_hint={"x": 0, "y": 0})
        self.project_menu = ProjectMenu(on_action=on_action,
                                        on_change=self._grid_changed,
                                        size_hint=(1, 1),
                                        pos_hint={"x": 0, "y": 0})
        self.config_menu = ConfigMenu(on_change=self._config_changed,
                                      on_toast=self.toast_msg,
                                      size_hint=(1, 1),
                                      pos_hint={"x": 0, "y": 0})
        self.placeholder = Label(text="", halign="center", valign="middle",
                                 font_size=dp(40), bold=True,
                                 color=(*COLOR_BORDER[:3], 1),
                                 pos_hint={"center_x": 0.5, "center_y": 0.5})


        outer.add_widget(root)
        # toast de feedback (guardado, acciones pendientes...)
        self.toast = Label(text="", bold=True, font_size=dp(20), opacity=0,
                           color=COLOR_OK, size_hint=(1, None), height=dp(40),
                           pos_hint={"center_x": 0.5, "y": 0.04})
        outer.add_widget(self.toast)
        self.add_widget(outer)

    # -- fondos ---------------------------------------------------------
    def _sync_bg(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size

    # -- transporte de pantallas ---------------------------------------
    def enter_song(self, project, name):
        self.project = project
        self.song_name = name
        self.song_grid.set_project(project)
        self.project_menu.set_project(project)
        self.groove_grid.set_project(project)
        self.instrument_menu.set_project(project)
        self.goto("song")

    def refresh_header(self, *_):
        self.header.text = self._header_text()

    def _sync_play_chip(self, *_):
        self._play_chip.pos = (self.play_ind.x + dp(2),
                               self.play_ind.y + dp(6))
        self._play_chip.size = (self.play_ind.width - dp(4),
                                self.play_ind.height - dp(12))

    def _sync_live_chip(self, *_):
        self._live_chip.pos = (self.live_ind.x + dp(2),
                               self.live_ind.y + dp(6))
        self._live_chip.size = (self.live_ind.width - dp(4),
                                self.live_ind.height - dp(12))

    def set_midi_live(self, on):
        """Muestra el indicador '●' (pintado MIDI en vivo) en la cabecera."""
        if on:
            self.live_ind.text = "●"
            self.live_ind.color = COLOR_ERROR
            self._live_chip_color.rgba = (0.95, 0.45, 0.40, 0.16)
        else:
            self.live_ind.text = ""
            self.live_ind.color = (0, 0, 0, 0)
            self._live_chip_color.rgba = (0, 0, 0, 0)

    def set_play_indicator(self, playing, elapsed=0.0):
        """Muestra \"▶ m:ss\" en la cabecera mientras suena (vacío al parar)."""
        if playing:
            s = int(elapsed)
            if s >= 3600:
                text = f"▶ {s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
            else:
                text = f"▶ {s // 60}:{s % 60:02d}"
            self.play_ind.text = text
            self.play_ind.color = COLOR_OK
            self._play_chip_color.rgba = (0.45, 0.85, 0.45, 0.14)
        else:
            self.play_ind.text = ""
            self.play_ind.color = (0, 0, 0, 0)
            self._play_chip_color.rgba = (0, 0, 0, 0)

    def toast_msg(self, text):
        self.toast.text = text
        self.toast.opacity = 1
        Clock.unschedule(self._hide_toast)
        Clock.schedule_once(self._hide_toast, 1.6)

    def _hide_toast(self, *_):
        self.toast.opacity = 0

    def _grid_changed(self):
        if self._dirty_cb:
            self._dirty_cb()
        self.header.text = self._header_text()

    # -- configuración global (interfaces MIDI) ------------------------
    def set_config(self, cfg, on_change=None):
        """Inyecta la configuración global y el callback de persistencia."""
        self.config = cfg
        self._config_cb = on_change
        self.config_menu.set_config(cfg)

    def _config_changed(self):
        if self._config_cb:
            self._config_cb()
        self.header.text = self._header_text()

    def navigate(self, dx, dy):
        nxt = neighbor(self.current, dx, dy)
        if nxt:
            self.goto(nxt)


    def goto(self, key):
        self.current = key
        (col, row), _label, letter = SCREENS[key]
        if key == "chain":
            # la chain es la de la celda de SONG donde está el cursor. Solo se
            # re-crea el contexto si la celda ha cambiado: así, al volver de
            # PHRASE a la misma chain se conserva la posición del cursor (y la
            # selección/portapapeles) en vez de resetearla a 0.
            if (self.chain_grid.cv is None
                    or self.chain_grid.song_row != self.song_grid.cursor_row
                    or self.chain_grid.track != self.song_grid.cursor_track):
                self.chain_grid.set_context(self.project,
                                            self.song_grid.cursor_row,
                                            self.song_grid.cursor_track)

        elif key == "phrase":
            # la phrase es la del step de CHAIN (o del cursor de SONG si no
            # se pasó por CHAIN)
            if self.chain_grid.cv is not None:
                sr, tr, cs = (self.chain_grid.song_row, self.chain_grid.track,
                              self.chain_grid.cursor_step)
            else:
                sr, tr, cs = (self.song_grid.cursor_row,
                              self.song_grid.cursor_track, 0)
            self.phrase_grid.set_context(self.project, sr, tr, cs)
        elif key in ("phrase_table", "instrument_table"):
            self.table_grid.set_context(self.project, self._table_id(key))
        elif key == "instrument":
            # ir al instrumento del step de PHRASE, si venimos de ahí
            if self.phrase_grid.pv is not None:
                iid = self.phrase_grid._instr(self.phrase_grid.cursor_step)
                if iid is not None:
                    self.instrument_menu.select_instrument(iid)
        elif key == "config":
            # refresca la lista de puertos MIDI y avisa si alguna interfaz
            # guardada ya no existe (se conserva para la siguiente ejecución)
            self.config_menu.set_config(self.config)
            missing = self.config_menu._missing
            if missing:
                self.toast_msg("Interfaz MIDI guardada no disponible")
        self.header.text = self._header_text()
        self._update_nav(col, row, letter)
        self._show_content(key)


    def _table_id(self, key):
        # desde PHRASE: la tabla del comando TABL del step si lo hay
        if key == "phrase_table" and self.phrase_grid.pv is not None:
            pg = self.phrase_grid
            for which in (1, 2):
                if pg.pv.fx_cmd_at(pg.cursor_step, pg.track, which).strip() \
                        == "TABL":
                    return pg.pv.fx_param_at(pg.cursor_step, pg.track, which) \
                        & 0x7F
        return min(self.project.tables) if self.project.tables else 0

    def _header_text(self):
        label = SCREENS[self.current][1]
        if self.current == "chain":
            return f"CHAIN {self.chain_grid.chain_label()}    {self.song_name}"
        if self.current == "phrase":
            tag = "PHRASE (ROBOT)" if self.phrase_grid.track == ROBOT_TRACK \
                else "PHRASE"
            base = f"{tag} {self.phrase_grid.phrase_label()}    {self.song_name}"
            sample = self.phrase_grid.current_sample_name()
            return f"{base}    {sample}" if sample else base
        if self.current == "groove":
            return f"GROOVE {self.groove_grid.groove_label()}    {self.song_name}"
        if self.current in ("phrase_table", "instrument_table"):
            return f"TABLE {self.table_grid.table_label()}    {self.song_name}"
        if self.current == "instrument":
            return (f"INSTRUMENT {self.instrument_menu.instr_label()}"
                    f"    {self.song_name}")
        return f"{label}    {self.song_name}"

    def _show_content(self, key):
        self.content.clear_widgets()
        if key == "song":
            self.content.add_widget(self.song_grid)
            self.song_grid._redraw()
        elif key == "pots":
            self.content.add_widget(self.pots_grid)
            self.pots_grid._redraw()
        elif key == "pads":
            self.content.add_widget(self.pads_grid)
            self.pads_grid._redraw()
        elif key == "chain":
            self.content.add_widget(self.chain_grid)
            self.chain_grid._redraw()
        elif key == "phrase":
            self.content.add_widget(self.phrase_grid)
            self.phrase_grid._redraw()
        elif key == "groove":
            self.content.add_widget(self.groove_grid)
            self.groove_grid._redraw()
        elif key in ("phrase_table", "instrument_table"):
            self.content.add_widget(self.table_grid)
            self.table_grid._redraw()
        elif key == "instrument":
            self.content.add_widget(self.instrument_menu)
            self.instrument_menu._redraw()
        elif key == "project":
            self.content.add_widget(self.project_menu)
            self.project_menu._redraw()
        elif key == "config":
            self.content.add_widget(self.config_menu)
            self.config_menu._redraw()
        else:
            self.placeholder.text = f"{SCREENS[key][1]}\n(vacía)"
            self.content.add_widget(self.placeholder)


    def _update_nav(self, cur_col, cur_row, cur_letter):
        for i, cell in enumerate(self.nav_cells):
            if i == cur_col:
                cell.set(cur_letter, ROW_COLORS[cur_row])
            else:
                cell.set(NAV_COLUMNS[i], None)
