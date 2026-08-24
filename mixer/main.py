#!/usr/bin/env python3
"""Mixer: editor visual de robotraca.json con el engine de sinte embebido.

App Kivy standalone: no hay servidor ni red; `backend.MixerBackend` crea el
Player de sinte en este proceso (misma carga de canciones, mismo
robotraca.json, misma salida de audio, mismo controlador MIDI físico) y la
UI lo conduce. Sirve para probar y configurar cada canción: lista de
canciones, mute/vocoder/presence por canal, a qué apunta cada knob y
master; Guardar escribe el robotraca.json. El campo "fx" del JSON (niveles
de efecto por canal) ya no se edita desde el mixer, pero se conserva al
guardar; en su lugar hay un único osciloscopio de la mezcla final
(`MixScope`).

Sin controles en vivo duplicados: el transporte (canción anterior/
siguiente, play/pausa, stop) y los pads de WAV los dispara el controlador
MIDI físico exactamente igual que en el player real (mismos botones del
TOML, ver `lgpt_player.open_midi_input`); el mixer solo traduce las
acciones de transporte que llegan por `Player.ui_queue` a las mismas
llamadas de `MixerBackend` (ver `_bucle`/`_boton_fisico`). Los knobs
físicos ya escriben en el engine en vivo por su cuenta (vía
`args.pots`/`match_pot`, configurado por knob con `on_knob_param`/
`on_knob_canal`); el mixer no necesita reenviar nada de eso.

Lo que PERSISTE en el modelo (toggles, MASTER, POT, SAVE) se re-sincroniza
entero con `get_config()` tras arrancar, tras cambiar de canción y tras
guardar: la UI no guarda estado propio de la config, el backend es la
fuente de verdad.

Arquitectura: un único hilo trabajador ejecuta las llamadas al backend en
orden (cola FIFO), sondea `state()` cada ~250 ms y drena los botones
físicos pendientes (`drain_buttons()`); los resultados llegan a la UI por
`Clock.schedule_once`. Los widgets nunca tocan el engine y el hilo nunca
toca widgets. La flag `_syncing` evita reenviar comandos mientras la UI se
actualiza con datos que vienen del backend.
"""

from __future__ import annotations

import os
import queue
import threading

from kivy.config import Config
Config.set("graphics", "width", "1400")
Config.set("graphics", "height", "900")

from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, Line, Rectangle
from kivy.lang import Builder
from kivy.properties import (BooleanProperty, ListProperty, NumericProperty,
                             StringProperty)
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget

from backend import MixerBackend, parse_pot_target

POLL_SECONDS = 0.25
KV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "mixer.kv")

# Parámetros seleccionables en los knobs además de los efectos (que salen
# vivos de EFFECT_PRESETS): los que entiende Engine._apply_param.
PARAMS_EXTRA = ["tempo", "volume", "pan", "pitch", "cutoff"]

# Carpeta "virtual" para los wav que cuelgan directo de wavs_dir (sin
# subcarpeta), en el desplegable de carpeta de cada pad.
PAD_ROOT_LABEL = "(raíz)"

# Botón físico (acción de Player.ui_queue) -> método de MixerApp. Mismo
# significado que en el player real (lgpt_player._poll_buttons, contexto
# "song"): anterior/siguiente canción, play/pausa, stop.
BOTONES_FISICOS = {
    "up": "pad_anterior",
    "down": "pad_siguiente",
    "play": "_toggle_play",
    "stop": "stop",
}


class ReleaseSlider(Slider):
    """Slider que emite `on_release` al soltar el dedo/ratón.

    Los comandos que persisten (FX, MASTER) se envían una vez al soltar, no
    en cada píxel del arrastre.
    """
    __events__ = ("on_release",)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._uid = touch.uid
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if getattr(self, "_uid", None) == touch.uid:
            self._uid = None
            self.dispatch("on_release")
        return super().on_touch_up(touch)

    def on_release(self):
        pass


