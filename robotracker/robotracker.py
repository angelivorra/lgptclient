"""ROBOTRACKER — editor/reproductor táctil de canciones LGPT.

UI Kivy (8 canales, scroll cinético, fullscreen) sobre el motor de audio de
sinte (../sinte): mismo Engine, mismo parser, mismo writer, así que lo que
se edita aquí es exactamente lo que suena en la Pi.

Pantallas estilo Piggy: SONG (256×8 chains) → CHAIN (16 steps) → PHRASE
(16 steps, notas/instr/fx). Controles LGPT (config.xml de ~/LGPT/bin):
flechas = cursor, Ctrl+←/→ = pantallas, Ctrl+↑/↓ = salto 16 filas,
A+flechas = valor ±1 / ±0x10 (octava en notas), A en vacío = pegar o
insertar 00/nota, A en valor = copiar celda, A+S = cortar, Ctrl+S =
selección (flechas extienden, S copia), Esc = cancelar, Space = play,
F9 = guardar. Además: piano Z X D C V G B H N J M y Q 2 W 3 E R 5 T 6 Y 7
U (notas; la S es el botón B de LGPT), hex 0-9 b c d e f para
instr/índices, Supr borra, Insert crea chain/phrase, -/+ o F1/F2 ciclan
el valor (táctil: ✎ o −/+ en los popups), F6/F7 octava.

Ejecutar:  .venv/bin/python robotracker.py [--songs RUTA]
"""

import argparse
import time
from pathlib import Path

from kivy.config import Config

# Fallback window size when leaving fullscreen (target: Odin 2 Portal,
# 1920x1080, 16:9). Must be set before the Window is created.
Config.set("graphics", "width", "1280")
Config.set("graphics", "height", "720")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.image import Image as CoreImage
from kivy.core.text import LabelBase
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.utils import platform
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from lgpt_model import (FX_COMMANDS, FX_EMPTY, ChainView, PhraseView,
                        SongView, clip_region, cycle_cell, find_songs,
                        load_project, note_name_to_byte, nudge_cell,
                        paste_region, read_cell, used_chains, used_phrases,
                        NOTE_NAMES)
from pattern_editor import TRACK_COLUMNS, PatternEditor
from player import Player
from sinte_bridge import save_project

# Roboto (la fuente por defecto de Kivy) no tiene glifos de iconos; DejaVu
# Sans sí (▶ ■ ◀ ▮ ⬇ ✓ ✕ ♪). Va bundled para que funcione igual en Android.
LabelBase.register("Icons", str(Path(__file__).resolve().parent
                                / "fonts" / "DejaVuSans.ttf"))

COLOR_BAR_BG = (0.07, 0.07, 0.09, 1)
COLOR_BAR_TEXT = (0.75, 0.75, 0.80, 1)
COLOR_ACCENT = (0.95, 0.75, 0.20, 1)
COLOR_BTN = (0.18, 0.19, 0.23, 1)
COLOR_BTN_DOWN = (0.30, 0.32, 0.38, 1)
COLOR_BORDER = (0.36, 0.38, 0.46, 1)
COLOR_OK = (0.45, 0.85, 0.45, 1)
COLOR_ERROR = (0.95, 0.45, 0.40, 1)

ICONS_DIR = Path(__file__).resolve().parent / "icons" / "ui"

# Iconos de texto (DejaVu Sans) — para el toast
ICON_OK = "✓"        # ✓
ICON_ERROR = "✕"     # ✕

TOOLBAR_H = dp(60)

Window.clearcolor = (0.10, 0.10, 0.12, 1)
if platform not in ("android", "ios"):
    Window.fullscreen = "auto"

DEFAULT_SONGS = Path(__file__).resolve().parent.parent / "sinte" / "songs"

# Teclado-piano: codepoint -> semitono desde el Do de la octava actual
PIANO_KEYS = {
    "z": 0, "s": 1, "x": 2, "d": 3, "c": 4, "v": 5, "g": 6, "b": 7,
    "h": 8, "n": 9, "j": 10, "m": 11,
    "q": 12, "2": 13, "w": 14, "3": 15, "e": 16, "r": 17, "5": 18,
    "t": 19, "6": 20, "y": 21, "7": 22, "u": 23,
}
HEX_KEYS = {c: i for i, c in enumerate("0123456789abcdef")}

# Controles estilo LGPT (config.xml de ~/LGPT/bin, fork djdiskmachine):
# A = A, S = B, Ctrl = shoulder, Space = start, flechas = mover cursor.
# - A+flechas: valor ±1 (izq/der), ±0x10 (arr/abj; octava en notas)
# - A en celda vacía: pega el portapapeles, o inserta 00 / nota nueva
# - A en celda con valor: copia la celda
# - A+S: corta (la selección si la hay, si no la celda)
# - Ctrl+S: empieza selección (flechas la extienden), S a solas: copiarla
# - Ctrl+←/→: pantalla anterior/siguiente; Ctrl+↑/↓: salto ±16 filas
# - Esc: cancela la selección; Space: play/pausa
LGPT_A = "a"
LGPT_B = "s"


