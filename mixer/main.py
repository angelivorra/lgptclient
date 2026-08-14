#!/usr/bin/env python3
"""Mixer: editor visual de robotraca.json con el engine de sinte embebido.

App Kivy standalone: no hay servidor ni red; `backend.MixerBackend` crea el
Player de sinte en este proceso (misma carga de canciones, mismo
robotraca.json, misma salida de audio) y la UI lo conduce. Sirve para
probar y configurar cada canción: lista + play/stop, mute/vocoder/presence
por canal, efectos por canal, knobs asignables, pads y master; Guardar
escribe el robotraca.json.

Lo que PERSISTE en el modelo (toggles, FX, MASTER, POT, SAVE) se
re-sincroniza entero con `get_config()` tras arrancar, tras cambiar de
canción y tras guardar: la UI no guarda estado propio de la config, el
backend es la fuente de verdad. Lo que es solo en vivo (VOL/PAN/PARAM/
NETCC/PAD) se manda sin más.

Arquitectura: un único hilo trabajador ejecuta las llamadas al backend en
orden (cola FIFO) y sondea `state()` cada ~250 ms; los resultados llegan a
la UI por `Clock.schedule_once`. Los widgets nunca tocan el engine y el
hilo nunca toca widgets. La flag `_syncing` evita reenviar comandos
mientras la UI se actualiza con datos que vienen del backend.
"""

from __future__ import annotations

import math
import os
import queue
import threading

from kivy.config import Config
Config.set("graphics", "width", "1400")
Config.set("graphics", "height", "900")

from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line
from kivy.lang import Builder
from kivy.properties import (BooleanProperty, ListProperty, NumericProperty,
                             StringProperty)
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget

from backend import MixerBackend, parse_pot_target

POLL_SECONDS = 0.25
KV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "mixer.kv")

# Parámetros seleccionables en los knobs además de los efectos (que salen
# vivos de EFFECT_PRESETS): los que entiende Engine._apply_param.
PARAMS_EXTRA = ["tempo", "volume", "pan", "pitch", "cutoff"]

# Color del knob según su modo: target = verde, red = ámbar, off = gris.
KNOB_COLORES = {
    "target": (0.35, 0.9, 0.4, 1),
    "red": (0.95, 0.65, 0.15, 1),
    "off": (0.45, 0.45, 0.5, 1),
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


class Knob(Widget):
    """Knob circular: arrastre vertical recorre 0-127 en 270°.

    Se dibuja entero en canvas (sombra, cuerpo, bisel, arco de recorrido,
    arco de valor en el color del modo, marcas y puntero): hay que
    redibujar al mover o al cambiar tamaño/posición. No envía nada por sí
    mismo: la app escucha `on_value` en el kv y decide qué comando mandar
    según el target configurado (off/red/canales:param).
    """
    value = NumericProperty(0)
    modo = StringProperty("off")  # off | red | target

    # el 0 está abajo a la izquierda y el 127 abajo a la derecha
    A_MIN, A_MAX = -135.0, 135.0

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(pos=self._redraw, size=self._redraw,
                  value=self._redraw, modo=self._redraw)

    def on_value(self, *_):
        self.value = max(0, min(127, int(round(self.value))))

    @staticmethod
    def _arco(cx, cy, r, a0, a1, paso=4.0):
        """Puntos de un arco de a0 a a1 grados (0 = derecha, antihorario)."""
        if a1 < a0:
            a1 = a0
        n = max(2, int((a1 - a0) / paso) + 1)
        pts = []
        for i in range(n + 1):
            a = math.radians(a0 + (a1 - a0) * i / n)
            pts += [cx + math.cos(a) * r, cy + math.sin(a) * r]
        return pts

    def _redraw(self, *_):
        self.canvas.clear()
        if self.width < 10 or self.height < 10:
            return
        cx, cy = self.center
        r = min(self.width, self.height) / 2 - 4
        color = KNOB_COLORES.get(self.modo, KNOB_COLORES["off"])
        # Sentido de las agujas del reloj: el 0 abajo a la izquierda y el
        # 127 abajo a la derecha, subiendo por arriba. En canvas los ángulos
        # crecen antihorarios, así que al subir el valor el ángulo DECRECE:
        # -135° -> -180°(izq) -> -270°(arriba) -> -360°(dcha) -> -405°.
        av = self.A_MIN - (self.value / 127.0) * (self.A_MAX - self.A_MIN)
        with self.canvas:
            # sombra
            Color(0, 0, 0, 0.45)
            Ellipse(pos=(cx - r + 2, cy - r - 3), size=(2 * r, 2 * r))
            # cuerpo
            Color(0.15, 0.15, 0.17, 1)
            Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
            # bisel exterior
            Color(0.30, 0.30, 0.34, 1)
            Line(circle=(cx, cy, r), width=1.6)
            # arco de recorrido (gris), por arriba
            Color(0.32, 0.32, 0.36, 1)
            Line(points=self._arco(cx, cy, r - 4,
                                   self.A_MIN - 270, self.A_MIN),
                 width=3.2, cap="round")
            # arco de valor (color del modo): del 0 a la posición actual
            if self.value > 0:
                Color(*color)
                Line(points=self._arco(cx, cy, r - 4, av, self.A_MIN),
                     width=3.2, cap="round")
            # marcas cada 45° por el arco de arriba
            Color(0.55, 0.55, 0.6, 1)
            for k in range(7):
                ar = math.radians(self.A_MIN - k * 45)
                Line(points=[cx + math.cos(ar) * (r + 1),
                             cy + math.sin(ar) * (r + 1),
                             cx + math.cos(ar) * (r - 3),
                             cy + math.sin(ar) * (r - 3)], width=1.1)
            # puntero
            ar = math.radians(av)
            Color(*color)
            Line(points=[cx + math.cos(ar) * r * 0.30,
                         cy + math.sin(ar) * r * 0.30,
                         cx + math.cos(ar) * r * 0.78,
                         cy + math.sin(ar) * r * 0.78],
                 width=2.6, cap="round")
            # tapa central
            Color(0.22, 0.22, 0.25, 1)
            Ellipse(pos=(cx - r * 0.28, cy - r * 0.28),
                    size=(r * 0.56, r * 0.56))

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.grab(self)
            self._y0 = touch.y
            self._v0 = self.value
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            # 150 px de arrastre = recorrido completo
            self.value = self._v0 + (touch.y - self._y0) * 127.0 / 150.0
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)