class MixScope(Widget):
    """Osciloscopio de la mezcla final: traza la forma de onda reciente.

    `values`: muestras (-1..1) de la mezcla final, más viejo primero, que
    MixerApp actualiza desde `state()` (engine.scope_snapshot()) en cada
    sondeo del hilo trabajador.
    """
    values = ListProperty([])

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(pos=self._redraw, size=self._redraw, values=self._redraw)

    def _redraw(self, *_):
        self.canvas.clear()
        if self.width < 10 or self.height < 10:
            return
        mid_y = self.y + self.height / 2
        with self.canvas:
            Color(0.09, 0.1, 0.1, 1)
            Rectangle(pos=self.pos, size=self.size)
            Color(0.24, 0.24, 0.27, 1)
            Line(points=[self.x, mid_y, self.x + self.width, mid_y],
                 width=1)
            vals = self.values
            if len(vals) < 2:
                return
            step = self.width / (len(vals) - 1)
            half_h = self.height / 2 - 2
            pts = []
            for i, v in enumerate(vals):
                pts += [self.x + i * step,
                        mid_y + max(-1.0, min(1.0, v)) * half_h]
            Color(0.3, 0.9, 0.45, 1)
            Line(points=pts, width=1.4)


class ChannelStrip(BoxLayout):
    """Strip de un canal tracker (0-7): toggles M/V/P.

    El área que antes ocupaban los sliders de efectos por canal ahora la
    cubre el osciloscopio único de mezcla (`MixScope`, en `MixerRoot`): los
    niveles de efecto ya guardados en el robotraca.json (campo "fx") se
    conservan al guardar, pero el mixer ya no los edita.
    """
    canal = NumericProperty(0)
    posicion = StringProperty("-")
    mute = BooleanProperty(False)
    voc = BooleanProperty(False)
    pres = BooleanProperty(False)


class KnobWidget(BoxLayout):
    """Knob virtual + a qué canales afecta + qué efecto/parámetro aplica.

    param: "off" | "red" | nombre de efecto/parámetro (valve, acid...,
    tempo, volume...). canales: lista de canales tracker 0-7 seleccionados.
    modo es derivado (color del knob): off / red / target.
    """
    knob_n = NumericProperty(1)     # 1-8, como en el robotraca.json (potN)
    param = StringProperty("off")
    canales = ListProperty([])
    modo = StringProperty("off")
    mix = NumericProperty(100)      # mezcla dry/wet del efecto (0-100%)


class PadAssignWidget(BoxLayout):
    """Qué WAV suena en un pad (1-4): solo configuración, el disparo en
    vivo lo hace el pad físico (sample1-4 del TOML), no un botón aquí.

    wav: ruta relativa a wavs_dir del último WAV elegido (o "—" si no se
    ha tocado desde el mixer en esta sesión). vol: volumen efectivo
    0-100% de este pad EN ESTA CANCIÓN (persiste por canción, a
    diferencia de wav que es el mismo banco para todas)."""
    pad_n = NumericProperty(1)
    wav = StringProperty("—")
    vol = NumericProperty(60)


class MixerRoot(BoxLayout):
    pass


