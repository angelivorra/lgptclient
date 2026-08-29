"""ROBOTRACKER2 — clon de la interfaz de lgptclient, pantalla por pantalla.

App Kivy nueva (misma estética que robotracker) sobre el motor de ../sinte.
Estado actual: cargar canción (lista) → editor con navegación 2D de pantallas
estilo LGPT (SONG implementada, resto vacías).

Todos los controles pasan por `controls` (botones lógicos): en PC el teclado,
en la Odin 2 Portal el gamepad. La semántica LGPT (dpad = mover cursor, A+dir =
editar, L+dir = cambiar de pantalla, B = borrar, START = play, BACK = volver)
se resuelve aquí sobre botones lógicos.

Ejecutar:  robotracker/.venv/bin/python robotracker2/robotracker2.py [--songs RUTA]
"""

import argparse
import os
import shutil
from pathlib import Path

from kivy.config import Config

# Tamaño de ventana de reserva (fuera de fullscreen). Antes de crear la Window.
Config.set("graphics", "width", "1280")
Config.set("graphics", "height", "720")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.screenmanager import ScreenManager, NoTransition

from controls import (A, B, BACK, DOWN, DPAD, L2, LEFT, R2, RIGHT, START, UP,
                      GAMEPAD_BUTTONS, hat_to_buttons, key_to_button)
from sinte_bridge import save_project
from songs import DEFAULT_SONGS, display_name, find_songs, load_project
from player import Player
from robots import screen_label
from screens.confirm import ConfirmDialog
from screens.load_song import LoadSongScreen
from screens.editor import EditorScreen
from screens.image_browser import ImageBrowser
from screens.sample_browser import SampleBrowser
from theme import setup_window

# Biblioteca de samples para el navegador (repo: lgptclient/samples).
DEFAULT_SAMPLES = DEFAULT_SONGS.parent.parent / "samples"
# images/ del repo: eventos de pantalla (MDCC) del canal de robotas.
DEFAULT_IMAGES = DEFAULT_SONGS.parent.parent / "images"

# Opciones del diálogo de cambios sin guardar.
_CONFIRM_OPTS = [("save", "Guardar"), ("discard", "Descartar"),
                 ("cancel", "Cancelar")]

# Botón lógico del dpad -> desplazamiento en la rejilla de pantallas (L+dir).
NAV_DELTA = {UP: (0, -1), DOWN: (0, 1), LEFT: (-1, 0), RIGHT: (1, 0)}