def _bar_layout(height):
    layout = BoxLayout(size_hint_y=None, height=height,
                       padding=(dp(6), 0), spacing=dp(4))
    with layout.canvas.before:
        Color(*COLOR_BAR_BG)
        layout._bg = Rectangle(pos=layout.pos, size=layout.size)
    layout.bind(pos=lambda w, *_: setattr(w._bg, "pos", w.pos),
                size=lambda w, *_: setattr(w._bg, "size", w.size))
    return layout


def _bar_label(text, width=None, bold=False, color=COLOR_BAR_TEXT):
    lbl = Label(text=text, bold=bold, color=color, font_size=dp(15),
                halign="left", valign="middle")
    if width:
        lbl.size_hint_x = None
        lbl.width = width
    lbl.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
    return lbl


class IconButton(Button):
    """Botón flat con borde redondeado e icono PNG (o solo texto)."""

    def __init__(self, text="", icon=None, width=dp(56), **kw):
        super().__init__(text=text, size_hint_x=None, width=width,
                         bold=True, font_size=dp(16),
                         background_normal="", background_down="",
                         background_color=(0, 0, 0, 0), **kw)
        self._active = False
        self._icon_name = None
        self._icon_rect = None
        with self.canvas.before:
            self._bg_color = Color(*COLOR_BTN)
            self._bg = RoundedRectangle(radius=[dp(8)])
            self._border_color = Color(*COLOR_BORDER)
            self._border = Line(width=1.1)
        if icon:
            self.set_icon(icon)
        self.bind(pos=self._layout, size=self._layout, state=self._layout)
        self._layout()

    def set_icon(self, name):
        self._icon_name = name
        tex = CoreImage(str(ICONS_DIR / f"{name}.png")).texture
        if self._icon_rect is None:
            with self.canvas.after:
                Color(1, 1, 1, 1)
                self._icon_rect = Rectangle(texture=tex)
        else:
            self._icon_rect.texture = tex
        self._layout()

    def set_active(self, active):
        self._active = active
        self._layout()

    def _layout(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rounded_rectangle = (*self.pos, *self.size, dp(8))
        self._bg_color.rgba = (COLOR_BTN_DOWN
                               if self.state == "down" or self._active
                               else COLOR_BTN)
        if self._icon_rect is not None:
            s = min(self.size) * 0.42
            self._icon_rect.pos = (self.center_x - s / 2,
                                   self.center_y - s / 2)
            self._icon_rect.size = (s, s)


class RobotrackerApp(App):
    title = "ROBOTRACKER"

    def __init__(self, songs_dir=DEFAULT_SONGS, **kwargs):
        super().__init__(**kwargs)
        self.songs_dir = Path(songs_dir)
        self.player: Player | None = None
        self.view = None
        self.screen = "phrase"
        self.octave = 4
        self.last_instr = 0
        self.dirty = False
        self._nibbles: list[int] = []
        self._fx_param_mode = False
        self._held: set[str] = set()      # teclas LGPT pulsadas ahora
        self._sel_anchor = None           # (row, track) o None
        self._clipboard = None            # bloque de clip_region

    # ------------------------------------------------------------------
    def build(self):
        self.songs = find_songs(self.songs_dir)
        if not self.songs:
            raise SystemExit(f"No hay canciones LGPT en {self.songs_dir}")
        self.song_idx = 0
        self.song_row = 0

        main = BoxLayout(orientation="vertical")

        # --- toolbar -------------------------------------------------
        toolbar = _bar_layout(TOOLBAR_H)
        self.play_btn = IconButton(icon="play", width=dp(64))
        self.play_btn.bind(on_press=self.toggle_play)
        toolbar.add_widget(self.play_btn)
        stop_btn = IconButton(icon="stop", width=dp(64))
        stop_btn.bind(on_press=self.stop)
        toolbar.add_widget(stop_btn)
        # indicador de reproducción (parpadea mientras suena)
        self.play_indicator = _bar_label("●", width=dp(24),
                                         bold=True, color=COLOR_OK)
        self.play_indicator.font_name = "Icons"
        self.play_indicator.font_size = dp(18)
        self.play_indicator.halign = "center"
        self.play_indicator.opacity = 0.15
        toolbar.add_widget(self.play_indicator)

        prev_song = IconButton(icon="prev", width=dp(52))
        prev_song.bind(on_press=lambda *_: self.step_song(-1))
        toolbar.add_widget(prev_song)
        # el nombre de canción es el elemento flexible: se encoge si falta hueco
        self.song_label = _bar_label("")
        self.song_label.shorten = True
        self.song_label.shorten_from = "right"
        toolbar.add_widget(self.song_label)
        next_song = IconButton(icon="next", width=dp(52))
        next_song.bind(on_press=lambda *_: self.step_song(1))
        toolbar.add_widget(next_song)

        self.screen_btns = {}
        for name, letter in (("song", "S"), ("chain", "C"), ("phrase", "P")):
            btn = IconButton(text=letter, width=dp(52))
            btn.bind(on_press=lambda _b, n=name: self.set_screen(n))
            self.screen_btns[name] = btn
            toolbar.add_widget(btn)

        self.context_label = _bar_label("", width=dp(110))
        # tap en el contexto (fila song / step chain) = subir un nivel
        self.context_label.bind(on_touch_up=self._context_tap)
        toolbar.add_widget(self.context_label)
        edit_btn = IconButton(text="✎", width=dp(52))
        edit_btn.font_name = "Icons"
        edit_btn.bind(on_press=self._edit_cell_popup)
        toolbar.add_widget(edit_btn)
        self.bpm_label = _bar_label("", width=dp(70))
        toolbar.add_widget(self.bpm_label)
        self.oct_label = _bar_label("", width=dp(55))
        toolbar.add_widget(self.oct_label)
        save_btn = IconButton(icon="save", width=dp(64))
        save_btn.bind(on_press=self.save)
        toolbar.add_widget(save_btn)
        exit_btn = IconButton(icon="exit", width=dp(52))
        exit_btn.bind(on_press=self.quit_app)
        toolbar.add_widget(exit_btn)
        main.add_widget(toolbar)

        # --- editor ---------------------------------------------------
        self.editor = PatternEditor()
        self.editor.bind(on_enter_cell=self._enter_cell)
        main.add_widget(self.editor)

        root = FloatLayout()
        root.add_widget(main)

        # --- toast (feedback de guardar, errores...) --------------------
        self.toast = Label(text="", font_size=dp(18), bold=True,
                           font_name="Icons", opacity=0,
                           size_hint=(None, None),
                           pos_hint={"center_x": 0.5, "center_y": 0.5})
        with self.toast.canvas.before:
            Color(0.05, 0.05, 0.07, 0.92)
            self.toast._bg = Rectangle(pos=self.toast.pos,
                                       size=self.toast.size)
        self.toast.bind(
            texture_size=lambda w, ts: setattr(
                w, "size", (ts[0] + dp(48), ts[1] + dp(28))),
            pos=lambda w, *_: setattr(w._bg, "pos", w.pos),
            size=lambda w, *_: setattr(w._bg, "size", w.size))
        root.add_widget(self.toast)

        self.load_song(0)

        # Some window providers don't propagate the initial size to the
        # root widget (leaving margins right/top); force the sync.
        root.size = Window.size
        Window.bind(on_resize=lambda *_: setattr(root, "size", Window.size))

        Window.bind(on_key_down=self._on_key_down)
        Window.bind(on_key_up=self._on_key_up)
        Clock.schedule_interval(self._tick, 1 / 30)
        return root

    # ------------------------------------------------------------------
    # Toast
    # ------------------------------------------------------------------
    def _toast(self, text, ok=True):
        self.toast.text = text
        self.toast.color = COLOR_OK if ok else COLOR_ERROR
        self.toast.opacity = 1
        Clock.unschedule(self._hide_toast)
        Clock.schedule_once(self._hide_toast, 1.6)

    def _hide_toast(self, *_):
        self.toast.opacity = 0

    # ------------------------------------------------------------------
    # Songs y pantallas
    # ------------------------------------------------------------------
    def load_song(self, idx):
        self.song_idx = idx % len(self.songs)
        if self.player is not None:
            self.player.close()
        song_dir = self.songs[self.song_idx]
        self.project = load_project(song_dir)
        self.player = Player(song_dir)
        self.dirty = False
        self.set_screen("phrase", reset_cursor=True)

    def step_song(self, delta):
        self.load_song(self.song_idx + delta)

    def set_screen(self, name, reset_cursor=False):
        """Cambia de vista arrastrando el contexto del cursor (estilo Piggy:
        song -> chain usa la fila de la song; chain -> phrase usa el step)."""
        cursor_row = self.editor.cursor_row
        if name == "chain":
            if self.screen == "song":
                self.song_row = cursor_row
            self.view = ChainView(self.project, self.song_row)
        elif name == "phrase":
            if self.screen == "song":
                self.song_row = cursor_row
            if self.screen == "chain":
                chain_step = cursor_row
            elif isinstance(self.view, PhraseView):
                chain_step = self.view.chain_step
            else:
                chain_step = 0
            self.view = PhraseView(self.project, self.song_row, chain_step)
        else:
            self.view = SongView(self.project)
        self.screen = name
        self.editor.pattern = self.view
        self.editor.scroll_x = self.editor.scroll_y = 0
        self._clear_selection()
        if reset_cursor:
            self.editor.cursor_row = 0
            self.editor.cursor_track = 0
            self.editor.cursor_col = 0
        else:
            self.editor.cursor_row = min(cursor_row, self.view.length - 1)
        self._nibbles = []
        self._fx_param_mode = False
        for n, btn in self.screen_btns.items():
            btn.set_active(n == name)
        self._refresh_labels()

    def _refresh_labels(self):
        name = self.songs[self.song_idx].name
        self.song_label.text = name + (" *" if self.dirty else "")
        tempo = self.project.project.get("tempo", "?")
        self.bpm_label.text = f"BPM {tempo}"
        self.oct_label.text = f"Oct {self.octave}"
        if self.screen == "song":
            self.context_label.text = ""
        elif self.screen == "chain":
            self.context_label.text = f"Song row {self.song_row:02X}"
        else:
            self.context_label.text = (f"Row {self.song_row:02X} "
                                       f"step {self.view.chain_step:X}")

    # ------------------------------------------------------------------
    # Entrar con tap / popup genérico
    # ------------------------------------------------------------------
    def _context_tap(self, widget, touch):
        if widget.collide_point(*touch.pos):
            if self.screen == "phrase":
                self.set_screen("chain")
            elif self.screen == "chain":
                self.set_screen("song")

    def _enter_cell(self, *_):
        """Tap sobre la celda ya seleccionada = popup de la celda (entrar,
        cambiar valor, nueva, vaciar). En PHRASE/instr: banco de instr."""
        if isinstance(self.view, PhraseView):
            if TRACK_COLUMNS[self.editor.cursor_col][0] == "instr":
                self._pick_instrument()
        else:
            self._edit_cell_popup()

    def _open_list_popup(self, title, items, on_pick, value_stepper=None):
        """Popup táctil con una lista scrollable de opciones.
        `items` = [(texto, valor)]; al elegir se llama on_pick(valor).
        Con `value_stepper` (callable(delta)) el pie lleva −/+ que ciclan
        el valor de la celda sin cerrar el popup."""
        grid = GridLayout(cols=1, size_hint_y=None, spacing=dp(4),
                          padding=dp(6))
        grid.bind(minimum_height=grid.setter("height"))
        popup = Popup(title=title, size_hint=(0.7, 0.8),
                      background_color=(0.05, 0.05, 0.07, 0.97),
                      title_size=dp(20), separator_color=COLOR_ACCENT)
        for text, value in items:
            btn = Button(text=text, size_hint_y=None, height=dp(52),
                         font_size=dp(17), halign="left",
                         background_normal="", background_down="",
                         background_color=COLOR_BTN)
            btn.bind(size=lambda w, *_: setattr(w, "text_size", w.size),
                     on_press=lambda _b, v=value: (popup.dismiss(),
                                                   on_pick(v)))
            grid.add_widget(btn)
        scroll = ScrollView()
        scroll.add_widget(grid)
        box = BoxLayout(orientation="vertical", spacing=dp(6),
                        padding=(0, 0, 0, dp(6)))
        box.add_widget(scroll)
        footer = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        if value_stepper is not None:
            for label, delta in (("− valor", -1), ("+ valor", 1)):
                b = Button(text=label, font_size=dp(17),
                           background_normal="", background_down="",
                           background_color=COLOR_BTN)
                b.bind(on_press=lambda _b, d=delta: value_stepper(d))
                footer.add_widget(b)
        close = Button(text="Cerrar", font_size=dp(17),
                       background_normal="", background_down="",
                       background_color=COLOR_BTN)
        close.bind(on_press=popup.dismiss)
        footer.add_widget(close)
        box.add_widget(footer)
        popup.content = box
        popup.open()
        return popup

    def _pick_instrument(self):
        bank = sorted(self.project.instrument_bank.items())
        items = [("—  (sin instrumento)", None)]
        for iid, entry in bank:
            params = entry.get("params", {})
            name = (params.get("sample") if entry.get("type") == "Sample"
                    else f"MIDI ch {int(params.get('channel', 0)) + 1}")
            items.append((f"{iid:02X}  {name or '(vacío)'}", iid))
        self._open_list_popup("Instrumento", items, self._apply_instrument,
                              value_stepper=self._value_step)

    def _apply_instrument(self, iid):
        row, track = self.editor.cursor_row, self.editor.cursor_track
        self.view.set_instr(row, track, iid)
        if iid is not None:
            self.last_instr = iid
        self._mark_dirty()
        self.editor.redraw()

    # ------------------------------------------------------------------
    # Valor − / + (táctil y mando)
    # ------------------------------------------------------------------
    def _value_step(self, delta):
        """Cicla el valor de la celda por los valores existentes (estilo
        Piggy: mantener botón + izq/der). En celda vacía, + crea."""
        row, track = self.editor.cursor_row, self.editor.cursor_track
        col = self._cursor_col_key() if isinstance(self.view, PhraseView) \
            else None
        if cycle_cell(self.view, row, track, delta, col=col,
                      octave=self.octave, last_instr=self.last_instr):
            if isinstance(self.view, PhraseView) and col == "instr":
                iid = self.view.cell(row, track).instr
                if iid is not None:
                    self.last_instr = int(iid, 16)
            self._after_edit(advance=False)

    def _edit_cell_popup(self, *_):
        """Popup de la celda del cursor (botón ✎ o tap sobre la celda ya
        seleccionada): entrar, elegir valor de la lista, −/+, nueva, vaciar.
        En SONG son chains, en CHAIN phrases, en PHRASE/instr instrumentos."""
        row, track = self.editor.cursor_row, self.editor.cursor_track
        if isinstance(self.view, SongView):
            kind = "Chain"
            items = [(f"{c:02X}", c) for c in used_chains(self.project)]
            deeper = "chain"
        elif isinstance(self.view, ChainView):
            kind = "Phrase"
            items = [(f"{p:02X}", p) for p in used_phrases(self.project)]
            deeper = "phrase"
        elif isinstance(self.view, PhraseView) \
                and self._cursor_col_key() == "instr":
            self._pick_instrument()
            return
        else:
            self._toast("− / + para cambiar el valor")
            return

        def on_pick(v):
            if v == "enter":
                self.set_screen(deeper)
                return
            if v == "new":
                if isinstance(self.view, SongView):
                    self.view.new_chain(row, track)
                else:
                    self.view.new_phrase(row, track)
            else:
                self.view.set_value(row, track, v)
            self._after_edit(advance=False)

        entries = []
        current = self.view.cell(row, track).note
        if current is not None:
            entries.append((f"» Entrar en {kind.lower()} {current}", "enter"))
        entries += [(f"+ Nueva {kind.lower()}", "new"),
                    ("— Vaciar", None)] + items
        self._open_list_popup(f"{kind} · fila {row:02X} · canal {track + 1}",
                              entries, on_pick,
                              value_stepper=self._value_step)

    # ------------------------------------------------------------------
    # Transporte + playhead
    # ------------------------------------------------------------------
    def toggle_play(self, *_):
        # En la vista SONG el play arranca desde la fila del cursor
        # (estilo Piggy); en CHAIN/PHRASE desde el principio de la song.
        from_row = self.editor.cursor_row if self.screen == "song" else 0
        if not self.player.toggle(from_row) and self.player.audio_error:
            self._toast(f"{ICON_ERROR} Audio: {self.player.audio_error}",
                        ok=False)

    def stop(self, *_):
        self.player.stop()

    def quit_app(self, *_):
        # ojo: nuestra stop() (transporte) sombrea App.stop; hay que
        # llamar a la de Kivy explícitamente
        App.stop(self)

    def _tick(self, _dt):
        eng = self.player.engine
        playing = eng.playing
        icon = "pause" if playing else "play"
        if self.play_btn._icon_name != icon:
            self.play_btn.set_icon(icon)
        self.play_btn.set_active(playing)
        if playing:
            # parpadeo ~2 Hz
            self.play_indicator.opacity = (
                1.0 if int(time.monotonic() * 2) % 2 == 0 else 0.25)
        else:
            self.play_indicator.opacity = 0.15
        rows = set()
        if playing:
            view = self.view
            for t in range(view.num_tracks):
                ch = eng.channels[t]
                # playhead en las tres pantallas: cada vista resalta la
                # posición del secuenciador que le corresponde
                if isinstance(view, PhraseView):
                    if view.phrase_of(t) is not None and ch.phrase == view.phrase_of(t):
                        rows.add(ch.phrase_pos)
                elif isinstance(view, ChainView):
                    if view.chain_of(t) is not None and ch.chain == view.chain_of(t):
                        rows.add(ch.chain_pos)
                elif isinstance(view, SongView):
                    if ch.playing:
                        rows.add(ch.song_pos)
        rows = frozenset(rows)
        if rows != self.editor.play_rows:
            self.editor.play_rows = rows
            self.editor.redraw()

    # ------------------------------------------------------------------
    # Edición
    # ------------------------------------------------------------------
    def _mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self._refresh_labels()

    def _cursor_col_key(self):
        return TRACK_COLUMNS[self.editor.cursor_col][0]

    def _reset_entry(self):
        self._nibbles = []
        self._fx_param_mode = False

    def _nibbles_value(self, width):
        """Valor hex con los dígitos tecleados hasta ahora en las posiciones
        altas (estilo tracker: '5' en un param de 4 dígitos = 0x5000)."""
        value = 0
        for d in self._nibbles:
            value = (value << 4) | d
        return value << (4 * (width - len(self._nibbles)))

    def _edit_note(self, semitone):
        if not isinstance(self.view, PhraseView):
            return
        if self._cursor_col_key() != "note":
            return
        note_byte = note_name_to_byte(
            f"{NOTE_NAMES[semitone % 12]}{self.octave + semitone // 12}")
        row, track = self.editor.cursor_row, self.editor.cursor_track
        self.view.set_note(row, track, note_byte)
        if self.view.cell(row, track).instr is None:
            self.view.set_instr(row, track, self.last_instr)
        self._after_edit(advance=True)

    def _edit_hex(self, digit):
        """Entrada hex por nibbles: 2 dígitos para instr/índices, 4 para el
        param de un fx."""
        row, track = self.editor.cursor_row, self.editor.cursor_track
        if isinstance(self.view, PhraseView):
            key = self._cursor_col_key()
            if key == "instr":
                width, setter = 2, self.view.set_instr
            elif key in ("fx1", "fx2"):
                width = 4
                which = 1 if key == "fx1" else 2
                setter = lambda r, t, v: self.view.set_fx_param(r, t, which, v)
                self._fx_param_mode = True
            else:
                return
        elif isinstance(self.view, (SongView, ChainView)):
            width, setter = 2, self.view.set_value
        else:
            return
        self._nibbles.append(digit)
        value = self._nibbles_value(width)
        setter(row, track, value)
        complete = len(self._nibbles) >= width
        if complete:
            self._reset_entry()
            if isinstance(self.view, PhraseView) \
                    and self._cursor_col_key() == "instr":
                self.last_instr = value
        self._after_edit(advance=complete)

    def _cycle_fx_cmd(self, letter):
        """En columna fx: salta al primer comando que empieza por la letra;
        repetir la letra cicla entre los que empiezan igual."""
        key = self._cursor_col_key()
        which = 1 if key == "fx1" else 2
        row, track = self.editor.cursor_row, self.editor.cursor_track
        candidates = [c for c in FX_COMMANDS if c.lower().startswith(letter)]
        if not candidates:
            return
        current = self.view.fx_cmd_at(row, track, which)
        if current in candidates:
            nxt = candidates[(candidates.index(current) + 1) % len(candidates)]
        else:
            nxt = candidates[0]
        self.view.set_fx_cmd(row, track, which, nxt)
        self._after_edit(advance=False)

    def _new_slot(self):
        """Insert: crea una chain/phrase nueva en la celda vacía del cursor
        (vistas song/chain; en phrase se crea sola al editar)."""
        row, track = self.editor.cursor_row, self.editor.cursor_track
        if self.view.cell(row, track).note is not None:
            return
        if isinstance(self.view, SongView):
            created = self.view.new_chain(row, track)
        elif isinstance(self.view, ChainView):
            created = self.view.new_phrase(row, track)
        else:
            return
        if created is not None:
            self._after_edit(advance=False)

    def _clear_cell(self):
        row, track = self.editor.cursor_row, self.editor.cursor_track
        if isinstance(self.view, PhraseView):
            key = self._cursor_col_key()
            if key == "note":
                self.view.set_note(row, track, None)
            elif key == "instr":
                self.view.set_instr(row, track, None)
            elif key in ("fx1", "fx2"):
                self.view.clear_fx(row, track, 1 if key == "fx1" else 2)
            else:
                return
        else:
            self.view.set_value(row, track, None)
        self._after_edit(advance=False)

    def _after_edit(self, advance):
        self._mark_dirty()
        if advance:
            self.editor.move(drow=1)
        self.editor.redraw()

    def save(self, *_):
        try:
            save_project(self.project)
        except Exception as exc:
            self._toast(f"{ICON_ERROR} Error al guardar: {exc}", ok=False)
            return
        self.dirty = False
        self._refresh_labels()
        self._toast(f"{ICON_OK} Guardado")

    # ------------------------------------------------------------------
    # Controles LGPT (ver el comentario junto a HEX_KEYS)
    # ------------------------------------------------------------------
    def _on_key_up(self, _window, _key, _scancode, codepoint, *_args):
        self._held.discard((codepoint or "").lower())

    def _screen_up(self):
        """Sube un nivel: phrase → chain → song."""
        if self.screen == "phrase":
            self.set_screen("chain")
        elif self.screen == "chain":
            self.set_screen("song")

    def _screen_down(self):
        """Baja un nivel: song → chain → phrase."""
        if self.screen == "song":
            self.set_screen("chain")
        elif self.screen == "chain":
            self.set_screen("phrase")

    def _cell_empty(self, row, track) -> bool:
        data = read_cell(self.view, row, track)
        if data is None:
            return True
        if isinstance(self.view, PhraseView):
            note, instr, c1, p1, c2, p2 = data
            return (note is None and instr is None and p1 == 0 and p2 == 0
                    and c1 in (FX_EMPTY, "----") and c2 in (FX_EMPTY, "----"))
        return False

    def _insert_default(self):
        """A en celda vacía (sin portapapeles): inserta 00 en song/chain;
        en phrase, nota Do de la octava actual o instr 00 según la columna."""
        row, track = self.editor.cursor_row, self.editor.cursor_track
        if isinstance(self.view, (SongView, ChainView)):
            self.view.set_value(row, track, 0)
            self._after_edit(advance=True)
            return
        col = self._cursor_col_key()
        if col == "note":
            self._edit_note(0)          # ya hace _after_edit(advance=True)
        elif col == "instr":
            self.view.set_instr(row, track, self.last_instr)
            self._after_edit(advance=True)

    def _lgpt_a_tap(self):
        """A a solas: celda vacía = pegar o insertar; con valor = copiar."""
        row, track = self.editor.cursor_row, self.editor.cursor_track
        if self._cell_empty(row, track):
            if self._clipboard:
                self._paste()
            else:
                self._insert_default()
        else:
            self._clipboard = clip_region(self.view, row, track, row, track)
            self._toast(f"{ICON_OK} Celda copiada")

    def _lgpt_arrows(self, key, ctrl):
        ed = self.editor
        drow = -1 if key == 273 else 1 if key == 274 else 0
        dcol = -1 if key == 276 else 1 if key == 275 else 0
        if ctrl:
            # Ctrl+flechas: ←/→ cambian de pantalla, ↑/↓ saltan 16 filas
            if dcol < 0:
                self._screen_up()
            elif dcol > 0:
                self._screen_down()
            else:
                ed.move(drow=16 * drow)
            return True
        if LGPT_A in self._held:
            # A+flechas: ±1 con izq/der; ±0x10 (u octava en notas) arr/abj
            if drow:
                big = 12 if (isinstance(self.view, PhraseView)
                             and self._cursor_col_key() == "note") else 0x10
                self._nudge(big * drow)
            else:
                self._nudge(dcol)
            return True
        if self._sel_anchor is not None:
            # con selección activa, izq/der mueven por CANAL (la selección
            # es de celdas, no de columnas internas)
            ed.move(drow=drow, dtrack=dcol)
            self._update_selection()
        else:
            ed.move(drow=drow, dcol=dcol)
        return True

    # -- selección / portapapeles -----------------------------------------
    def _selection(self):
        """(r0, t0, r1, t1) normalizado de la selección activa."""
        if self._sel_anchor is None:
            return None
        ar, at = self._sel_anchor
        cr, ct = self.editor.cursor_row, self.editor.cursor_track
        return (min(ar, cr), min(at, ct), max(ar, cr), max(at, ct))

    def _update_selection(self):
        self.editor.selection = self._selection()
        self.editor.redraw()

    def _clear_selection(self):
        self._sel_anchor = None
        if self.editor.selection is not None:
            self.editor.selection = None
            self.editor.redraw()

    def _copy_selection(self):
        sel = self._selection()
        if sel is None:
            return
        self._clipboard = clip_region(self.view, *sel)
        self._clear_selection()
        self._toast(f"{ICON_OK} Copiado")

    def _cut_selection(self):
        sel = self._selection()
        if sel is None:
            return
        self._clipboard = clip_region(self.view, *sel, cut=True)
        self._clear_selection()
        self._after_edit(advance=False)
        self._toast(f"{ICON_OK} Cortado")

    def _cut_cell(self):
        row, track = self.editor.cursor_row, self.editor.cursor_track
        self._clipboard = clip_region(self.view, row, track, row, track,
                                      cut=True)
        self._after_edit(advance=False)
        self._toast(f"{ICON_OK} Celda cortada")

    def _paste(self):
        if not self._clipboard:
            return
        paste_region(self.view, self.editor.cursor_row,
                     self.editor.cursor_track, self._clipboard)
        self._after_edit(advance=False)
        self._toast(f"{ICON_OK} Pegado")

    def _nudge(self, delta):
        """A+flechas: incremento crudo; con selección, a toda la región."""
        changed = False
        if self._sel_anchor is not None:
            r0, t0, r1, t1 = self._selection()
            for r in range(r0, r1 + 1):
                for t in range(t0, t1 + 1):
                    changed |= nudge_cell(self.view, r, t, delta)
        else:
            col = self._cursor_col_key() \
                if isinstance(self.view, PhraseView) else None
            changed = nudge_cell(self.view, self.editor.cursor_row,
                                 self.editor.cursor_track, delta, col=col)
        if changed:
            self._after_edit(advance=False)

    # ------------------------------------------------------------------
    # Teclado
    # ------------------------------------------------------------------
    def _on_key_down(self, _window, key, _scancode, codepoint, modifiers):
        ed = self.editor
        shift = "shift" in modifiers
        ctrl = "ctrl" in modifiers

        # --- controles LGPT (tienen prioridad; ver junto a HEX_KEYS) ----
        if key in (273, 274, 275, 276):           # flechas
            return self._lgpt_arrows(key, ctrl)
        ch0 = (codepoint or "").lower()
        if ch0 == LGPT_A and not ctrl:
            first = LGPT_A not in self._held
            self._held.add(LGPT_A)
            if first:
                self._lgpt_a_tap()
            return True
        if ch0 == LGPT_B and not ctrl:
            first = LGPT_B not in self._held
            self._held.add(LGPT_B)
            if first:
                if LGPT_A in self._held:
                    # A+S: cortar (la selección si la hay, si no la celda)
                    if self._sel_anchor is not None:
                        self._cut_selection()
                    else:
                        self._cut_cell()
                elif self._sel_anchor is not None:
                    self._copy_selection()        # S a solas: copiar sel.
            return True

        if key == 27 and self._sel_anchor is not None:  # Esc: cancela sel.
            self._clear_selection()
            return True

        if ctrl and codepoint == "s":
            # Ctrl+S = empezar selección (LT+B en LGPT); guardar: F9
            self._sel_anchor = (ed.cursor_row, ed.cursor_track)
            self._update_selection()
            return True
        if key == 290:        # F9: guardar (Ctrl+S ahora es selección LGPT)
            self.save()
            return True

        # --- edición ---------------------------------------------------
        if codepoint and not ctrl:
            ch = codepoint.lower()
            if ch in ("-", "_"):
                self._reset_entry()
                self._value_step(-1)
                return True
            if ch in ("+", "="):
                self._reset_entry()
                self._value_step(1)
                return True
            colkey = self._cursor_col_key()
            on_phrase = isinstance(self.view, PhraseView)
            if on_phrase and colkey == "note" and ch in PIANO_KEYS:
                self._reset_entry()
                self._edit_note(PIANO_KEYS[ch])
                return True
            if on_phrase and colkey in ("fx1", "fx2"):
                # letra = comando (cicla); a-f solo valen como hex si ya
                # estamos tecleando el param; dígitos = param
                if ch.isalpha() and not (self._fx_param_mode
                                         and ch in HEX_KEYS):
                    self._reset_entry()
                    self._cycle_fx_cmd(ch)
                    return True
                if ch in HEX_KEYS:
                    self._edit_hex(HEX_KEYS[ch])
                    return True
                return False
            if ch in HEX_KEYS:
                self._edit_hex(HEX_KEYS[ch])
                return True
        if key in (8, 127):     # backspace / delete
            self._reset_entry()
            self._clear_cell()
            return True
        if key == 277:          # insert: nueva chain/phrase en celda vacía
            self._reset_entry()
            self._new_slot()
            return True

        # --- navegación ------------------------------------------------
        if key == 273:      # up
            ed.move(drow=-4 if shift else -1)
        elif key == 274:    # down
            ed.move(drow=4 if shift else 1)
        elif key == 276:    # left
            ed.move(dcol=-1)
        elif key == 275:    # right
            ed.move(dcol=1)
        elif key == 9:      # tab
            ed.move(dtrack=-1 if shift else 1)
        elif key == 280:    # page up
            ed.move(drow=-16)
        elif key == 281:    # page down
            ed.move(drow=16)
        elif key == 278:    # home
            ed.cursor_row = 0
            ed._ensure_cursor_visible()
        elif key == 279:    # end
            ed.cursor_row = ed.pattern.length - 1
            ed._ensure_cursor_visible()
        elif key == 32:     # space: play/pause
            self.toggle_play()
        elif key == 282:    # F1: valor - (L2 en la Odin)
            self._reset_entry()
            self._value_step(-1)
            return True
        elif key == 283:    # F2: valor + (R2 en la Odin)
            self._reset_entry()
            self._value_step(1)
            return True
        elif key == 287:    # F6: octave down
            self.octave = max(0, self.octave - 1)
            self._refresh_labels()
        elif key == 288:    # F7: octave up
            self.octave = min(8, self.octave + 1)
            self._refresh_labels()
        elif key == 284:    # F3: song screen
            self.set_screen("song")
        elif key == 285:    # F4: chain screen
            self.set_screen("chain")
        elif key == 286:    # F5: phrase screen
            self.set_screen("phrase")
        else:
            return False
        self._reset_entry()
        return True

    def on_stop(self):
        if self.player is not None:
            self.player.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--songs", default=str(DEFAULT_SONGS),
                        help="carpeta con proyectos lgpt_* (defecto: ../sinte/songs)")
    args = parser.parse_args()
    RobotrackerApp(args.songs).run()


if __name__ == "__main__":
    main()
