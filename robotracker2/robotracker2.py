"""ROBOTRACKER2 — clon de la interfaz de lgptclient, pantalla por pantalla.

App Kivy (misma estética que robotracker) sobre el motor de ../sinte.
Cargar canción → editor con navegación 2D de pantallas estilo LGPT.

Todos los controles pasan por `controls` (botones lógicos): en PC el teclado,
en la Odin 2 Portal el gamepad. La semántica LGPT (dpad = mover cursor, A+dir =
editar, L+dir = cambiar de pantalla, B = borrar, START = play, BACK = volver)
se resuelve aquí sobre botones lógicos.

Ejecutar:  robotracker2/.venv/bin/python robotracker2/robotracker2.py [--songs RUTA]
"""

import os

# Kivy escanea sys.argv él solo (getopt con sus propias -f/-p/--size/...) al
# importarse, ANTES de que nuestro propio argparse (más abajo) tenga ocasión
# de correr. Con argumentos que Kivy no reconoce (--samples, --images,
# --ayuda: los que pasa el launcher de la Odin) esto imprime su uso y mata el
# proceso — invisible en PC porque ahí se lanza sin argumentos extra. Hay que
# desactivarlo antes de la primera importación de kivy, sea cual sea.
os.environ.setdefault("KIVY_NO_ARGS", "1")

import argparse
import filecmp
import queue
import shutil
import time
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

from config import load_config, save_config
from controls import (A, B, BACK, DOWN, DPAD, L2, LEFT, R2, RIGHT, SELECT,
                      START, UP, GAMEPAD_BUTTONS, hat_to_buttons, key_to_button,
                      trigger_axis_buttons)
from lgpt_model import EMPTY, compact_instruments, compact_sequencer
from midi_ctrl import POTS_KNOBS, MidiControl
from midi_input import MidiNotesInput, midi_input_names
from sinte_bridge import save_project
try:
    from evdev_triggers import GamepadReader  # entrada evdev (Odin)
except ImportError:
    GamepadReader = None
from songs import DEFAULT_SONGS, display_name, find_songs, load_project
from player import Player
from robots import ROBOT_TRACK, RobotPlayback, screen_label
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
# ayuda_imagenes/ del repo: miniaturas YA renderizadas (bin/genera.py
# --markdown) para previsualizar sin recomponer nada a mano.
DEFAULT_AYUDA = DEFAULT_SONGS.parent.parent / "ayuda_imagenes"

# Opciones del diálogo de cambios sin guardar.
_CONFIRM_OPTS = [("save", "Guardar"), ("discard", "Descartar"),
                 ("cancel", "Cancelar")]
# Opciones del diálogo Sí/No (p. ej. borrar samples del disco).
_YES_NO_OPTS = [("yes", "Sí"), ("no", "No")]

# Botón lógico del dpad -> desplazamiento en la rejilla de pantallas (L+dir).
NAV_DELTA = {UP: (0, -1), DOWN: (0, 1), LEFT: (-1, 0), RIGHT: (1, 0)}