class MixerApp(App):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.backend: MixerBackend | None = None
        self._cola: queue.Queue = queue.Queue()
        self._fin = threading.Event()
        self._syncing = False
        self._ultima_cfg: dict = {}
        self._canciones: list = []
        self._song_idx = 0          # última canción viva según state()
        self._efectos: list = []    # EFFECT_PRESETS, lo rellena _on_arrancado
        self._wav_tree: dict = {}   # carpeta -> [nombres .wav], ver _build_wav_tree

    # -- arranque / parada --------------------------------------------------

    def load_kv(self, filename=None):
        # carga explícita y una sola vez: así build() funciona también en
        # pruebas sin run() (Builder.files guarda las rutas ya cargadas)
        if KV_PATH not in Builder.files:
            Builder.load_file(KV_PATH)

    def build(self):
        self.load_kv()
        return MixerRoot()

    def on_start(self):
        threading.Thread(target=self._bucle, daemon=True,
                         name="mixer-worker").start()
        self._enviar(self._arrancar_backend, self._on_arrancado)

    def on_stop(self):
        self._fin.set()
        if self.backend is not None:
            self.backend.close()

    def _arrancar_backend(self):
        """Crea el backend (abre el audio) y devuelve canciones + config +
        la lista viva de efectos del engine + los WAV disponibles/
        asignados para los pads + las canciones de origen (LGPT)."""
        try:
            self.backend = MixerBackend()
        except Exception as exc:
            return exc
        return (self.backend.songs(), self.backend.get_config(),
                self.backend.effects(), self.backend.wav_candidates(),
                self.backend.pad_assignments(), self.backend.origin_songs())

    def _on_arrancado(self, res):
        if self.backend is None:
            self._aviso(f"sin audio: {res}")
            return
        canciones, cfg, efectos, wavs, asignados, origen = res
        self._efectos = efectos
        self._canciones = canciones.get("songs", [])
        self._syncing = True
        try:
            sp = self.root.ids.spinner_canciones
            sp.values = self._canciones
            cur = canciones.get("current", 0)
            if self._canciones and 0 <= cur < len(self._canciones):
                sp.text = self._canciones[cur]
            self.root.ids.spinner_origen.values = origen
            for n in range(1, 9):
                kw = self._knob_widget(n)
                if kw is not None:
                    kw.ids.param_spinner.values = \
                        ["off", "red"] + efectos + PARAMS_EXTRA
            self._wav_tree = self._build_wav_tree(wavs)
            for n in range(1, 5):
                pw = self._pad_widget(n)
                if pw is not None:
                    pw.wav = asignados.get(str(n), "—")
        finally:
            self._syncing = False
        self._aplicar_config(cfg)
        self._aviso(f"{len(self._canciones)} canciones")

    # -- hilo trabajador ------------------------------------------------------

    def _bucle(self):
        """Ejecuta la cola de llamadas al backend, sondea state() y drena
        los botones físicos pendientes (transporte del controlador MIDI)."""
        while not self._fin.is_set():
            try:
                self._cola.get(timeout=POLL_SECONDS)()
            except queue.Empty:
                pass
            if self._fin.is_set() or self.backend is None:
                continue
            for accion in self.backend.drain_buttons():
                self._boton_fisico(accion)
            try:
                estado = self.backend.state()
            except Exception as exc:
                Clock.schedule_once(lambda dt, e=exc:
                                    self._aviso(f"state: {e}"))
                continue
            Clock.schedule_once(lambda dt, e=estado: self._aplicar_state(e))

    def _boton_fisico(self, accion):
        """Traduce un botón del controlador MIDI (up/down/play/stop) a la
        misma acción que tendría en el player real (ver BOTONES_FISICOS)."""
        metodo = BOTONES_FISICOS.get(accion)
        if metodo is not None:
            getattr(self, metodo)()

    def _enviar(self, tarea, on_result=None):
        """Encola una llamada al backend; el resultado vuelve a la UI."""
        def trabajo():
            try:
                res = tarea()
            except Exception as exc:
                Clock.schedule_once(lambda dt, e=exc:
                                    self._aviso(f"error: {e}"))
                return
            if on_result is not None:
                Clock.schedule_once(lambda dt, r=res: on_result(r))
        self._cola.put(trabajo)

    def _listo(self) -> bool:
        return self.backend is not None and not self._syncing

    # -- transporte y canciones ----------------------------------------------

    def seleccionar_cancion(self, nombre):
        if not self._listo() or nombre not in self._canciones:
            return
        self._seleccionar_indice(self._canciones.index(nombre))

    def _seleccionar_indice(self, i):
        def tarea():
            r = self.backend.select(i)
            if r != "OK":
                return r, None
            # SELECT cambia de canción: el modelo cambia, hay que releerlo
            return r, self.backend.get_config()

        def fin(res):
            r, cfg = res
            if r != "OK":
                self._aviso(f"SELECT: {r}")
                return
            self._song_idx = i
            self._aplicar_config(cfg)
            self._syncing = True
            try:
                self.root.ids.spinner_canciones.text = self._canciones[i]
            finally:
                self._syncing = False
            self._aviso(f"canción: {self._canciones[i]}")
        self._enviar(tarea, fin)

    # -- traer/actualizar canciones desde LGPT ------------------------------

    def importar_cancion(self):
        """Trae o actualiza la canción elegida en spinner_origen desde
        la carpeta de trabajo de LGPT (importa-cancion.sh)."""
        if not self._listo():
            return
        nombre = self.root.ids.spinner_origen.text
        if nombre in ("", "— origen —"):
            self._aviso("elige antes una canción de origen")
            return
        self._aviso(f"importando {nombre}…")
        self._enviar(lambda: self.backend.import_song(nombre),
                     self._fin_importar)

    def actualizar_todas(self):
        """Actualiza desde LGPT todas las canciones ya presentes en
        songs/ (importa-cancion.sh --todas); no trae canciones nuevas."""
        if not self._listo():
            return
        self._aviso("actualizando todas las canciones desde LGPT…")
        self._enviar(self.backend.import_all_songs, self._fin_importar)

    def _fin_importar(self, r):
        if r != "OK":
            self._aviso(f"importar: {r}")
            return
        self._enviar(self.backend.songs, self._on_canciones_actualizadas)

    def _on_canciones_actualizadas(self, canciones):
        """Tras importar: la lista de canciones (y sus índices) puede
        haber cambiado; se resincroniza el spinner sin tocar la canción
        que esté sonando ahora mismo (import_song/import_all_songs solo
        tocan ficheros en disco, no recargan el engine en vivo)."""
        self._syncing = True
        try:
            self._canciones = canciones.get("songs", [])
            self.root.ids.spinner_canciones.values = self._canciones
            cur = canciones.get("current", 0)
            if self._canciones and 0 <= cur < len(self._canciones):
                self.root.ids.spinner_canciones.text = self._canciones[cur]
                self._song_idx = cur
        finally:
            self._syncing = False
        self._aviso("canciones actualizadas — reselecciona una para "
                    "cargar los cambios en el engine")

    def stop(self):
        self._comando_simple(lambda: self.backend.stop(), "STOP")

    def _toggle_play(self):
        """Botón físico "play": play/pausa, como en el player real."""
        self._comando_simple(lambda: self.backend.toggle_play(), "PLAY")

    def pad_siguiente(self):
        """Botón físico "down": canción siguiente, como en el player real."""
        if self._listo() and self._canciones:
            self._seleccionar_indice(
                (self._song_idx + 1) % len(self._canciones))

    def pad_anterior(self):
        """Botón físico "up": canción anterior, como en el player real."""
        if self._listo() and self._canciones:
            self._seleccionar_indice(
                (self._song_idx - 1) % len(self._canciones))

    def _comando_simple(self, fn, que):
        if self.backend is None:
            return
        self._enviar(fn, lambda r: self._check(r, que))

    # -- channel strips ---------------------------------------------------------

    def on_mute(self, canal, on):
        if not self._listo():
            return
        self._enviar(lambda: self.backend.set_mute(canal, on),
                     lambda r: self._check(r, "MUTE"))

    def on_vocoder(self, canal, on):
        if not self._listo():
            return
        self._enviar(lambda: self.backend.set_vocoder(canal, on),
                     lambda r: self._check(r, "VOCODER"))

    def on_presence(self, canal, on):
        if not self._listo():
            return
        self._enviar(lambda: self.backend.set_presence(canal, on),
                     lambda r: self._check(r, "PRESENCE"))

    # -- knobs: solo configuración de a qué apunta cada uno en la canción ----
    # (el valor en vivo lo manda el pot físico directo al engine, ver
    # lgpt_player.open_midi_input/match_pot/match_pot_red).

    def on_knob_param(self, n, param):
        """Cambia qué aplica el knob (spinner): off / red / efecto."""
        if not self._listo():
            return
        kw = self._knob_widget(n)
        if kw is None:
            return
        kw.param = param
        self._enviar_spec(n, kw)

    def on_knob_canal(self, n, canal, on):
        """(Des)marca un canal del knob: a qué canales afecta."""
        if not self._listo():
            return
        kw = self._knob_widget(n)
        if kw is None:
            return
        canales = set(kw.canales)
        (canales.add if on else canales.discard)(canal)
        kw.canales = sorted(canales)
        self._enviar_spec(n, kw)

    def on_knob_mix(self, n, pct):
        """Mezcla dry/wet (0-100%) del efecto al que apunta este knob: no
        es un valor en vivo por hardware, se fija aquí y se persiste."""
        if not self._listo():
            return
        kw = self._knob_widget(n)
        if kw is None or kw.param not in self._efectos:
            return
        kw.mix = pct
        for canal in kw.canales:
            self._enviar(lambda c=canal: self.backend.set_fx_mix(
                c, kw.param, pct), lambda r, c=canal:
                self._check(r, f"MIX{n}:{c}"))

    def _enviar_spec(self, n, kw):
        """Compone el target del knob ("off" | "red" | "canales:param") y
        lo manda al backend, que lo aplica en vivo y lo mete al modelo."""
        if kw.param in ("off", "red"):
            spec = kw.param
        elif kw.canales:
            spec = ",".join(str(c) for c in kw.canales) + ":" + kw.param
        else:
            spec = "off"          # param elegido pero sin canales: inactivo
        kw.modo = "off" if spec == "off" else (
            "red" if spec == "red" else "target")
        self._enviar(lambda: self.backend.set_pot(n, spec),
                     lambda r: self._check(r, f"POT{n}"))

    # -- pads: qué WAV suena en cada uno (banco global, no por canción) ------
    # (el disparo en vivo lo hace el pad físico, ver MixerApp._boton_fisico
    # y MixerBackend.drain_buttons/pad).

    def _build_wav_tree(self, wavs):
        """Agrupa las rutas relativas de wav_candidates() por carpeta, para
        mostrar cada subcarpeta (candidatos2, Distorted metal...) como su
        propio desplegable en vez de una lista plana con "carpeta/wav.wav".
        PAD_ROOT_LABEL agrupa los que cuelgan directo de wavs_dir."""
        tree: dict = {}
        for rel in wavs:
            if "/" in rel:
                folder, name = rel.rsplit("/", 1)
            else:
                folder, name = PAD_ROOT_LABEL, rel
            tree.setdefault(folder, []).append(name)
        return tree

    def on_pad_open(self, n, anchor):
        """Botón único del pad: abre un desplegable en árbol (carpetas
        expandibles inline, ver _render_pad_dropdown) en vez de un segundo
        spinner encadenado."""
        dd = DropDown(auto_width=False, width=240)
        expandidas = set()

        def render():
            dd.container.clear_widgets()
            self._render_pad_dropdown(dd, expandidas, render)

        render()
        dd.bind(on_select=lambda inst, rel_path: self.on_pad_assign(n, rel_path))
        dd.open(anchor)

    def _render_pad_dropdown(self, dd, expandidas, render, folder=None, indent=0):
        """Pinta un nivel del árbol de wavs dentro de `dd`: los ficheros de
        `folder` (None = raíz) seguidos de las subcarpetas, expandiendo
        inline (sin cerrar el desplegable) las que estén en `expandidas`."""
        clave = PAD_ROOT_LABEL if folder is None else folder
        nombres = sorted(self._wav_tree.get(clave, []))
        for nombre in nombres:
            rel_path = nombre if folder is None else f"{folder}/{nombre}"
            btn = Button(text="  " * indent + nombre, size_hint_y=None,
                        height=26, halign="left", valign="middle")
            btn.bind(size=lambda b, s: setattr(b, "text_size", s))
            btn.bind(on_release=lambda b, r=rel_path: dd.select(r))
            dd.container.add_widget(btn)
        if folder is not None:
            return
        for sub in sorted(k for k in self._wav_tree if k != PAD_ROOT_LABEL):
            abierta = sub in expandidas
            flecha = "v " if abierta else "> "
            hdr = Button(text=flecha + sub + "/", size_hint_y=None, height=26,
                        background_color=(0.28, 0.28, 0.32, 1),
                        halign="left", valign="middle")
            hdr.bind(size=lambda b, s: setattr(b, "text_size", s))

            def toggle(b, s=sub):
                expandidas.symmetric_difference_update({s})
                render()
            hdr.bind(on_release=toggle)
            dd.container.add_widget(hdr)
            if abierta:
                self._render_pad_dropdown(dd, expandidas, render,
                                          folder=sub, indent=1)

    def on_pad_assign(self, n, rel_path):
        if not self._listo() or rel_path in ("—", ""):
            return
        pw = self._pad_widget(n)
        if pw is not None:
            pw.wav = rel_path
        self._enviar(lambda: self.backend.assign_pad(n, rel_path),
                     lambda r: self._check(r, f"PAD{n}"))

    def on_pad_volume(self, n, pct):
        """Volumen del pad n (0-100%), por canción."""
        if not self._listo():
            return
        self._enviar(lambda: self.backend.set_pad_volume(n, pct),
                     lambda r: self._check(r, f"PADVOL{n}"))

    # -- barra inferior -------------------------------------------------------

    def on_master(self, pct):
        if not self._listo():
            return
        self._enviar(lambda: self.backend.set_master(pct),
                     lambda r: self._check(r, "MASTER"))

    def guardar(self):
        """SAVE + re-sincronización: tras guardar se relee el modelo."""
        if self.backend is None:
            return

        def tarea():
            r = self.backend.save()
            cfg = self.backend.get_config() if r == "OK" else None
            return r, cfg

        def fin(res):
            r, cfg = res
            if r != "OK":
                self._aviso(f"SAVE: {r}")
                return
            self._aplicar_config(cfg)
            self._aviso("guardado en robotraca.json")
        self._enviar(tarea, fin)

    def recargar(self):
        if self.backend is None:
            return
        self._enviar(self.backend.get_config, self._on_recargado)

    def _on_recargado(self, cfg):
        self._aplicar_config(cfg)
        self._aviso("config recargada")

    # -- sincronización desde el backend -------------------------------------

    def _aplicar_config(self, cfg):
        """Re-sincroniza TODA la UI con el modelo de config del backend."""
        if not isinstance(cfg, dict):
            return
        self._ultima_cfg = cfg
        self._syncing = True
        try:
            mute = set(cfg.get("mute", []))
            voc = set(cfg.get("vocoder", []))
            pres = set(cfg.get("presence", []))
            for strip in self._strips():
                c = strip.canal
                strip.mute = c in mute
                strip.voc = c in voc
                strip.pres = c in pres
            master = cfg.get("master", 100)
            try:
                master = max(0, min(200, int(master)))
            except (TypeError, ValueError):
                master = 100
            self.root.ids.master.value = master
            pots = cfg.get("pots") or {}
            pots_red = set(cfg.get("pots_red") or [])
            fx_mix = cfg.get("fx_mix") or {}
            for n in range(1, 9):
                kw = self._knob_widget(n)
                if kw is None:
                    continue
                key = f"pot{n}"
                if key in pots_red:
                    kw.param, kw.canales, kw.modo, kw.mix = \
                        "red", [], "red", 100
                    continue
                target = parse_pot_target(str(pots.get(key, "off")))
                if target is None:
                    kw.param, kw.canales, kw.modo, kw.mix = \
                        "off", [], "off", 100
                else:
                    canales, nombre, _tope = target
                    kw.param = nombre
                    kw.canales = list(canales)
                    kw.modo = "target"
                    kw.mix = 100
                    if canales:
                        kw.mix = fx_mix.get(str(canales[0]), {}) \
                            .get(nombre, 100)
            vol_pct = cfg.get("pad_volume_pct") or {}
            for n in range(1, 5):
                pw = self._pad_widget(n)
                if pw is None:
                    continue
                try:
                    pw.vol = max(0, min(100, int(vol_pct.get(str(n), 60))))
                except (TypeError, ValueError):
                    pw.vol = 60
        finally:
            self._syncing = False

    def _aplicar_state(self, e):
        """Datos vivos del engine: transporte, BPM, posiciones y mezcla."""
        self._song_idx = e.get("song", self._song_idx)
        lbl = self.root.ids.lbl_playing
        if e.get("playing"):
            lbl.text = "SONANDO"
            lbl.color = (0.35, 0.95, 0.4, 1)
        else:
            lbl.text = "PARADA"
            lbl.color = (0.55, 0.55, 0.6, 1)
        self.root.ids.lbl_bpm.text = f"BPM: {e.get('bpm', '—')}"
        self.root.ids.lbl_activos.text = f"Activos: {e.get('active', '—')}"
        pos = e.get("positions") or []
        for strip in self._strips():
            c = strip.canal
            strip.posicion = str(pos[c]) if c < len(pos) else "-"
        self.root.ids.scope.values = e.get("scope") or []

    # -- utilidades ------------------------------------------------------------

    def _strips(self):
        return sorted(self.root.ids.strips.children, key=lambda s: s.canal)

    def _knob_widget(self, n):
        for kw in self.root.ids.knobs.children:
            if kw.knob_n == n:
                return kw
        return None

    def _pad_widget(self, n):
        for pw in self.root.ids.pads.children:
            if pw.pad_n == n:
                return pw
        return None

    def _check(self, r, que):
        if r != "OK":
            self._aviso(f"{que}: {r}")

    def _aviso(self, msg):
        if self.root is not None:
            self.root.ids.lbl_estado.text = str(msg)


if __name__ == "__main__":
    MixerApp().run()