class Robotracker2App(App):
    title = "ROBOTRACKER2"

    def __init__(self, songs_dir=DEFAULT_SONGS, fullscreen=False,
                 samples_dir=DEFAULT_SAMPLES, images_dir=DEFAULT_IMAGES,
                 **kwargs):
        super().__init__(**kwargs)
        self.songs_dir = songs_dir
        self.samples_dir = Path(samples_dir)
        self.images_dir = Path(images_dir)
        self.browser = None        # SampleBrowser/ImageBrowser activo (o None)
        self._screen_step = None   # step de PHRASE que se está editando
        self.fullscreen = fullscreen
        self.held = set()          # botones lógicos pulsados ahora
        self.dirty = False
        self._a_consumed = False   # A se usó en un acorde (no disparar tap)
        self.dialog = None         # ConfirmDialog activo (o None)
        self.player = None         # reproductor de la canción cargada
        self._mute_combo = None    # combo L2+S en curso (mute) o None

    def build(self):
        setup_window(self.fullscreen)
        self.songs = find_songs(self.songs_dir)
        if not self.songs:
            raise SystemExit(f"No hay canciones LGPT en {self.songs_dir}")

        self.sm = ScreenManager(transition=NoTransition())
        self.load_screen = LoadSongScreen(self.songs, name="load")
        self.editor_screen = EditorScreen(on_change=self._mark_dirty,
                                          on_action=self._project_action,
                                          on_pick_screen=self._open_screen_browser,
                                          images_dir=self.images_dir,
                                          name="editor")
        self.sm.add_widget(self.load_screen)
        self.sm.add_widget(self.editor_screen)
        self.sm.current = "load"

        self.root_layout = FloatLayout()
        self.root_layout.add_widget(self.sm)

        Window.bind(on_key_down=self._on_key_down, on_key_up=self._on_key_up)
        Window.bind(on_request_close=self._on_request_close)
        # Gamepad (Odin 2 Portal); inofensivo si no hay mando conectado.
        Window.bind(on_joy_button_down=self._on_joy_button_down,
                    on_joy_button_up=self._on_joy_button_up,
                    on_joy_hat=self._on_joy_hat)
        self._hat_buttons = set()
        Clock.schedule_interval(self._tick, 1 / 30)   # playhead
        return self.root_layout

    # ------------------------------------------------------------------
    # Entrada -> botones lógicos
    # ------------------------------------------------------------------
    def _on_key_down(self, _win, key, _scancode, codepoint, _modifiers):
        button = key_to_button(key, codepoint)
        if button is None:
            return False
        self.held.add(button)
        return self._dispatch(button, set(self.held))

    def _on_key_up(self, _win, key, *_):
        button = key_to_button(key)
        if button is not None:
            self._release(button)
        return False

    def _on_joy_button_down(self, _win, _stick, buttonid):
        button = GAMEPAD_BUTTONS.get(buttonid)
        if button is None:
            return False
        self.held.add(button)
        return self._dispatch(button, set(self.held))

    def _on_joy_button_up(self, _win, _stick, buttonid):
        button = GAMEPAD_BUTTONS.get(buttonid)
        if button is not None:
            self._release(button)
        return False

    def _release(self, button):
        if self.browser is not None:
            self.held.discard(button)
            return
        # Combo de mute (L2+S): el orden de soltado decide si queda o revierte.
        if self._mute_combo is not None and button in (L2, B):
            self._release_mute(button)
            self.held.discard(button)
            return
        self.held.discard(button)
        if self.dialog is not None:
            self._a_consumed = False
            return
        # A soltado sin haberse usado en un acorde -> "tap".
        if button == A:
            if not self._a_consumed and self.sm.current == "editor":
                ed = self.editor_screen
                if ed.current == "song":
                    ed.song_grid.a_tap()       # copiar/pegar/00
                elif ed.current == "chain":
                    ed.chain_grid.a_tap()      # copiar/pegar/00
                elif ed.current == "phrase":
                    ed.phrase_grid.a_tap()     # copiar/pegar/def
                elif ed.current == "groove":
                    ed.groove_grid.a_tap()     # copiar/pegar/def
                elif ed.current in ("phrase_table", "instrument_table"):
                    ed.table_grid.a_tap()      # copiar/pegar/def
                elif ed.current == "project":
                    ed.project_menu.activate()  # activar acción
            self._a_consumed = False

    def _on_request_close(self, *_a, **_k):
        # Botón de cerrar la ventana: avisa si hay cambios sin guardar.
        if self.dirty and self.dialog is None \
                and self.editor_screen.project is not None:
            self._confirm_exit()
            return True     # cancela el cierre; se decide en el diálogo
        return False

    def _on_joy_hat(self, _win, _stick, _hatid, value):
        # value = (x, y); genera press/release de las direcciones del dpad.
        new = hat_to_buttons(*value)
        for b in new - self._hat_buttons:
            self.held.add(b)
            self._dispatch(b, set(self.held))
        for b in self._hat_buttons - new:
            self.held.discard(b)
        self._hat_buttons = new
        return True

    # ------------------------------------------------------------------
    # Semántica (sobre botones lógicos)
    # ------------------------------------------------------------------
    def _dispatch(self, button, active):
        if self.browser is not None:
            return self._dispatch_browser(button)
        if self.dialog is not None:
            return self._dispatch_dialog(button)
        if self.sm.current == "load":
            return self._dispatch_load(button)
        if self.sm.current == "editor":
            return self._dispatch_editor(button, active)
        return False

    def _dispatch_load(self, button):
        if button == UP:
            self.load_screen.move(-1)
        elif button == DOWN:
            self.load_screen.move(1)
        elif button == A:
            self._request_load(self.load_screen.selected())
        else:
            return False
        return True

    def _dispatch_editor(self, button, active):
        ed = self.editor_screen
        # Navegación entre pantallas (global en el editor): L2 (Ctrl izq) + dpad.
        if button in DPAD and L2 in active:
            ed.navigate(*NAV_DELTA[button])
            return True
        if button == START:                 # play/stop (global en el editor)
            self._toggle_play()
            return True
        if ed.current == "song":
            return self._dispatch_song(button, active)
        if ed.current == "chain":
            return self._dispatch_chain(button, active)
        if ed.current == "phrase":
            return self._dispatch_phrase(button, active)
        if ed.current == "groove":
            return self._dispatch_groove(button, active)
        if ed.current in ("phrase_table", "instrument_table"):
            return self._dispatch_table(button, active)
        if ed.current == "instrument":
            return self._dispatch_instrument(button, active)
        if ed.current == "project":
            return self._dispatch_project(button, active)
        if button == BACK:
            self.sm.current = "load"
            return True
        return False

    def _dispatch_chain(self, button, active):
        g = self.editor_screen.chain_grid
        if button in DPAD:
            if A in active:
                g.edit(button)                       # A+dir: editar valor
                self._a_consumed = True
            else:
                g.move(button)                       # mover cursor
            return True
        if button == A:
            if R2 in active:                         # Ctrl+A: cortar / pegar
                g.cut_selection() if g.has_selection else g.paste_block()
                self._a_consumed = True
            else:
                self._a_consumed = False             # A tap: copiar/pegar/00
            return True
        if button == B:
            if R2 in active:                         # Ctrl+S: ciclar selección
                g.cycle_selection()
            elif g.has_selection:                    # S: copiar selección
                g.copy_selection()
            else:                                    # S: borrar celda
                g.delete()
            return True
        if button == BACK:
            if g.has_selection:
                g.cancel_selection()
            else:
                self.sm.current = "load"
            return True
        return False

    def _dispatch_song(self, button, active):
        g = self.editor_screen.song_grid
        if button in DPAD:
            if A in active:
                g.edit(button)                       # A+dir: editar valor
                self._a_consumed = True
            else:
                g.move(button)                       # mover cursor / extender sel.
            return True
        if button == A:
            if R2 in active:                         # Ctrl+A: cortar / pegar
                g.cut_selection() if g.has_selection else g.paste_block()
                self._a_consumed = True
            else:
                self._a_consumed = False             # A tap: se resuelve al soltar
            return True
        if button == L2:                             # L2(+S): mute mientras suena
            if B in active and self._playing_song():
                self._mute_start()
            return True
        if button == B:
            if L2 in active and self._playing_song():  # L2+S: mute de pista
                self._mute_start()
            elif R2 in active:                       # Ctrl+S: ciclar selección
                g.cycle_selection()
            elif g.has_selection:                    # S: copiar selección
                g.copy_selection()
            else:                                    # S: borrar celda
                g.delete()
            return True
        if button == BACK:
            if g.has_selection:
                g.cancel_selection()
            else:
                self.sm.current = "load"
            return True
        return False

    def _dispatch_phrase(self, button, active):
        g = self.editor_screen.phrase_grid
        if button in DPAD:
            if A in active:
                g.edit(button)                       # A+dir: editar campo
                self._a_consumed = True
            else:
                g.move(button)                       # mover cursor
            return True
        if button == A:
            if R2 in active:                         # Ctrl+A: pegar campo
                g.paste_field()
                self._a_consumed = True
            else:
                self._a_consumed = False             # A tap: copiar/pegar/def
            return True
        if button == B:
            g.delete()
            return True
        if button == BACK:
            self.sm.current = "load"
            return True
        return False

    def _dispatch_groove(self, button, active):
        g = self.editor_screen.groove_grid
        if button in DPAD:
            if A in active:
                g.edit(button)                       # A+dir: editar ticks
                self._a_consumed = True
            else:
                g.move(button)                       # step / cambiar groove
            return True
        if button == A:
            if R2 in active:                         # Ctrl+A: pegar
                g.paste()
                self._a_consumed = True
            else:
                self._a_consumed = False             # A tap: copiar/pegar/def
            return True
        if button == B:
            g.delete()
            return True
        if button == BACK:
            self.sm.current = "load"
            return True
        return False

    def _dispatch_table(self, button, active):
        g = self.editor_screen.table_grid
        if button in DPAD:
            if A in active:
                g.edit(button)
                self._a_consumed = True
            else:
                g.move(button)
            return True
        if button == A:
            if R2 in active:
                g.paste_field()
                self._a_consumed = True
            else:
                self._a_consumed = False
            return True
        if button == B:
            g.delete()
            return True
        if button == BACK:
            self.sm.current = "load"
            return True
        return False

    def _dispatch_instrument(self, button, active):
        m = self.editor_screen.instrument_menu
        if button in DPAD:
            if A in active and button in (LEFT, RIGHT):
                m.edit(button)                   # A+izq/dcha: paso grande
                self._a_consumed = True
            else:
                m.move(button)                   # arr/abj campo, izq/dcha valor
            return True
        if button == A:
            if m.field_key() == "sample":        # abrir navegador de samples
                self._open_sample_browser()
            return True
        if button == BACK:
            self.sm.current = "load"
            return True
        return False

    # -- navegadores (samples / imágenes de pantalla) -------------------
    # Ambos (SampleBrowser, ImageBrowser) comparten la misma interfaz:
    # move(button), activate(), back(), cleanup(). La app no necesita saber
    # cuál de los dos está abierto.
    def _open_browser(self, browser):
        self.browser = browser
        self.browser.size_hint = (1, 1)
        self.browser.pos = self.root_layout.pos
        self.browser.size = self.root_layout.size
        self.root_layout.bind(size=lambda w, *_: setattr(self.browser, "size",
                                                          w.size))
        self.root_layout.add_widget(self.browser)

    def _open_sample_browser(self):
        # biblioteca si existe; si no, los samples de la propia canción
        root = self.samples_dir if self.samples_dir.is_dir() \
            else self.editor_screen.project.dir / "samples"
        self._open_browser(SampleBrowser(root, on_load=self._load_sample,
                                         on_close=self._close_browser))

    def _dispatch_browser(self, button):
        b = self.browser
        if button in (UP, DOWN):
            b.move(button)
        elif button == A:
            b.activate()
        elif button in (B, BACK):
            b.back()
        return True

    def _close_browser(self):
        if self.browser is not None:
            self.browser.cleanup()
            self.root_layout.remove_widget(self.browser)
            self.browser = None

    def _load_sample(self, path):
        project = self.editor_screen.project
        name = path.name
        dest = project.dir / "samples" / name
        try:
            dest.parent.mkdir(exist_ok=True)
            if not dest.exists():
                shutil.copy2(path, dest)
        except OSError as exc:                   # noqa: BLE001
            self.editor_screen.toast_msg(f"Error: {exc}")
            self._close_browser()
            return
        self.editor_screen.instrument_menu.set_sample(name)
        self.dirty = True
        self.editor_screen.toast_msg(f"Sample: {name}")
        self._close_browser()

    def _open_screen_browser(self, step):
        self._screen_step = step
        self._open_browser(ImageBrowser(self.images_dir, on_load=self._load_screen,
                                        on_close=self._close_browser))

    def _load_screen(self, cc, value):
        self.editor_screen.phrase_grid.set_screen(self._screen_step, cc, value)
        self.dirty = True
        self.editor_screen.toast_msg(f"Screen: {screen_label(cc, value)}")
        self._close_browser()

    def _dispatch_project(self, button, active):
        m = self.editor_screen.project_menu
        if button == UP:
            m.move(-1)
        elif button == DOWN:
            m.move(1)
        elif button in (LEFT, RIGHT):
            m.adjust(1 if button == RIGHT else -1, coarse=(A in active))
            if A in active:
                self._a_consumed = True
        elif button == A:
            self._a_consumed = False                 # tap activa la acción
        elif button == BACK:
            self.sm.current = "load"
        else:
            return False
        return True

    def _project_action(self, key):
        ed = self.editor_screen
        if key == "load":
            self.sm.current = "load"
        elif key == "save":
            self._save()
        elif key == "exit":
            self._request_exit()
        elif key == "save_as":
            ed.toast_msg("Save Song As: pendiente")
        else:                                        # compact_seq / compact_instr
            ed.toast_msg("Compact: pendiente")

    def _save(self):
        ed = self.editor_screen
        try:
            save_project(ed.project)
            self.dirty = False
            ed.toast_msg("Guardado")
        except Exception as exc:                     # noqa: BLE001
            ed.toast_msg(f"Error: {exc}")

    # ------------------------------------------------------------------
    # Diálogo de cambios sin guardar
    # ------------------------------------------------------------------
    def _dispatch_dialog(self, button):
        d = self.dialog
        if button == LEFT:
            d.move(-1)
        elif button == RIGHT:
            d.move(1)
        elif button == A:
            self._a_consumed = True
            self._dialog_choose()
        elif button in (B, BACK):
            self._close_dialog()
        return True

    def _confirm(self, message, on_proceed):
        self.dialog = ConfirmDialog(message, _CONFIRM_OPTS, on_proceed,
                                    selected=len(_CONFIRM_OPTS) - 1)  # Cancelar
        self.root_layout.add_widget(self.dialog)

    def _close_dialog(self):
        if self.dialog is not None:
            self.root_layout.remove_widget(self.dialog)
            self.dialog = None

    def _dialog_choose(self):
        key = self.dialog.selected_key()
        proceed = self.dialog.on_proceed
        self._close_dialog()
        if key == "save":
            self._save()
            proceed()
        elif key == "discard":
            proceed()
        # "cancel": no hace nada

    def _request_exit(self):
        if self.dirty:
            self._confirm_exit()
        else:
            self.stop()

    def _confirm_exit(self):
        self._confirm("Cambios sin guardar.\n¿Salir de todas formas?",
                      on_proceed=self.stop)

    def _request_load(self, song_dir):
        if self.dirty and self.editor_screen.project is not None:
            self._confirm("Cambios sin guardar.\n¿Cargar otra canción?",
                          on_proceed=lambda: self.load_song(song_dir))
        else:
            self.load_song(song_dir)

    # ------------------------------------------------------------------
    # Reproducción (play/stop + playhead)
    # ------------------------------------------------------------------
    def _toggle_play(self):
        if self.player is None:
            return
        if self.player.playing:
            self.player.stop()
        else:
            # arranca desde la fila del cursor de SONG (como LGPT)
            self.player.play_from(self.editor_screen.song_grid.cursor_row)

    # -- mute (L2+S en SONG, estilo LGPT) ------------------------------
    def _playing_song(self):
        return (self.player is not None and self.player.playing
                and self.editor_screen.current == "song")

    def _set_mute(self, track, muted):
        eng = self.player.engine
        (eng.muted.add if muted else eng.muted.discard)(track)
        self.editor_screen.song_grid.set_muted(eng.muted)

    def _mute_start(self):
        if self._mute_combo is not None:
            return
        track = self.editor_screen.song_grid.cursor_track
        original = track in self.player.engine.muted
        self._set_mute(track, not original)          # toggle en vivo (preview)
        self._mute_combo = {"track": track, "original": original,
                            "committed": False}

    def _release_mute(self, button):
        combo = self._mute_combo
        if button == L2:
            # soltar Ctrl(L2) con S aún pulsada -> queda (commit)
            if B in self.held:
                combo["committed"] = True
        elif button == B:
            # soltar S antes -> revierte al estado anterior
            if not combo["committed"]:
                self._set_mute(combo["track"], combo["original"])
        remaining = self.held - {button}
        if L2 not in remaining and B not in remaining:
            self._mute_combo = None

    def _tick(self, _dt):
        ed = self.editor_screen
        p = self.player
        if p is not None and ed.current == "song":
            ed.song_grid.set_muted(p.engine.muted)   # refleja mutes en vivo
        playing = self.sm.current == "editor" and p is not None and p.playing
        if not playing:
            ed.song_grid.set_play([None] * 8)
            ed.chain_grid.set_play(None)
            ed.phrase_grid.set_play(None)
            return
        chans = p.engine.channels
        if ed.current == "song":
            ed.song_grid.set_play(
                [c.song_pos if c.playing else None for c in chans])
        elif ed.current == "chain":
            t = ed.chain_grid.track
            c = chans[t]
            ci = ed.chain_grid.chain_index()
            ed.chain_grid.set_play(
                c.chain_pos if (c.playing and c.chain == ci) else None)
        elif ed.current == "phrase":
            t = ed.phrase_grid.track
            c = chans[t]
            ph = ed.phrase_grid.pv.phrase_of(t) if ed.phrase_grid.pv else None
            ed.phrase_grid.set_play(
                c.phrase_pos if (c.playing and c.phrase == ph) else None)

    # ------------------------------------------------------------------
    def _mark_dirty(self):
        self.dirty = True

    def load_song(self, song_dir):
        project = load_project(song_dir)
        if self.player is not None:
            self.player.close()
        self.player = Player(project)
        self.editor_screen.enter_song(project, display_name(song_dir.name))
        self.dirty = False
        self.sm.current = "editor"


def main():
    parser = argparse.ArgumentParser(description="ROBOTRACKER2")
    parser.add_argument("--songs", default=str(DEFAULT_SONGS),
                        help="carpeta con las canciones LGPT")
    parser.add_argument("--fullscreen", action="store_true",
                        default=os.environ.get("ROBOTRACKER2_FULLSCREEN") == "1",
                        help="pantalla completa (Odin); en PC va en ventana")
    parser.add_argument("--samples", default=str(DEFAULT_SAMPLES),
                        help="biblioteca de samples para el navegador")
    parser.add_argument("--images", default=str(DEFAULT_IMAGES),
                        help="carpeta images/ para el navegador de pantalla")
    args = parser.parse_args()
    Robotracker2App(songs_dir=args.songs, fullscreen=args.fullscreen,
                    samples_dir=args.samples, images_dir=args.images).run()


if __name__ == "__main__":
    main()