class Robotracker2App(App):
    title = "ROBOTRACKER2"

    def __init__(self, songs_dir=DEFAULT_SONGS, fullscreen=False,
                 samples_dir=DEFAULT_SAMPLES, images_dir=DEFAULT_IMAGES,
                 ayuda_dir=DEFAULT_AYUDA, pads_dir=None, **kwargs):
        super().__init__(**kwargs)
        self.songs_dir = songs_dir
        self.samples_dir = Path(samples_dir)
        # Biblioteca de samples de los pads (clave "pads" del robotraca.json
        # de cada canción, resuelta contra esta carpeta): pads/ en la raíz
        # del repo, p.ej. <repo>/pads con canciones en <repo>/sinte/songs
        # (Odin: /storage/pads con /storage/sinte/songs). Los pads NO tienen
        # configuración global: sin la clave "pads", la canción los tiene
        # vacíos. Si la biblioteca no existe se usa samples_dir (siguen
        # vacíos y el navegador enseña la biblioteca general).
        if pads_dir:
            self.pads_dir = Path(pads_dir)
        else:
            songs = Path(songs_dir).resolve()
            self.pads_dir = next(
                (p for p in (songs.parent.parent / "pads",
                             songs.parent / "pads",
                             self.samples_dir.parent / "pads")
                 if p.is_dir()), self.samples_dir)
        self.images_dir = Path(images_dir)
        self.ayuda_dir = Path(ayuda_dir)
        self.browser = None        # SampleBrowser/ImageBrowser activo (o None)
        self._screen_step = None   # step de PHRASE que se está editando
        self._pads_pad = None      # pad (1-4) al que apunta el navegador PADS
        self._pads_dirty = False   # pads de la canción sin guardar (memoria)
        self._pots_dirty = False   # knobs de la canción sin guardar (memoria)
        self._mute_dirty = False   # mute de canales sin guardar (robotraca)
        self.fullscreen = fullscreen
        self.held = set()          # botones lógicos pulsados ahora
        self._trig_buttons = set()  # gatillos (ejes) actualmente "pulsados"
        self._ev_pad = None       # GamepadReader evdev (modo Odin) o None
        self.dirty = False
        self._a_consumed = False   # A se usó en un acorde (no disparar tap)
        self.dialog = None         # ConfirmDialog activo (o None)
        self.player = None         # reproductor de la canción cargada
        self._song_dir = None      # directorio de la canción cargada
        self._play_start = None    # monotonic() al arrancar (temporizador)
        self._play_keys = [None] * 8  # (phrase, step) por canal: pulso SONG
        self._robot_play = RobotPlayback()  # SCREEN sostenida + HIT del canal 8
        self._pad_hits = queue.SimpleQueue()  # pads MIDI -> destello en _tick
        self._fresh_press = False  # el botón actual no estaba ya en self.held
        self.midi_live = False     # pintado MIDI en vivo en PHRASE (R2+START)
        self._midi_notes = MidiNotesInput()
        self._midi_ctrl = None     # controlador MIDI (botones+knobs, mixer)

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
                                          ayuda_dir=self.ayuda_dir,
                                          name="editor")
        # Configuración global (interfaces MIDI) persistida entre ejecuciones.
        self.config = load_config()
        self.editor_screen.set_config(self.config, on_change=self._config_changed)

        # Controlador MIDI del reproductor (botones + knobs), como el mixer:
        # los botones llegan a ui_queue (drenada en _tick) y los knobs se
        # reconfiguran por canción desde robotraca.json (MidiControl.set_song).
        self._midi_ctrl = MidiControl(
            self.config.get("buttons") or {},
            self.config.get("hw_pots") or {},
            self.config.get("pad_volume", 45),
            pads_dir=self.pads_dir,
            on_trigger=self._ensure_pad_audio)
        if self.config.get("midi_control"):
            self._midi_ctrl.open(self.config["midi_control"])
        self.sm.add_widget(self.load_screen)
        self.sm.add_widget(self.editor_screen)
        self.sm.current = "load"


        self.root_layout = FloatLayout()
        self.root_layout.add_widget(self.sm)

        Window.bind(on_key_down=self._on_key_down, on_key_up=self._on_key_up)
        Window.bind(on_request_close=self._on_request_close)
        self._hat_buttons = set()
        if os.environ.get("ROBOTRACKER2_EVDEV_GAMEPAD"):
            # Odin 2 (ROCKNIX): InputPlumber oculta el mando a SDL; toda la
            # entrada (cruceta, stick, botones, gatillos) llega en su
            # DualSense virtual, que se lee aquí por evdev
            # (evdev_triggers.py). El teclado sigue enlazado: según el
            # perfil activo de InputPlumber puede traducir a teclas, pero en
            # el perfil por defecto no emite nada. Sin joystick nativo: con
            # el mando oculto no hay nada que ver, y si algún día SDL viera
            # el DualSense virtual duplicaría la entrada.
            if GamepadReader is not None:
                self._ev_pad = GamepadReader(
                    on_event=lambda b, p: Clock.schedule_once(
                        lambda _dt: self._on_evdev_button(b, p), 0))
                self._ev_pad.start()
        else:
            # Gamepad (Odin 2 Portal); inofensivo si no hay mando conectado.
            Window.bind(on_joy_button_down=self._on_joy_button_down,
                        on_joy_button_up=self._on_joy_button_up,
                        on_joy_hat=self._on_joy_hat,
                        on_joy_axis=self._on_joy_axis)
        Clock.schedule_interval(self._tick, 1 / 30)   # playhead
        return self.root_layout

    # ------------------------------------------------------------------
    # Entrada -> botones lógicos
    # ------------------------------------------------------------------
    def _on_key_down(self, _win, key, _scancode, codepoint, _modifiers):
        button = key_to_button(key, codepoint)
        if button is None:
            return False
        # Distingue una pulsación nueva de la repetición que manda el SO al
        # mantener la tecla (p.ej. para no alternar el mute varias veces
        # solo por mantener S pulsada).
        self._fresh_press = button not in self.held
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
        self._fresh_press = button not in self.held
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
        self.held.discard(button)
        if self.dialog is not None:
            self._a_consumed = False
            return
        # A soltado sin haberse usado en un acorde -> "tap". Pero si se suelta
        # con un hombro (L2/R2) mantenido, no es un tap: es el final de un
        # combo (p.ej. L2+B+A), y soltar A no debe disparar copiar/pegar/00
        # sobre la celda (eso "cortaría" la celda seleccionada).
        if button == A:
            if (not self._a_consumed and self.sm.current == "editor"
                    and not (L2 in self.held or R2 in self.held)):
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
        if self._session_dirty() \
                and self.dialog is None \
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

    def _on_joy_axis(self, _win, _stick, axisid, value):
        # Gatillos analógicos L2/R2: ejes del joystick nativo. Cada eje de
        # gatillo genera press/release al cruzar el umbral, como un botón
        # (los ejes de los sticks no se mapean y se ignoran aquí).
        new = trigger_axis_buttons(axisid, value)
        for b in new - self._trig_buttons:
            self._fresh_press = b not in self.held
            self.held.add(b)
            self._dispatch(b, set(self.held))
        for b in self._trig_buttons - new:
            self.held.discard(b)
            self._release(b)
        self._trig_buttons = new
        return True

    def _on_evdev_button(self, button, pressed):
        # Entrada leída por evdev (GamepadReader, Odin): transiciones ya
        # filtradas (umbrales/histéresis) desde el hilo lector. Misma
        # semántica que _on_joy_axis (press/release como botón).
        if pressed:
            self._fresh_press = button not in self.held
            self.held.add(button)
            self._dispatch(button, set(self.held))
            self._trig_buttons = self._trig_buttons | {button}
        else:
            self._trig_buttons = self._trig_buttons - {button}
            self.held.discard(button)
            self._release(button)
        return True

    # ------------------------------------------------------------------
    # Semántica (sobre botones lógicos)
    # ------------------------------------------------------------------
    def _dispatch(self, button, active):
        # Cualquier otro botón pulsado mientras A está mantenido consume el
        # tap de A: si no, al soltar A luego se resuelve como "tap" (copiar/
        # pegar/valor por defecto) sobre lo que haya quedado tras el combo
        # (p.ej. A+S borra y, sin esto, el tap de A repone un valor encima).
        if A in active and button != A:
            self._a_consumed = True
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
            if R2 in active:                # R2+START: pintado MIDI en vivo
                self._toggle_midi_live()    # (no toca play/stop)
            else:
                self._toggle_play()
            return True
        if ed.current == "pots":
            return self._dispatch_pots(button, active)
        if ed.current == "pads":
            return self._dispatch_pads(button, active)
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
        if ed.current == "config":
            return self._dispatch_config(button, active)
        if ed.current == "live":
            return self._dispatch_live(button, active)
        if button == BACK:
            self.sm.current = "load"
            return True
        return False

    # ------------------------------------------------------------------
    # Pantalla EFECTOS (knobs por canción, ver screens/pots_view.py)
    # ------------------------------------------------------------------
    def _dispatch_pots(self, button, active):
        g = self.editor_screen.pots_grid
        if g.picker is not None:
            # Lista de efectos abierta (A sobre la columna EFECTO): arr/abj
            # mueve el cursor, A elige, B cierra. El resto no hace nada.
            if button in (UP, DOWN):
                g.picker_move(-1 if button == UP else 1)
                return True
            if button == A:
                if L2 in active or R2 in active:  # L2 navega: A no hace nada
                    self._a_consumed = True
                else:
                    self._midi_ctrl.set_pot_efecto_nombre(
                        POTS_KNOBS[g.cursor], g.picker_selected())
                    g.set_state(self._midi_ctrl.pots_state())
                    g.close_picker()
                    self._pots_dirty = True
                    self._sync_unsaved()
                return True
            if button == B:
                if L2 not in active and R2 not in active:
                    g.close_picker()
                return True
            return True
        if g.cursor == g.SAVE_ROW:
            # Fila GUARDAR (abajo del todo): arr/abj la abandonan, solo A
            # guarda; el resto no hace nada (select ya no guarda).
            if button in (UP, DOWN):
                g.move(button)
                return True
            if button == A:
                if L2 in active or R2 in active:  # L2 navega: A no hace nada
                    self._a_consumed = True
                else:
                    self._pots_save()
            return True
        pot = POTS_KNOBS[g.cursor]
        # A + dpad: edita la celda (CANAL / EFECTO / % según la columna).
        # El tap de A ya queda consumido en _dispatch por el acorde.
        if button in DPAD and A in active:
            return self._pots_combo(pot, g.col, button)
        if button in DPAD:
            if button in (LEFT, RIGHT):
                g.move_col(-1 if button == LEFT else 1)
            else:
                g.move(button)
            return True
        if button == A:
            if L2 in active or R2 in active:      # L2 navega: A no hace nada
                self._a_consumed = True
            elif g.col == 1:                      # columna EFECTO: la lista
                g.open_picker()
            return True
        if button == SELECT:
            return True                           # no guarda: fila GUARDAR
        # BACK (y el resto) caen al handler genérico del editor: volver a la
        # lista de carga.
        return False

    def _pots_combo(self, pot, col, dpad):
        """A+dpad sobre la celda (la columna activa): CANAL y EFECTO
        ciclan con cualquier dirección; % usa izq/dcha fino y arr/abj
        de 10 en 10. En memoria + en vivo. La lista de efectos se abre
        con A (tap), no con A+dir."""
        g = self.editor_screen.pots_grid
        if col == 0:
            delta = 1 if dpad in (UP, RIGHT) else -1
            self._midi_ctrl.set_pot_canal(pot, delta)
        elif col == 1:
            delta = 1 if dpad in (UP, RIGHT) else -1
            self._midi_ctrl.set_pot_efecto(pot, delta)
        else:
            delta = {LEFT: -1, RIGHT: 1, UP: 10, DOWN: -10}[dpad]
            self._midi_ctrl.set_pot_mix(pot, delta)
        g.set_state(self._midi_ctrl.pots_state())
        self._pots_dirty = True
        self._sync_unsaved()
        return True

    def _pots_save(self):
        """Guarda los knobs en memoria al robotraca.json de la canción. Los
        cambios de EFECTOS no se persisten al instante: viven en el cfg y en
        el engine hasta la fila GUARDAR (A sobre ella) o hasta guardar la
        canción (_save)."""
        self._midi_ctrl.save()
        self._pots_dirty = False
        self._sync_unsaved()
        self.editor_screen.toast_msg("Efectos guardados")

    # ------------------------------------------------------------------
    # Pantalla PADS (pads sampler por canción, ver screens/pads_view.py)
    # ------------------------------------------------------------------
    def _dispatch_pads(self, button, active):
        g = self.editor_screen.pads_grid
        if g.cursor == g.SAVE_ROW:
            # Fila GUARDAR (abajo del todo): arr/abj la abandonan, solo A
            # guarda; el resto no hace nada (select ya no guarda los pads).
            if button in (UP, DOWN):
                g.move(button)
                return True
            if button == A:
                if L2 in active or R2 in active:  # L2 navega: A no hace nada
                    self._a_consumed = True
                else:
                    self._pads_save()
            return True
        pad = g.cursor + 1                       # cursor 0-based -> pad 1-4
        if button in DPAD:
            if button in (LEFT, RIGHT):
                self._pads_volume(pad, -5 if button == LEFT else 5)
            else:
                g.move(button)
            return True
        if button == A:
            if L2 in active or R2 in active:      # L2 navega: A no hace nada
                self._a_consumed = True
            else:
                self._open_pads_browser(pad)
            return True
        if button == B:
            if L2 not in active and R2 not in active:
                self._pads_clear(pad)
            return True
        if button == SELECT:
            return True                           # ya no guarda: fila GUARDAR
        # BACK (y el resto) caen al handler genérico del editor: volver a la
        # lista de carga.
        return False

    def _pads_volume(self, pad, delta):
        pct = self._midi_ctrl.pads_state()[pad - 1][1] + delta
        self._midi_ctrl.set_pad_volume(pad, max(0, min(100, pct)))
        self.editor_screen.pads_grid.set_state(self._midi_ctrl.pads_state())
        self._pads_dirty = True
        self._sync_unsaved()

    def _pads_clear(self, pad):
        self._midi_ctrl.assign_pad(pad, None)
        self.editor_screen.pads_grid.set_state(self._midi_ctrl.pads_state())
        self.editor_screen.toast_msg(f"PAD {pad}: sin sample")
        self._pads_dirty = True
        self._sync_unsaved()

    def _ensure_pad_audio(self, pad_idx=None):
        """Los pads suenan aunque la canción no esté reproduciéndose: su
        Voice se renderiza en el callback del stream, así que basta con
        que el stream exista. Se crea perezoso (aquí, al disparar un pad
        desde el callback MIDI), no al cargar la canción."""
        if self.player is not None:
            self.player._ensure_stream()
        if pad_idx is not None:
            self._pad_hits.put(pad_idx)

    def _pads_save(self):
        """Guarda los pads en memoria al robotraca.json de la canción. Los
        cambios de PADS no se persisten al instante: viven en el cfg y en
        el engine hasta la fila GUARDAR (A sobre ella) o hasta guardar la
        canción (_save)."""
        self._midi_ctrl.save()
        self._pads_dirty = False
        self._sync_unsaved()
        self.editor_screen.toast_msg("Pads guardados")

    def _open_pads_browser(self, pad):
        """Navegador de samples para el pad: enseña la biblioteca de pads
        (pads/, solo samples de pads, no la biblioteca general) y la carga
        asigna al pad (clave "pads" de la canción)."""
        self._pads_pad = pad
        root = self.pads_dir if self.pads_dir.is_dir() \
            else self.editor_screen.project.dir / "samples"
        self._open_browser(SampleBrowser(
            root, on_load=self._pads_sample_loaded,
            on_close=self._close_browser,
            on_toast=self.editor_screen.toast_msg))

    def _pads_sample_loaded(self, path):
        # El WAV ya está en la biblioteca de pads: se referencia por su
        # nombre relativo a ella (p.ej. "Distorted metal/Dip Spit.wav"),
        # sin copiarlo a la canción.
        path = Path(path)
        try:
            name = path.relative_to(self.pads_dir).as_posix()
        except ValueError:                       # navegador en fallback
            name = path.name
        self._midi_ctrl.assign_pad(self._pads_pad, name)
        self.editor_screen.pads_grid.set_state(self._midi_ctrl.pads_state())
        # sin self.dirty (el robotraca.json no es el lgptsav.dat): la
        # asignación queda en memoria hasta guardar (fila GUARDAR o Guardar)
        self._pads_dirty = True
        self._sync_unsaved()
        self.editor_screen.toast_msg(f"PAD {self._pads_pad}: {name}")
        self._close_browser()


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
            if R2 in active:                         # Ctrl+A: duplicar / pegar
                if g.has_selection:
                    g.duplicate_phrase()
                else:
                    g.paste_block()
                self._a_consumed = True
            elif L2 in active:                       # L2 es navegar: A no hace nada
                self._a_consumed = True
            else:
                self._a_consumed = False             # A tap: copiar/pegar/00
            return True
        if button == B:
            if L2 in active:                         # L2 es navegar: B no hace nada
                pass
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
            if R2 in active:                         # Ctrl+A: duplicar / pegar
                if g.has_selection:
                    g.duplicate_chain()
                else:
                    g.paste_block()
                self._a_consumed = True
            elif L2 in active:                       # L2 es navegar: A no hace nada
                self._a_consumed = True
            else:
                self._a_consumed = False             # A tap: se resuelve al soltar
            return True
        if button == L2:                             # L2(+S): mute mientras suena

            if B in active and self._playing_song() and self._fresh_press:
                self._mute_toggle(g.cursor_track)
            return True
        if button == B:
            if L2 in active:                         # L2(+S): mute (o nada)
                if self._playing_song() and self._fresh_press:
                    self._mute_toggle(g.cursor_track)
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
            if R2 in active:                         # Ctrl+A: cortar / pegar
                g.cut_selection() if g.has_selection else g.paste_block()
                self._a_consumed = True
            elif L2 in active:                       # L2 es navegar: A no hace nada
                self._a_consumed = True
            else:
                self._a_consumed = False             # A tap: copiar/pegar/def
            return True
        if button == B:
            if L2 in active:                         # L2 es navegar: B no hace nada
                pass
            elif R2 in active:                       # Ctrl+S: ciclar selección
                g.cycle_selection()
            elif g.has_selection:                    # S: copiar selección
                g.copy_selection()
            else:                                    # S: borrar campo
                g.delete()
            return True
        if button == BACK:
            if g.has_selection:
                g.cancel_selection()
            else:
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
            if A in active:
                m.edit(button)     # A+arr/abj paso grande, A+izq/dcha fino
                self._a_consumed = True
            else:
                m.move(button)     # arr/abj fila, izq/dcha pareja (solo foco)
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
    # move(button), activate(), back(), cleanup(). SampleBrowser añade
    # go_back()/go_forward() (historial de carpetas, flechas izq/dcha);
    # ImageBrowser no los tiene y las flechas no hacen nada allí.
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
                                         on_close=self._close_browser,
                                         on_toast=self.editor_screen.toast_msg))

    def _dispatch_browser(self, button):
        b = self.browser
        if button in (UP, DOWN):
            b.move(button)
        elif button == A:
            b.activate()
        elif button == LEFT:
            go_back = getattr(b, "go_back", None)
            if go_back is not None:
                go_back()
        elif button == RIGHT:
            go_forward = getattr(b, "go_forward", None)
            if go_forward is not None:
                go_forward()
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
        dest, notice = resolve_sample_import(path, project.dir / "samples")
        try:
            dest.parent.mkdir(exist_ok=True)
            if dest.resolve() != Path(path).resolve():
                shutil.copy2(path, dest)
        except OSError as exc:                   # noqa: BLE001
            self.editor_screen.toast_msg(f"Error: {exc}")
            self._close_browser()
            return
        name = dest.name
        self.editor_screen.instrument_menu.set_sample(name)
        self._mark_dirty()
        self.editor_screen.toast_msg(notice or f"Sample: {name}")
        self._close_browser()

    def _open_screen_browser(self, step):
        self._screen_step = step
        self._open_browser(ImageBrowser(self.images_dir, ayuda_dir=self.ayuda_dir,
                                        on_load=self._load_screen,
                                        on_close=self._close_browser))

    def _load_screen(self, cc, value):
        self.editor_screen.phrase_grid.set_screen(self._screen_step, cc, value)
        self._mark_dirty()
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

    def _dispatch_config(self, button, active):
        m = self.editor_screen.config_menu
        if button == UP:
            m.move(-1)
        elif button == DOWN:
            m.move(1)
        elif button in (LEFT, RIGHT):
            m.adjust(1 if button == RIGHT else -1, coarse=(A in active))
            if A in active:
                self._a_consumed = True
        elif button == B:
            m.clear()                                # poner a "ninguna"
        elif button == BACK:
            self.sm.current = "load"
        else:
            return False
        return True

    def _dispatch_live(self, button, active):
        """Solo lectura: dpad/A/B no editan; BACK vuelve a la lista."""
        if button == BACK:
            self.sm.current = "load"
            return True
        return True

    def _config_changed(self):
        """Persiste la configuración global (interfaces MIDI) al cambiar."""
        if self.midi_live:        # la interfaz puede haber cambiado: apaga
            self._set_midi_live(False)   # el modo (el usuario lo re-arma)
        # La interfaz de control puede haber cambiado: reabrir (barato;
        # los knobs/botones siguen la lista del engine por referencia).
        if self._midi_ctrl is not None:
            self._midi_ctrl.open(self.config.get("midi_control"))
        save_config(self.config)

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
        elif key == "compact_seq":
            self._compact_sequencer()
        elif key == "compact_instr":
            self._compact_instruments()


    def _save(self):
        """Guarda la canción (lgptsav.dat) y el robotraca.json (mute de
        SONG y, si hay, pads/knobs en memoria)."""
        ed = self.editor_screen
        try:
            save_project(ed.project)
            self.dirty = False
            msg = "Guardado"
        except Exception as exc:                     # noqa: BLE001
            msg = f"Error: {exc}"
        self._midi_ctrl.sync_mute()
        if self._pads_dirty or self._pots_dirty or self._mute_dirty:
            extra = []
            if self._pads_dirty or self._pots_dirty:
                extra.append("pads/knobs")
            if self._mute_dirty:
                extra.append("mute")
            self._midi_ctrl.save()
            self._pads_dirty = False
            self._pots_dirty = False
            self._mute_dirty = False
            msg += " + " + "/".join(extra)
        self._sync_unsaved()
        ed.toast_msg(msg)

    # ------------------------------------------------------------------
    # Compact (menú PROJECT)
    # ------------------------------------------------------------------
    def _compact_sequencer(self):
        """Compact Sequencer: borra in-place las chains/phrases sin uso
        (semántica del LGPT original, sin renumerar). Directo, sin diálogo."""
        ed = self.editor_screen
        project = ed.project
        if project is None:
            return
        self._stop_play()        # no borrar chains/phrases en uso por el player
        n_c, n_p = compact_sequencer(project)
        self._mark_dirty()
        if n_c or n_p:
            ed.toast_msg(f"Compact: {n_c} chains, {n_p} phrases")
        else:
            ed.toast_msg("Compact: nada que purgar")

    def _compact_instruments(self):
        """Compact Instruments: elimina del banco los instrumentos sin
        referencia (ROBOT_INSTR 0x80 nunca) y, si quedan wavs huérfanos en
        samples/, pregunta si borrarlos del disco (Sí/No, "No" por defecto)."""
        ed = self.editor_screen
        project = ed.project
        if project is None:
            return
        self._stop_play()
        n, unused = compact_instruments(project)
        self._mark_dirty()
        ed.instrument_menu.set_project(project)   # re-cachea instr_ids
        ed.refresh_header()
        if n:
            ed.toast_msg(f"Compact: {n} instrumentos")
        else:
            ed.toast_msg("Compact: nada que purgar")
        if unused:
            self._confirm(
                f"Borrar del disco {len(unused)} samples sin usar?",
                lambda key: self._purge_unused_samples(unused, key),
                opts=_YES_NO_OPTS)

    def _purge_unused_samples(self, names, key):
        """Borra de <song>/samples/ los wavs sin usar (solo si el diálogo
        respondió "Sí"). La lista sale del glob del propio directorio, así
        que unlink no puede salirse de él."""
        if key != "yes":
            return
        samples = self.editor_screen.project.dir / "samples"
        removed = 0
        for name in names:
            try:
                (samples / name).unlink()
                removed += 1
            except OSError:
                continue
        self.editor_screen.toast_msg(f"Samples borrados: {removed}")

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

    def _confirm(self, message, on_proceed, opts=None):
        if opts is None:
            opts = _CONFIRM_OPTS
        self.dialog = ConfirmDialog(message, opts, on_proceed,
                                    selected=len(opts) - 1)  # última (segura)
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
        elif key != "cancel":
            proceed(key)          # diálogos con opciones propias (Sí/No)

    def _request_exit(self):
        if self._session_dirty():
            self._confirm_exit()
        else:
            self.stop()

    def _confirm_exit(self):
        self._confirm("Cambios sin guardar.\n¿Salir de todas formas?",
                      on_proceed=self.stop)

    def _request_load(self, song_dir):
        if self._session_dirty() \
                and self.editor_screen.project is not None:
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
            self._stop_play()
            return
        ed = self.editor_screen
        if ed.current == "chain":
            # play de la chain del cursor, en bucle
            ci = ed.chain_grid.chain_index()
            if ci is None:
                return
            ok = self.player.play_loop("chain", ed.chain_grid.track, ci)
        elif ed.current == "phrase":
            # play de la phrase del cursor, en bucle
            pi = ed.phrase_grid.pv.phrase_of(ed.phrase_grid.track) \
                if ed.phrase_grid.pv else None
            if pi is None:
                return
            ok = self.player.play_loop("phrase", ed.phrase_grid.track, pi)
        else:
            # arranca desde la fila del cursor de SONG: el engine solo
            # arranca los canales que tienen algo en esa fila
            ok = self.player.play_from(ed.song_grid.cursor_row)
        if ok:
            self._play_start = time.monotonic()
            self.editor_screen.set_play_indicator(True, 0)

    def _stop_play(self):
        """Para la reproducción (botón stop del controlador MIDI)."""
        if self.player is None:
            return
        self.player.stop()
        self._play_start = None
        self.editor_screen.set_play_indicator(False)

    # -- controlador MIDI del reproductor (botones, como el mixer) ---------
    def _midi_action(self, accion):
        """Traduce una acción del controlador MIDI (up/down/play/stop) a la
        misma acción que en el player. sampleN no llega aquí: el callback
        MIDI dispara los pads del engine directamente (ver midi_ctrl)."""
        if accion == "play":
            self._toggle_play()
        elif accion == "stop":
            self._stop_play()
        elif accion in ("up", "down"):
            self._midi_song_step(-1 if accion == "up" else 1)

    def _midi_song_step(self, delta):
        """Canción anterior/siguiente con up/down del controlador (como la
        lista del player). En la pantalla de carga mueve el cursor y carga
        la seleccionada."""
        if not self.songs:
            return
        if self._song_dir is not None and self._song_dir in self.songs:
            idx = (self.songs.index(self._song_dir) + delta) % len(self.songs)
            self._request_load(self.songs[idx])
        else:                       # pantalla de carga (sin canción)
            self.load_screen.move(delta)
            self._request_load(self.load_screen.selected())


    # -- mute (L2+S en SONG, estilo LGPT) ------------------------------
    def _playing_song(self):
        return (self.player is not None and self.player.playing
                and self.editor_screen.current == "song")

    def _set_mute(self, track, muted):
        eng = self.player.engine
        (eng.muted.add if muted else eng.muted.discard)(track)
        self.editor_screen.song_grid.set_muted(eng.muted)
        self._midi_ctrl.sync_mute()
        self._mute_dirty = True
        self._sync_unsaved()

    def _mute_toggle(self, track):
        """L2+S: cada pulsación NUEVA de S (no la repetición del SO al
        mantenerla) alterna el mute de `track` ahí mismo. No hay "revertir":
        lo que quede en el momento de soltar Ctrl es lo que se queda —
        no hace falta más lógica al soltar ninguna de las dos teclas."""
        self._set_mute(track, track not in self.player.engine.muted)

    # ------------------------------------------------------------------
    # Pintado MIDI en vivo en PHRASE (R2+START)
    # ------------------------------------------------------------------
    def _toggle_midi_live(self):
        """Alterna el modo de pintar notas MIDI en la phrase mientras suena.

        Requiere una interfaz 'MIDI Notas' configurada (CONFIG) y disponible.
        Con el modo activo, las notas del controlador se pintan en el step
        del playhead de la phrase en edición (nota + velocidad vía VOLM) —
        ver PhraseGrid.live_note. R2+START no toca play/stop.
        """
        if not self._fresh_press:       # repetición del SO: no re-alternar
            return
        ed = self.editor_screen
        if self.midi_live:
            self._set_midi_live(False)
            ed.toast_msg("MIDI live: OFF")
            return
        port = self.config.get("midi_notes")
        if not port:
            ed.toast_msg("Configura 'MIDI Notas' en CONFIG")
            return
        if port not in midi_input_names():
            ed.toast_msg("Interfaz MIDI Notas no disponible")
            return
        if not self._midi_notes.open_port(port):
            ed.toast_msg(f"Error MIDI: {self._midi_notes.error}")
            return
        self._set_midi_live(True)
        ed.toast_msg("MIDI live: ON (pinta en PHRASE al sonar)")

    def _set_midi_live(self, on):
        self.midi_live = on
        self.editor_screen.set_midi_live(on)
        if not on:
            self._midi_notes.close()

    def _paint_midi_notes(self):
        """Pinta en la phrase del playhead las notas MIDI pendientes.

        Solo cuando: modo vivo activo, hay play, se está en PHRASE, y la
        phrase que suena es la que se está editando (si se navegó a otra
        phrase distinta de la que toca el canal, no se pinta nada)."""
        notes = self._midi_notes.poll()
        if not notes:
            return
        if self.player is None or not self.player.playing:
            return
        ed = self.editor_screen
        if ed.current != "phrase":
            return
        g = ed.phrase_grid
        if g.pv is None:
            return
        t = g.track
        c = self.player.engine.channels[t]
        ph = g.pv.phrase_of(t)
        if not (c.playing and c.phrase == ph):
            return          # la phrase que suena no es la que se edita
        step = c.phrase_pos
        for note, vel in notes:
            g.live_note(step, note, vel)

    def _tick(self, dt):
        for accion in self._midi_ctrl.drain():
            self._midi_action(accion)
        if self.midi_live:
            self._paint_midi_notes()
        ed = self.editor_screen
        p = self.player
        while True:
            try:
                ed.pads_grid.hit(self._pad_hits.get_nowait())
            except queue.Empty:
                break
        if self._midi_ctrl is not None:
            ed.pots_grid.set_live(self._midi_ctrl.live_pot_cc())
        ed.pads_grid.tick_pulse(dt)
        if p is not None and ed.current == "song":
            ed.song_grid.set_muted(p.engine.muted)   # refleja mutes en vivo
        playing = self.sm.current == "editor" and p is not None and p.playing
        if playing and self._play_start is not None:
            ed.set_play_indicator(True,
                                  time.monotonic() - self._play_start)
        else:
            ed.set_play_indicator(False)
        if not playing:
            ed.song_grid.set_play([None] * 8)
            ed.song_grid.clear_pulse()
            ed.chain_grid.set_play(None)
            ed.phrase_grid.set_play(None)
            self._play_keys = [None] * 8
            if (self._robot_play.playing or self._robot_play.cc is not None
                    or self._robot_play.note is not None
                    or self._robot_play.hit_note is not None):
                self._robot_play.reset()
                ed.live_grid.reset()
            elif ed.current == "live":
                ed.live_grid.tick_pulse(dt)
            return
        chans = p.engine.channels
        hits = self._song_hits(p.engine)
        self._robot_play.update(p.engine)
        if ed.current == "live":
            ed.live_grid.set_from(self._robot_play)
            ed.live_grid.tick_pulse(dt)
        if ed.current == "song":
            ed.song_grid.set_play(
                [c.song_pos if c.playing else None for c in chans])
            ed.song_grid.tick_pulse(dt, hits)
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

    def _song_hits(self, engine):
        """Canales que acaban de avanzar a un step con nota (o MDCC en robotas)."""
        hits = []
        notes = engine.project.notes
        cmd1 = engine.project.cmd1
        n = len(notes)
        for i, ch in enumerate(engine.channels):
            if not ch.playing or ch.phrase == 0xFF:
                self._play_keys[i] = None
                continue
            key = (ch.phrase, ch.phrase_pos)
            if key == self._play_keys[i]:
                continue
            self._play_keys[i] = key
            row = ch.phrase * 16 + ch.phrase_pos
            if row >= n:
                continue
            if notes[row] != EMPTY:
                hits.append(i)
            elif i == ROBOT_TRACK and cmd1[row] == "MDCC":
                hits.append(i)
        return hits

    # ------------------------------------------------------------------
    def _session_dirty(self):
        return self.dirty or self._pads_dirty or self._pots_dirty \
            or self._mute_dirty

    def _sync_unsaved(self):
        """Asterisco en cabecera si hay cambios de canción, pads o knobs."""
        self.editor_screen.set_unsaved(self._session_dirty())

    def _mark_dirty(self):
        self.dirty = True
        self._sync_unsaved()

    def load_song(self, song_dir):
        project = load_project(song_dir)
        if self.player is not None:
            self.player.close()
        # Sin banco global de pads: los pads son SOLO por canción
        # (robotraca.json "pads" contra la biblioteca pads/, aplicado en
        # _midi_ctrl.set_song); el engine se crea sin wavs_dir.
        self.player = Player(project)
        # Controlador MIDI del reproductor: aplica el robotraca.json de la
        # canción (mute/vocoder/presence/fx/fx_mix/master/pad_volume/pads)
        # al engine y reconfigura los knobs a sus targets de esa canción.
        self._midi_ctrl.set_song(self.player.engine, song_dir)
        self._song_dir = song_dir
        self._play_start = None
        self._robot_play.reset()
        self.editor_screen.live_grid.reset()
        self.dirty = False
        self._pads_dirty = False
        self._pots_dirty = False
        self._mute_dirty = False
        self.editor_screen.set_play_indicator(False)
        self.editor_screen.enter_song(project, display_name(song_dir.name))
        # PADS/POTS: estado de esta canción (robotraca.json "pads" y
        # "pots"/"fx_mix"; sin la clave, vacíos — no hay banco global)
        self.editor_screen.pads_grid.set_state(self._midi_ctrl.pads_state())
        self.editor_screen.pots_grid.set_state(self._midi_ctrl.pots_state())
        self._sync_unsaved()
        self.sm.current = "editor"

    def on_stop(self):
        """Al salir, cierra audio, MIDI y evdev (si hay algo abierto)."""
        if self.player is not None:
            self.player.close()
            self.player = None
        if self._ev_pad is not None:
            self._ev_pad.stop()
        self._midi_notes.close()
        if self._midi_ctrl is not None:
            self._midi_ctrl.close()