class ChannelStrip(BoxLayout):
    """Strip de un canal tracker (0-7): toggles M/V/P y sliders de efectos.

    Los sliders de efectos se construyen en Python (MixerApp._construir_fx)
    a partir de la lista viva `EFFECT_PRESETS` del engine: si el player
    gana un efecto nuevo, aparece aquí solo. Se guardan en `fx_sliders`
    ({nombre: slider}) para sincronizarlos con la config.
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


class MixerRoot(BoxLayout):
    pass


class MixerApp(App):
    pads_count = NumericProperty(0)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.backend: MixerBackend | None = None
        self._cola: queue.Queue = queue.Queue()
        self._fin = threading.Event()
        self._syncing = False
        self._ultima_cfg: dict = {}
        self._canciones: list = []
        self._song_idx = 0          # última canción viva según state()

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
        la lista viva de efectos del engine."""
        try:
            self.backend = MixerBackend()
        except Exception as exc:
            return exc
        return (self.backend.songs(), self.backend.get_config(),
                self.backend.effects())

    def _on_arrancado(self, res):
        if self.backend is None:
            self._aviso(f"sin audio: {res}")
            return
        canciones, cfg, efectos = res
        self._efectos = efectos
        self._canciones = canciones.get("songs", [])
        self._construir_fx()
        self._syncing = True
        try:
            sp = self.root.ids.spinner_canciones
            sp.values = self._canciones
            cur = canciones.get("current", 0)
            if self._canciones and 0 <= cur < len(self._canciones):
                sp.text = self._canciones[cur]
            for n in range(1, 9):
                kw = self._knob_widget(n)
                if kw is not None:
                    kw.ids.param_spinner.values = \
                        ["off", "red"] + efectos + PARAMS_EXTRA
        finally:
            self._syncing = False
        self._aplicar_config(cfg)
        self._aviso(f"{len(self._canciones)} canciones")

    def _construir_fx(self):
        """Un slider por efecto y canal, según la lista viva del engine."""
        for strip in self._strips():
            box = strip.ids.fx_box
            box.clear_widgets()
            strip.fx_sliders = {}
            for name in self._efectos:
                col = BoxLayout(orientation="vertical", spacing=1)
                col.add_widget(Label(text=name[:3].upper(), font_size="8sp",
                                     size_hint_y=None, height=11,
                                     color=(0.6, 0.6, 0.65, 1)))
                sl = ReleaseSlider(orientation="vertical", min=0, max=100,
                                   value=0)
                sl.bind(on_release=lambda s, c=strip.canal, n=name:
                        self.on_fx(c, n, int(s.value)))
                col.add_widget(sl)
                box.add_widget(col)
                strip.fx_sliders[name] = sl

    # -- hilo trabajador ------------------------------------------------------

    def _bucle(self):
        """Ejecuta la cola de llamadas al backend y sondea state()."""
        while not self._fin.is_set():
            try:
                self._cola.get(timeout=POLL_SECONDS)()
            except queue.Empty:
                pass
            if self._fin.is_set() or self.backend is None:
                continue
            try:
                estado = self.backend.state()
            except Exception as exc:
                Clock.schedule_once(lambda dt, e=exc:
                                    self._aviso(f"state: {e}"))
                continue
            Clock.schedule_once(lambda dt, e=estado: self._aplicar_state(e))

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

    def play(self):
        self._comando_simple(lambda: self.backend.play(), "PLAY")

    def pause(self):
        self._comando_simple(lambda: self.backend.pause(), "PAUSE")

    def stop(self):
        self._comando_simple(lambda: self.backend.stop(), "STOP")

    # Pads de transporte (como los botones del player curses)
    def pad_play(self):
        self.play()

    def pad_stop(self):
        self.stop()

    def pad_siguiente(self):
        if self._listo() and self._canciones:
            self._seleccionar_indice(
                (self._song_idx + 1) % len(self._canciones))

    def pad_anterior(self):
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

    def on_fx(self, canal, preset, pct):
        if not self._listo():
            return
        val = round(pct * 127 / 100)
        self._enviar(lambda: self.backend.set_fx(canal, preset, val),
                     lambda r: self._check(r, "FX"))

    # -- knobs ----------------------------------------------------------------

    def on_knob(self, n, val):
        """Giro del knob n (1-8): en vivo, sin persistir.

        red -> NETCC (reenvío por red); con param y canales -> PARAM por
        cada canal seleccionado; off o sin canales -> nada.
        """
        if not self._listo():
            return
        kw = self._knob_widget(n)
        if kw is None:
            return
        if kw.param == "off":
            return
        if kw.param == "red":
            self._enviar(lambda: self.backend.netcc(n, val))
            return
        if not kw.canales:
            return

        def tarea():
            r = "OK"
            for ch in kw.canales:
                r = self.backend.param(ch, kw.param, val)
            return r
        self._enviar(tarea)

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

    # -- pads -----------------------------------------------------------------

    def pad(self, n):
        if self.backend is None:
            return
        self._enviar(lambda: self.backend.pad(n),
                     lambda r: self._check(r, "PAD"))

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
            fx = cfg.get("fx", {})
            for strip in self._strips():
                c = strip.canal
                strip.mute = c in mute
                strip.voc = c in voc
                strip.pres = c in pres
                fx_c = fx.get(str(c), {}) if isinstance(fx, dict) else {}
                for name, sl in getattr(strip, "fx_sliders", {}).items():
                    sl.value = fx_c.get(name, 0)
            master = cfg.get("master", 100)
            try:
                master = max(0, min(200, int(master)))
            except (TypeError, ValueError):
                master = 100
            self.root.ids.master.value = master
            pots = cfg.get("pots") or {}
            pots_red = set(cfg.get("pots_red") or [])
            for n in range(1, 9):
                kw = self._knob_widget(n)
                if kw is None:
                    continue
                key = f"pot{n}"
                if key in pots_red:
                    kw.param, kw.canales, kw.modo = "red", [], "red"
                    continue
                target = parse_pot_target(str(pots.get(key, "off")))
                if target is None:
                    kw.param, kw.canales, kw.modo = "off", [], "off"
                else:
                    canales, nombre, _tope = target
                    kw.param = nombre
                    kw.canales = list(canales)
                    kw.modo = "target"
        finally:
            self._syncing = False

    def _aplicar_state(self, e):
        """Datos vivos del engine: transporte, BPM, posiciones y pads."""
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
        self.pads_count = e.get("pads") or 0

    # -- utilidades ------------------------------------------------------------

    def _strips(self):
        return sorted(self.root.ids.strips.children, key=lambda s: s.canal)

    def _knob_widget(self, n):
        for kw in self.root.ids.knobs.children:
            if kw.knob_n == n:
                return kw
        return None

    def _check(self, r, que):
        if r != "OK":
            self._aviso(f"{que}: {r}")

    def _aviso(self, msg):
        if self.root is not None:
            self.root.ids.lbl_estado.text = str(msg)


if __name__ == "__main__":
    MixerApp().run()