def resolve_sample_import(src, dest_dir):
    """Destino en `dest_dir` para importar el WAV `src`.

    Devuelve `(ruta_destino, aviso_o_None)`. El caller copia si origen y
    destino no son el mismo fichero. Si ya hay un WAV con el mismo nombre
    y contenido distinto, usa `stem_2.wav`, `stem_3.wav`… y un aviso: no
    asigna en silencio el sample que ya estaba en la canción.
    """
    src = Path(src)
    dest_dir = Path(dest_dir)
    dest = dest_dir / src.name
    if not dest.exists():
        return dest, None
    try:
        if dest.resolve() == src.resolve():
            return dest, None
    except OSError:
        pass
    try:
        if filecmp.cmp(src, dest, shallow=False):
            return dest, None
    except OSError:
        pass
    stem, suffix = dest.stem, dest.suffix
    n = 2
    while True:
        candidate = dest_dir / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate, (
                f"Ya existía {src.name}; importado como {candidate.name}")
        n += 1


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
    parser.add_argument("--ayuda", default=str(DEFAULT_AYUDA),
                        help="carpeta ayuda_imagenes/ (miniaturas ya renderizadas)")
    args = parser.parse_args()
    Robotracker2App(songs_dir=args.songs, fullscreen=args.fullscreen,
                    samples_dir=args.samples, images_dir=args.images,
                    ayuda_dir=args.ayuda).run()


if __name__ == "__main__":
    main()
