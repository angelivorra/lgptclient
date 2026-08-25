#!/usr/bin/env python3
"""Reproductor standalone de proyectos LittleGPTracker para consola.

Pensado para Raspberry Pi 4 con HAT de audio (headless), con control
en directo por MIDI CC (canal MIDI 1-8 -> canal tracker 0-7):

    CC 1  -> cutoff del filtro   CC 7  -> volumen
    CC 10 -> pan                 CC 20 -> pitch (+-1 octava, centro en 64)

La configuración (carpeta de canciones, dispositivo de salida de audio,
puertos MIDI de entrada y salida) se lee de `lttileplayer.toml` en el
directorio del programa. Los argumentos de línea de comandos tienen
prioridad sobre el archivo.

Uso:
    lgpt_player.py [--config TOML] [--songs DIR] [--device DEV]
                   [--midi IN] [--midi-out OUT] [--samplerate HZ]
                   [--blocksize N]

Teclas:
    lista:  up/down o j/k moverse, enter reproducir, r reiniciar, q salir
    play:   espacio play/pausa, n siguiente, p anterior, q volver a la lista
"""

from __future__ import annotations

import argparse
import math
import os
import queue
import random
import sys
import threading
import time
import tomllib
import unicodedata
from pathlib import Path

import numpy as np
import sounddevice as sd

from event_server import EventMidiOut, EventServer
from lgpt_engine import EFFECT_PRESETS, Engine, MasterChain, MidiOut, \
    SAMPLE_RATE

DEFAULT_SONGS_DIR = "/home/angel/Documentos/canciones/"
CONFIG_PATH = Path(__file__).resolve().parent / "lttileplayer.toml"

# -- Calibración de motores por el controlador (Akai LPD8 mk2, notas fijas) --
# Pads en canal 9, knobs en canal 0. Ver pantalla _calib_view.
CALIB_OPEN_SPEC = "note:9:39"    # pad 4: abre la calibración desde la lista
CALIB_PAD_CHANNEL = 9
CALIB_PAD_ROBOT = 42             # pad 1: cambiar de robot
CALIB_PAD_SAVE = 43              # pad 2: aceptar y guardar (CALSAVE)
CALIB_PAD_MOTOR = 38             # pad 3: cambiar de motor
CALIB_PAD_PULSE = 39             # pad 4: iniciar/parar el pulso del motor
CALIB_KNOB_CHANNEL = 0
CALIB_KNOB_DUR = 70              # knob 1: duración
CALIB_KNOB_DELAY = 74           # knob 2: delay
# Rango que barre cada knob (0..127 -> estos límites, en ms).
CALIB_DUR_MIN_MS, CALIB_DUR_MAX_MS = 5, 250
CALIB_DELAY_MIN_MS, CALIB_DELAY_MAX_MS = -250, 250
CALIB_PULSE_INTERVAL_S = 0.4     # cada cuánto repite el golpe con el pulso ON


class _CalibExit(Exception):
    """Señal interna para salir del bucle de calibración (botón STOP)."""


def _calib_scale(value: int, lo: float, hi: float) -> float:
    """Mapea un knob 0..127 al rango [lo, hi] en ms."""
    value = max(0, min(127, value))
    return lo + (hi - lo) * value / 127.0

# Un bloque que consuma más de esta fracción de su presupuesto se apunta como
# "apurado": todavía no corta, pero es el aviso de que falta margen.
CARGA_AVISO = 0.75


class EstadoAudio:
    """Contadores del hilo de audio, para saber POR QUÉ hay un corte.

    Distingue las tres causas, que piden arreglos distintos:

    * `xruns`   — PortAudio avisa de que se quedó sin datos (`output_underflow`).
                  Es el corte de verdad: no llegamos a tiempo.
    * `apurados`— bloques que pasaron del `CARGA_AVISO` del presupuesto sin
                  llegar a cortar. Es el margen desapareciendo.
    * `saltos`  — el reloj del DAC dio un salto mayor del esperado. Eso no es
                  culpa nuestra (lo mueve el driver o el sistema), pero
                  descoloca el sincronismo con los clientes y hay que
                  recuperarlo.

    Se escribe solo desde el callback y se lee solo desde la UI. Sin locks a
    propósito: son enteros y floats sueltos, y una lectura a medias da un
    número viejo, nunca un fallo. En el camino de audio no se bloquea nada.
    """

    __slots__ = ("xruns", "apurados", "saltos", "bloques", "peor_ms",
                 "ultima_ms", "peor_desde", "causa", "presupuesto_ms")

    def __init__(self, presupuesto_ms: float):
        self.presupuesto_ms = presupuesto_ms
        self.reinicia()

    def reinicia(self):
        self.xruns = 0
        self.apurados = 0
        self.saltos = 0
        self.bloques = 0
        self.peor_ms = 0.0
        self.ultima_ms = 0.0
        self.peor_desde = 0.0      # peor de la ventana reciente (se va olvidando)
        self.causa = ""            # descripción del último incidente

    @property
    def carga(self) -> float:
        """Fracción del presupuesto que consume el bloque actual."""
        if self.presupuesto_ms <= 0:
            return 0.0
        return self.ultima_ms / self.presupuesto_ms

    @property
    def incidentes(self) -> int:
        return self.xruns + self.saltos


def sube_prioridad() -> str:
    """Pide prioridad para el proceso; devuelve qué consiguió.

    Se intenta primero tiempo real (SCHED_FIFO): con él, el hilo de audio no
    espera a que el planificador atienda a otra cosa, que es de donde salen
    los cortes cuando la CPU no está saturada de media pero sí a ratos.

    Prioridad 10 y no más: por encima del resto pero por debajo de los hilos
    del kernel, para que un cuelgue nuestro no deje la máquina inservible.

    Si no hay permiso (hace falta rtprio en limits.conf o CAP_SYS_NICE) se
    prueba con `nice`, y si tampoco, se sigue sin prioridad. Nunca es un
    error fatal: el player tiene que arrancar igual.
    """
    try:
        param = os.sched_param(10)
        os.sched_setscheduler(0, os.SCHED_FIFO, param)
        return "tiempo real (SCHED_FIFO 10)"
    except (AttributeError, OSError, PermissionError):
        pass
    try:
        os.nice(-10)
        return f"nice {os.nice(0)}"
    except (OSError, PermissionError):
        return "sin prioridad (falta permiso)"


def load_config(path: Path) -> dict:
    if path.is_file():
        with open(path, "rb") as f:
            return tomllib.load(f)
    return {}


def find_projects(songs_dir: Path) -> list[Path]:
    """Proyectos LGPT: directorios que contienen lgptsav.dat."""
    if not songs_dir.is_dir():
        return []
    return sorted(
        (d for d in songs_dir.iterdir()
         if d.is_dir() and (d / "lgptsav.dat").is_file()),
        key=lambda d: d.name.lower(),
    )


def _pick_port(names: list[str], wanted: str | None, what: str) -> str | None:
    """Resuelve un puerto MIDI por nombre parcial. Si el nombre guardado
    incluye el id de cliente ALSA ("... 128:0"), también se prueba sin él
    (el número cambia entre arranques)."""
    if not names:
        print(f"[midi] no hay puertos MIDI de {what}; desactivado")
        return None
    if wanted:
        base = wanted.rsplit(" ", 1)[0]      # sin el "client:port" final
        for n in names:
            if wanted.lower() in n.lower() or base.lower() in n.lower():
                return n
        print(f"[midi] puerto '{wanted}' no encontrado; disponibles: {names}")
        return None
    return names[0]


class WavRecorder:
    """Graba la salida de audio a un WAV sin bloquear el callback:
    el callback encola bloques y un hilo escritor los vuelca a disco."""

    def __init__(self, path: str, samplerate: int):
        import soundfile as sf
        self._sf = sf.SoundFile(path, "w", samplerate=samplerate,
                                channels=2, subtype="PCM_16")
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while True:
            block = self._queue.get()
            if block is None:
                break
            self._sf.write(block)
        self._sf.close()

    def write(self, block):
        self._queue.put(block.copy())

    def close(self):
        self._queue.put(None)
        self._thread.join()


class MidoMidiOut(MidiOut):
    """Sink MidiOut del engine sobre un puerto mido."""

    def __init__(self, port, mido):
        self._port = port
        self._mido = mido

    def note_on(self, channel, note, velocity):
        self._port.send(self._mido.Message(
            "note_on", channel=channel, note=note, velocity=velocity))

    def note_off(self, channel, note):
        self._port.send(self._mido.Message(
            "note_off", channel=channel, note=note, velocity=0))

    def cc(self, channel, control, value):
        self._port.send(self._mido.Message(
            "control_change", channel=channel, control=control, value=value))

    def program_change(self, channel, program):
        self._port.send(self._mido.Message(
            "program_change", channel=channel, program=program))


def parse_button_spec(spec: str) -> tuple | None:
    """'note:canal:nota' o 'cc:canal:control' -> tupla normalizada, o None."""
    try:
        kind, ch, num = spec.split(":")
        ch, num = int(ch), int(num)
    except (ValueError, AttributeError):
        return None
    if kind == "note":
        return ("note_on", ch & 0x0F, num & 0x7F)
    if kind == "cc":
        return ("control_change", ch & 0x0F, num & 0x7F)
    return None


def match_button(mapping: dict, msg) -> str | None:
    """Devuelve la acción del botón que coincide con el mensaje, o None.

    mapping: acción -> spec de parse_button_spec()."""
    if msg.type == "note_on" and msg.velocity == 0:
        return None
    for action, spec in mapping.items():
        if spec is None:
            continue
        mtype, ch, num = spec
        if msg.type != mtype or getattr(msg, "channel", None) != ch:
            continue
        if mtype == "note_on" and msg.note == num:
            return action
        if mtype == "control_change" and msg.control == num and msg.value > 0:
            return action
    return None


def parse_pot_target(target: str) -> tuple | None:
    """'canales:parametro[:tope]' -> (canales, parametro, escala).

    canales: uno o varios separados por coma (`2` o `1,2`), canal tracker
    0-7; un mismo knob puede así mover varias pistas a la vez (p.ej. la
    reverb de todos los bajos).
    tope: recorrido máximo del knob en % (100 por defecto). Sirve para dejar
    un efecto en una zona discreta: `1,2:reverb:35` = de 0 a 35%.
    Devuelve None si no es válido.
    """
    try:
        parts = target.split(":")
    except AttributeError:
        return None
    if len(parts) == 2:
        chans_str, name = parts
        scale = 1.0
    elif len(parts) == 3:
        chans_str, name, top = parts
        try:
            scale = float(top) / 100.0
        except ValueError:
            return None
        if not 0.0 < scale <= 1.0:
            return None
    else:
        return None
    if not name:
        return None
    chans = []
    for c in chans_str.split(","):
        try:
            ci = int(c)
        except ValueError:
            return None
        if not 0 <= ci < 8:
            return None
        chans.append(ci)
    if not chans:
        return None
    return (tuple(chans), name, scale)


def match_pot(pots: list, msg) -> tuple | None:
    """Devuelve (canales, parámetro, nº de knob 0-7, escala) del pot que
    coincide con el mensaje, o None.

    pots: lista de (spec, target, idx) con target de parse_pot_target
    (canales|None, param, escala); canales None = se deriva del canal MIDI
    del mensaje (% 8). `idx` es el knob físico (pot1 -> 0), necesario para
    pintarlo en el visor."""
    if msg.type != "control_change":
        return None
    for spec, target, idx in pots:
        if spec is None:
            continue
        mtype, ch, num = spec
        if mtype == "control_change" and msg.channel == ch \
                and msg.control == num:
            chans, tparam, scale = target
            if chans is None:
                chans = (msg.channel % 8,)
            return chans, tparam, idx, scale
    return None


def match_pot_red(pots_red: list, msg) -> int | None:
    """Como `match_pot`, pero para pots configurados en `pots_red` (JSON de
    la canción): no controlan nada local, solo se reenvían por red. Devuelve
    el número de control con el que reenviar, o None."""
    if msg.type != "control_change":
        return None
    for spec, control in pots_red:
        mtype, ch, num = spec
        if mtype == "control_change" and msg.channel == ch \
                and msg.control == num:
            return control
    return None


def open_midi_input(port_name: str | None, engine_ref: dict,
                    ui_queue: queue.SimpleQueue, buttons: dict,
                    pots: dict, pots_red: list | None = None):
    """Abre el puerto MIDI de entrada: botones a la UI y pots/CC al engine.

    engine_ref es un dict mutable con la clave "engine": el callback MIDI
    siempre usa el engine actual, aunque se cambie de canción.
    Si hay pots configurados solo se procesan esos; si no, se usa el mapeo
    CC por defecto del engine (1/7/10/20).
    pots_red (opcional): pots que no controlan nada local, solo se reenvían
    por red (ver `pots_red` del JSON de la canción y `match_pot_red`).
    """
    if port_name == "off":
        return None
    try:
        import mido
    except ImportError:
        print("[midi] mido no disponible; control MIDI desactivado")
        return None

    chosen = _pick_port(mido.get_input_names(), port_name, "entrada")
    if chosen is None:
        return None

    def on_message(msg):
        # En modo calibración, TODO el MIDI se desvía a calib_queue (con
        # valor/velocidad) y no dispara botones/pots/engine. Ver _calib_view.
        if engine_ref.get("calib_mode"):
            cq = engine_ref.get("calib_queue")
            if cq is not None:
                num = getattr(msg, "note", getattr(msg, "control", 0))
                val = getattr(msg, "value", getattr(msg, "velocity", 0))
                cq.put((msg.type, getattr(msg, "channel", 0), num, val))
            return
        rq = engine_ref.get("raw_queue")
        if rq is not None:
            num = getattr(msg, "note", getattr(msg, "control", 0))
            rq.put((msg.type, getattr(msg, "channel", 0), num))
        if engine_ref.get("capture_mode"):
            return                          # CONFIG capturando: no disparar
        # Los botones mapeados tienen prioridad sobre pots y CC
        action = match_button(buttons, msg)
        if action is not None:
            if action.startswith("sample"):
                # pads sampler: disparan WAVs del banco (sample1 -> pad 1,
                # ver wavs_dir/pads.json)
                engine = engine_ref.get("engine")
                if engine is not None:
                    try:
                        idx = int(action[6:]) - 1
                    except ValueError:
                        idx = 0
                    engine.push_event("trigger", idx)
            else:
                ui_queue.put(action)
            return
        engine = engine_ref.get("engine")
        if engine is None:
            return
        # pots: la lista se rellena por canción; se evalúa EN CADA mensaje
        handled = False
        if pots:
            hit = match_pot(pots, msg)
            if hit is not None:
                chans, tparam, idx, scale = hit
                value = int(round(msg.value * scale))
                for tch in chans:
                    engine.push_event("param", tch, tparam, value)
                handled = True
        if pots_red:
            control = match_pot_red(pots_red, msg)
            if control is not None:
                engine.push_event("netcc", control, msg.value)
                handled = True
        if not handled and not pots and msg.type == "control_change":
            engine.push_event("cc", msg.channel % 8, msg.control, msg.value)

    port = mido.open_input(chosen, callback=on_message)
    print(f"[midi] entrada: '{chosen}'")
    return port


def open_midi_output(port_name: str | None) -> MidoMidiOut | None:
    """Abre el puerto MIDI de salida para los eventos MIDI de LGPT."""
    if not port_name or port_name == "off":
        return None
    try:
        import mido
    except ImportError:
        print("[midi] mido no disponible; salida MIDI desactivada")
        return None

    if port_name == "virtual":
        # Crea un puerto ALSA nuevo al que se pueden conectar otros programas
        port = mido.open_output("lttileplayer", virtual=True)
        print("[midi] salida: puerto virtual 'lttileplayer'")
        return MidoMidiOut(port, mido)

    chosen = _pick_port(mido.get_output_names(), port_name, "salida")
    if chosen is None:
        return None
    port = mido.open_output(chosen)
    print(f"[midi] salida: '{chosen}'")
    return MidoMidiOut(port, mido)


# Microfuente 3x5 para el título y la lista de canciones (estética retro)
FONT3X5 = {
    "A": [" # ", "# #", "###", "# #", "# #"],
    "B": ["## ", "# #", "## ", "# #", "## "],
    "C": [" ##", "#  ", "#  ", "#  ", " ##"],
    "D": ["## ", "# #", "# #", "# #", "## "],
    "E": ["###", "#  ", "## ", "#  ", "###"],
    "F": ["###", "#  ", "## ", "#  ", "#  "],
    "G": [" ##", "#  ", "# #", "# #", " ##"],
    "H": ["# #", "# #", "###", "# #", "# #"],
    "I": ["###", " # ", " # ", " # ", "###"],
    "J": ["  #", "  #", "  #", "# #", " # "],
    "K": ["# #", "# #", "## ", "# #", "# #"],
    "L": ["#  ", "#  ", "#  ", "#  ", "###"],
    "M": ["# #", "###", "###", "# #", "# #"],
    "N": ["# #", "## ", "###", " ##", "# #"],
    "O": [" # ", "# #", "# #", "# #", " # "],
    "P": ["## ", "# #", "## ", "#  ", "#  "],
    "Q": [" # ", "# #", "# #", " ##", "  #"],
    "R": ["## ", "# #", "## ", "# #", "# #"],
    "S": [" ##", "#  ", " # ", "  #", "## "],
    "T": ["###", " # ", " # ", " # ", " # "],
    "U": ["# #", "# #", "# #", "# #", "###"],
    "V": ["# #", "# #", "# #", "# #", " # "],
    "W": ["# #", "# #", "###", "###", "# #"],
    "X": ["# #", "# #", " # ", "# #", "# #"],
    "Y": ["# #", "# #", " # ", " # ", " # "],
    "Z": ["###", "  #", " # ", "#  ", "###"],
    "0": [" # ", "# #", "# #", "# #", " # "],
    "1": [" # ", "## ", " # ", " # ", "###"],
    "2": ["## ", "  #", " # ", "#  ", "###"],
    "3": ["## ", "  #", " # ", "  #", "## "],
    "4": ["# #", "# #", "###", "  #", "  #"],
    "5": ["###", "#  ", "## ", "  #", "## "],
    "6": [" ##", "#  ", "## ", "# #", " # "],
    "7": ["###", "  #", " # ", " # ", " # "],
    "8": [" # ", "# #", " # ", "# #", " # "],
    "9": [" # ", "# #", " ##", "  #", "## "],
    "-": ["   ", "   ", "###", "   ", "   "],
    ".": ["   ", "   ", "   ", "   ", " # "],
    " ": ["   ", "   ", "   ", "   ", "   "],
}


def big_text(scr, y: int, x: int, text: str, scale: int, attr):
    """Dibuja `text` con la microfuente 3x5 escalada en bloques.

    Escala en los dos ejes: cada píxel del glifo ocupa scale x scale celdas
    (si solo se escalara a lo ancho, las letras salen a rayas). Las celdas
    que caen fuera de pantalla se descartan: en un terminal pequeño interesa
    recortar, no abortar el repintado entero."""
    h, w = scr.getmaxyx()
    for i, ch in enumerate(text):
        glyph = FONT3X5.get(ch, FONT3X5[" "])
        for r, line in enumerate(glyph):
            for c, px in enumerate(line):
                if px == " ":
                    continue
                px_x = x + i * 4 * scale + c * scale
                for dy in range(scale):
                    py = y + r * scale + dy
                    if 0 <= py < h and 0 <= px_x < w - 1:
                        scr.addstr(py, px_x, "█" * min(scale, w - 1 - px_x),
                                   attr)


def big_text_half(scr, y: int, x: int, text: str, attr):
    """Dibuja `text` con la microfuente 3x5 usando medio-bloques (▀ ▄ █):
    cada celda empaqueta 2 píxeles verticales, así que el texto queda más
    suave y compacto (3 filas de celda en vez de 5)."""
    h, w = scr.getmaxyx()
    for i, ch in enumerate(text):
        glyph = FONT3X5.get(ch, FONT3X5[" "])
        for pair in range(3):
            top = glyph[pair * 2]
            bottom = glyph[pair * 2 + 1] if pair * 2 + 1 < 5 else "   "
            py = y + pair
            if not 0 <= py < h:
                continue          # terminal pequeño: se recorta, no se aborta
            for c in range(3):
                t, b = top[c] != " ", bottom[c] != " "
                if t and b:
                    cell = "█"
                elif t:
                    cell = "▀"
                elif b:
                    cell = "▄"
                else:
                    continue
                px = x + i * 4 + c
                if 0 <= px < w - 1:
                    scr.addstr(py, px, cell, attr)


def lyric_glyph_text(text: str) -> str:
    """Adapta una línea de letra a la microfuente 3x5 (solo A-Z/0-9/-/.):
    mayúsculas y sin tildes (á->A, ñ->N...), para no dejar huecos en blanco
    por caracteres que el glifo no tiene."""
    decomposed = unicodedata.normalize("NFKD", text.upper())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def display_name(dirname: str) -> str:
    """Nombre de canción para la lista: sin 'lgpt_', corto y en mayúsculas."""
    name = dirname
    if name.startswith("lgpt_"):
        name = name[5:]
    name = name.split(".")[0]
    return name.upper()[:10]


def meter(value: float, width: int = 8) -> str:
    """Medidor retro de bloques: value 0-1."""
    value = min(max(value, 0.0), 1.0)
    filled = round(value * width)
    return "█" * filled + "░" * (width - filled)


class Player:
    def __init__(self, args):
        self.args = args
        self.buttons = args.buttons
        self.ui_queue: queue.SimpleQueue = queue.SimpleQueue()
        self.projects = find_projects(Path(args.songs))
        if not self.projects:
            sys.exit(f"No se encuentran proyectos LGPT en {args.songs}")
        self.index = 0
        song_filter = getattr(args, "song", None)
        if song_filter:
            for i, p in enumerate(self.projects):
                if song_filter.lower() in p.name.lower():
                    self.index = i
                    break
            else:
                print(f"[player] --song {song_filter!r} no encontrado, "
                      f"uso {self.projects[0].name}")
        self.engine_ref: dict = {}
        self.midi_in = None
        self._midi_retry_next = 0.0   # ver _ensure_midi_input: reconexión en caliente
        # El MIDI se usa solo de ENTRADA (el controlador). Los eventos para
        # los clientes del robot salen por TCP, no por un puerto MIDI.
        self.event_server: EventServer | None = None
        self.event_out: EventMidiOut | None = None
        self.recorder: WavRecorder | None = None
        self._notice: tuple | None = None   # (mensaje, timestamp) para la UI
        self._expected_dac_time: float | None = None  # reloj real esperado
        self.estado_audio = EstadoAudio(
            args.blocksize / float(args.samplerate) * 1000.0)
        self._restart = False               # STOP en el menú: relanzar
        self.stream = sd.OutputStream(
            samplerate=args.samplerate,
            channels=2,
            dtype="float32",
            blocksize=args.blocksize,
            device=args.device or None,
            callback=self._audio_callback,
        )

    # -- audio ----------------------------------------------------------------

    def _audio_callback(self, outdata, frames, time_info, status):
        t_entrada = time.perf_counter()
        est = self.estado_audio
        # `status` lo daba PortAudio desde siempre y no se miraba: es el aviso
        # directo de que el buffer se quedó vacío, sin depender de deducirlo
        # del reloj. Es la señal más fiable de corte real.
        if status:
            if getattr(status, "output_underflow", False):
                est.xruns += 1
                est.causa = "buffer vacío: no llegamos a tiempo"
            else:
                est.causa = f"aviso de PortAudio: {status}"
            self._set_notice(f"CORTE ({est.xruns}) {est.causa}")
        engine = self.engine_ref.get("engine")
        dac_time = time_info.outputBufferDacTime
        if engine is not None:
            expected = self._expected_dac_time
            if expected is not None:
                drift = dac_time - expected
                if drift > 0.002:      # >2ms: xrun real, no ruido de reloj
                    engine.catch_up(drift)
                    est.saltos += 1
                    est.causa = f"salto del reloj del DAC ({drift*1000:.0f}ms)"
                    self._set_notice(f"glitch recuperado ({drift * 1000:.0f}ms)")
        self._expected_dac_time = dac_time + frames / self.args.samplerate
        if engine is None:
            outdata[:] = 0
        else:
            # Reloj de pared de la primera muestra del bloque, para que el
            # engine pueda sellar los eventos con el instante en que sonarán.
            # dac_time va en el reloj del stream, no en el del sistema: se
            # pasa a reloj de pared con la diferencia contra currentTime.
            engine.block_time_ms = (
                time.time() + (dac_time - time_info.currentTime)) * 1000.0
            outdata[:] = engine.render(frames)
        recorder = self.recorder
        if recorder is not None:
            recorder.write(outdata)
        # Coste real de este bloque. Se mide al final, con todo hecho
        # (render + grabación), porque lo que provoca el corte
        # es el total, no solo el motor.
        ms = (time.perf_counter() - t_entrada) * 1000.0
        est.ultima_ms = ms
        est.bloques += 1
        if ms > est.peor_ms:
            est.peor_ms = ms
        # El peor reciente se olvida poco a poco: si no, un pico al arrancar
        # se queda en pantalla toda la sesión y deja de informar.
        est.peor_desde = max(ms, est.peor_desde * 0.999)
        if ms > est.presupuesto_ms * CARGA_AVISO:
            est.apurados += 1
            if not est.causa:
                est.causa = f"bloque apurado ({ms:.0f}ms de {est.presupuesto_ms:.0f})"

    def _load_song(self, index: int):
        project_dir = self.projects[index]
        old = self.engine_ref.get("engine")
        if old is not None:
            old.panic()                   # note off de notas MIDI colgadas
        engine = Engine(project_dir, sample_rate=self.args.samplerate,
                        audio_delay=self.args.delay,
                        wavs_dir=self.args.wavs_dir)
        engine.midi_out = self.event_out
        m = self.args.master_fx
        if m:
            engine.master_chain = MasterChain(
                self.args.samplerate,
                lo_db=float(m.get("eq_lo", 0.0)),
                mid_db=float(m.get("eq_mid", 0.0)),
                hi_db=float(m.get("eq_hi", 0.0)),
                limit_db=float(m.get("limit", -1.0)),
                release_s=float(m.get("release", 0.15)),
                gain_db=float(m.get("gain", 0.0)))
        engine.start()
        self._apply_song_config(project_dir, engine)
        self.engine_ref["engine"] = engine   # swap atómico de referencia
        return engine

    def _apply_song_config(self, project_dir: Path, engine: Engine):
        """Config por canción (robotraca.json en la carpeta del proyecto):
        mute de canales y targets de los knobs (canal:efecto).
        Sin JSON: sin mute y sin efectos."""
        import json
        cfg_file = project_dir / "robotraca.json"
        song_cfg = {}
        if cfg_file.is_file():
            try:
                song_cfg = json.loads(cfg_file.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                print(f"[config] {cfg_file.name}: {exc}")
        engine.muted = set(song_cfg.get("mute", []))
        if getattr(self.args, "mute_override", None) is not None:
            engine.muted = set(self.args.mute_override)
        # Compensación de presencia al final de la cadena de FX (ver
        # Engine.render/Channel.fx_presence): opt-in por canal, solo para
        # la pista en la que se esté trabajando, no global.
        presence_channels = set(song_cfg.get("presence", []))
        for ch in engine.channels:
            ch.fx_presence = ch.idx in presence_channels
        # Pistas cuyo acorde (param1/param2, ver Engine._chord_tones) se
        # manda al vocoder por el evento ACRD además de/en vez de sonar
        # localmente (ver Channel.vocoder_out).
        vocoder_channels = set(song_cfg.get("vocoder", []))
        for ch in engine.channels:
            ch.vocoder_out = ch.idx in vocoder_channels
        # Cantidad de cada efecto por canal (0-100), persistida por el mixer:
        # {"fx": {"2": {"acid": 80, "delay": 40}}}. Son los mismos nombres de
        # EFFECT_PRESETS que usan los targets de los pots.
        fx_cfg = song_cfg.get("fx", {})
        if isinstance(fx_cfg, dict):
            for ch_str, amounts in fx_cfg.items():
                try:
                    ci = int(ch_str)
                except (TypeError, ValueError):
                    continue
                if not 0 <= ci < len(engine.channels) \
                        or not isinstance(amounts, dict):
                    continue
                for name, val in amounts.items():
                    if name in EFFECT_PRESETS:
                        try:
                            engine.channels[ci].fx_amounts[name] = \
                                float(val) / 100.0
                        except (TypeError, ValueError):
                            pass
        # Mezcla dry/wet de cada efecto por canal (0-100), persistida por el
        # mixer: {"fx_mix": {"2": {"acid": 50}}}. Ausencia = 100 (100% wet,
        # igual que sin esto).
        fx_mix_cfg = song_cfg.get("fx_mix", {})
        if isinstance(fx_mix_cfg, dict):
            for ch_str, amounts in fx_mix_cfg.items():
                try:
                    ci = int(ch_str)
                except (TypeError, ValueError):
                    continue
                if not 0 <= ci < len(engine.channels) \
                        or not isinstance(amounts, dict):
                    continue
                for name, val in amounts.items():
                    if name in EFFECT_PRESETS:
                        try:
                            engine.channels[ci].fx_mix[name] = \
                                float(val) / 100.0
                        except (TypeError, ValueError):
                            pass
        # Volumen general de la canción (0-200, 100 = el del proyecto LGPT).
        # Sirve para igualar la sonoridad entre canciones sin tocar el
        # lgptsav.dat: unas están mezcladas más fuerte que otras.
        master = song_cfg.get("master")
        if master is not None:
            try:
                engine.master = engine.base_master * float(master) / 100.0
            except (TypeError, ValueError):
                print(f"[config] master inválido: {master!r}")
        # volumen de pads: número (todos) o dict por pad {"2": 40}
        pv = song_cfg.get("pad_volume", self.args.pad_volume)
        if isinstance(pv, dict):
            engine.pad_volume_map = {
                int(k) - 1: float(v) / 100 for k, v in pv.items()}
            # los pads que el dict no menciona siguen el volumen global,
            # no el que trae el engine de fábrica
            engine.pad_volume_default = float(self.args.pad_volume) / 100
        else:
            engine.pad_volume_map = {}
            engine.pad_volume_default = float(pv) / 100
        # targets por canción sobre el mapeo físico global de knobs
        song_pots = song_cfg.get("pots", {})
        self.args.pots.clear()
        for key, entry in self.args.hw_pots.items():
            if not isinstance(entry, dict):
                continue
            spec = parse_button_spec(entry.get("cc", ""))
            target = parse_pot_target(song_pots.get(key, ""))
            if spec is None or target is None:
                continue
            try:
                idx = int(key[3:]) - 1     # "pot3" -> 2
            except ValueError:
                continue
            if not 0 <= idx < 8:
                continue
            self.args.pots.append((spec, target, idx))
        # pots que solo se reenvían por red (ver NETCC_CHANNEL en el engine):
        # una lista de nombres de pot, no un dict target -> el control de red
        # es el propio número de pot ("pot3" -> reenvía como control 3).
        song_pots_red = set(song_cfg.get("pots_red", []))
        self.args.pots_red.clear()
        for key in song_pots_red:
            entry = self.args.hw_pots.get(key)
            if not isinstance(entry, dict):
                continue
            spec = parse_button_spec(entry.get("cc", ""))
            if spec is None:
                continue
            try:
                control = int(key[3:])     # "pot3" -> 3
            except ValueError:
                continue
            self.args.pots_red.append((spec, control))

    # -- UI curses --------------------------------------------------------------

    def _poll_buttons(self, context: str) -> str | None:
        """Traduce una acción de botón pendiente a la tecla equivalente."""
        try:
            action = self.ui_queue.get_nowait()
        except queue.Empty:
            return None
        if context == "list":
            return {"up": "up", "down": "down",
                    "play": "\n", "stop": "restart", "calib": "calib"}.get(action)
        return {"up": "p", "down": "n",
                "play": " ", "stop": "q"}.get(action)

    def _drain_buttons(self):
        while True:
            try:
                self.ui_queue.get_nowait()
            except queue.Empty:
                return

    def _midi_available(self, wanted: str | None) -> bool:
        """Como `_pick_port` pero sin imprimir nada: se llama cada pocos
        segundos desde `_ensure_midi_input` y no debe llenar la consola de
        avisos mientras el controlador está desenchufado."""
        try:
            import mido
            names = mido.get_input_names()
        except ImportError:
            return False
        if not wanted:
            return bool(names)
        base = wanted.rsplit(" ", 1)[0]
        return any(wanted.lower() in n.lower() or base.lower() in n.lower()
                   for n in names)

    def _ensure_midi_input(self):
        """Reconexión en caliente del controlador MIDI: si se enchufa
        después de arrancar el player, o se desenchufa un momento y vuelve,
        no debería hacer falta reiniciar. Se limita a comprobar cada 2s
        (mido.get_input_names() no es gratis) y solo actúa si cambia algo."""
        now = time.time()
        if now < self._midi_retry_next:
            return
        self._midi_retry_next = now + 2.0
        available = self._midi_available(self.args.midi)
        if self.midi_in is not None:
            if not available:
                self.midi_in.close()
                self.midi_in = None
                self._set_notice("MIDI desconectado")
        elif available:
            new_port = open_midi_input(
                self.args.midi, self.engine_ref, self.ui_queue, self.buttons,
                self.args.pots, self.args.pots_red)
            if new_port is not None:
                self.midi_in = new_port
                self._set_notice("MIDI reconectado")

    def _set_notice(self, msg: str):
        """Aviso breve en la línea inferior de la UI (thread-safe)."""
        self._notice = (msg, time.time())

    def _draw_notice(self, scr, curses, y: int):
        if self._notice is not None:
            msg, ts = self._notice
            if time.time() - ts < 3.0:
                try:
                    scr.addstr(y, 1, msg[:60],
                               curses.color_pair(5) | curses.A_BOLD)
                except curses.error:
                    pass
            else:
                self._notice = None

    def _draw_list(self, scr, curses):
        """ROBOTRACA a texto de consola + 3 canciones centradas (scroll
        infinito): prev/next con medio-bloques, seleccionada al doble."""
        scr.erase()
        h, w = scr.getmaxyx()
        names = [display_name(p.name) for p in self.projects]
        n = len(names)
        prev = names[(self.index - 1) % n]
        current = names[self.index]
        nxt = names[(self.index + 1) % n]
        # Tamaño fijo (el de "ABDUCCION") para toda la lista: si un título
        # no cabe ni a este tamaño, no se dibuja (en vez de encogerlo a una
        # fuente más pequeña o recortarlo a trozos por el borde).
        sel_scale = 1
        current_fits = len(current) * 4 * sel_scale <= w
        # bloque: título (1) + hueco + prev (3) + seleccionada + next (3)
        total_rows = 2 + 3 + 5 * sel_scale + 1 + 3
        y0 = max(0, (h - total_rows) // 2)
        title = "R O B O T R A C A"
        scr.addstr(y0, max(0, (w - len(title)) // 2), title,
                   self._pair_bright)
        y = y0 + 2
        big_text_half(scr, y, max(0, (w - len(prev) * 4) // 2), prev,
                      self._pair_dim)
        y += 3 + 1
        # Seleccionada en negativo: banda verde a todo el ancho y el nombre
        # en negro encima (con negro sobre verde, un espacio pinta el fondo
        # y un bloque lleno pinta la letra).
        rows_sel = 5 * sel_scale
        for r in range(rows_sel):
            yy = y + r
            if not 0 <= yy < h:
                continue
            # escribir en la última celda de la pantalla es error en curses
            width = w if yy < h - 1 else w - 1
            scr.addstr(yy, 0, " " * width, self._pair_neg)
        if current_fits:
            big_text(scr, y, max(0, (w - len(current) * 4 * sel_scale) // 2),
                     current, sel_scale, self._pair_neg)
        y += rows_sel + 1
        big_text_half(scr, y, max(0, (w - len(nxt) * 4) // 2), nxt,
                      self._pair_dim)
        self._draw_clients(scr, curses, w)
        self._draw_notice(scr, curses, h - 1)
        scr.refresh()

    def _draw_clients(self, scr, curses, w: int):
        """Iniciales de los clientes del robot en la esquina superior
        derecha: brillante = conectado, atenuada = ausente. Los conectados
        que no estén en la tabla de nombres salen como '?'."""
        if self.event_server is None:
            return
        conectadas = set(self.event_server.connected_ips())
        nombres = self.args.events.get("clients", {})
        marcas = [(nombres[ip][:1].upper(), ip in conectadas)
                  for ip in nombres]
        # los que conectan sin estar dados de alta: uno por cada IP
        marcas += [("?", True) for ip in conectadas if ip not in nombres]
        if not marcas:
            return
        x = max(0, w - len(marcas) * 2 - 1)
        for i, (letra, viva) in enumerate(marcas):
            attr = self._pair_bright if viva else self._pair_dim
            try:
                scr.addstr(0, x + i * 2, letra, attr)
            except curses.error:
                pass                      # pantalla estrecha: se recorta

    def _draw_song(self, scr, curses, engine: Engine):
        """Pantalla mínima de reproducción: estado, canción, BPM y progreso.

        Sin detalle por canal ni visualizador: el motor ya no aplica
        efectos de canal, así que no hay nada de eso que mostrar.
        """
        scr.erase()
        h, w = scr.getmaxyx()
        if engine.finished:
            state, color = "STOP ", 6
        elif engine.playing:
            state, color = "PLAY ", 2
        else:
            state, color = "PAUSA", 5
        row = max(engine.song_positions())
        pct = row / 255.0
        scr.addstr(0, 1, state, curses.color_pair(color) | curses.A_BOLD)
        scr.addstr(0, 7, engine.project.dir.name[:w - 8],
                   curses.color_pair(1) | curses.A_BOLD)
        scr.addstr(2, 1, f"{engine.tempo:.0f} BPM   {meter(pct, 20)} "
                         f"{pct * 100:5.1f}%"[:w - 2],
                   curses.color_pair(3))
        if engine.current_lyric:
            # Bloque completo (█), no medio-bloque (▀▄): la consola de la Pi
            # (15x50, fuente de consola básica) no tiene esos glifos y salía
            # distorsionada. Centrada en el hueco libre entre el BPM (fila 2)
            # y el aviso de teclas (fila h-2).
            lyric = lyric_glyph_text(engine.current_lyric)
            lyric_w = max(0, len(lyric) * 4 - 1)
            lyric_h = 5
            x = max(0, (w - lyric_w) // 2)
            top, bottom = 3, h - 3
            y = top + max(0, (bottom - top + 1 - lyric_h) // 2)
            big_text(scr, y, x, lyric, 1,
                     curses.color_pair(1) | curses.A_BOLD)
        scr.addstr(h - 1, 1,
                   "espacio: pausa  n/p: canción  q: lista"[:w - 2],
                   curses.color_pair(3))
        self._draw_notice(scr, curses, h - 2)
        scr.refresh()

    def _curses_main(self, scr):
        import curses
        try:
            curses.curs_set(0)
        except curses.error:
            pass                      # terminal sin cursor configurable
        curses.start_color()
        try:
            curses.use_default_colors()
            bg = -1
        except curses.error:
            bg = curses.COLOR_BLACK   # consola linux sin orig_pair
        # Paleta ROBOTRACA (terminal Pip-Boy: verde fósforo monocromo,
        # ámbar para estados; se complementa con setvtrgb en tty1)
        curses.init_pair(1, curses.COLOR_GREEN, bg)      # título/brillante
        curses.init_pair(2, curses.COLOR_GREEN, bg)      # selección
        curses.init_pair(3, curses.COLOR_GREEN, bg)      # secundario (dim)
        curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_GREEN)
        curses.init_pair(5, curses.COLOR_YELLOW, bg)     # pausa (ámbar)
        curses.init_pair(6, curses.COLOR_RED, bg)        # stop (ámbar osc)
        self._pair_bright = curses.color_pair(1) | curses.A_BOLD
        self._pair_sel = curses.color_pair(2) | curses.A_BOLD
        self._pair_dim = curses.color_pair(3) | curses.A_DIM
        self._pair_neg = curses.color_pair(4)      # negro sobre verde
        scr.timeout(100)
        engine = None
        needs_clear = True                # limpieza completa al cambiar de vista
        while True:                       # vista lista
            if needs_clear:
                scr.clear()
                needs_clear = False
            self._drain_buttons()
            self._ensure_midi_input()
            try:
                self._draw_list(scr, curses)
            except curses.error:
                pass                      # pantalla pequeña: recorte
            key = self._read_key(scr, curses, "list")
            if key is None:
                continue
            if key in ("q", "esc"):
                return
            if key in ("restart", "r"):
                # Salir del bucle: run() limpia y vuelve a ejecutar el
                # programa. Sirve para recoger cambios de configuración o
                # para salir de un estado colgado sin tocar el teclado.
                self._restart = True
                return
            if key == "c":
                self._config_view(scr, curses)
                self.projects = find_projects(Path(self.args.songs)) or \
                    self.projects
                self.index %= len(self.projects)
                needs_clear = True
            elif key in ("m", "calib"):
                self._calib_view(scr, curses)
                self._drain_buttons()
                needs_clear = True
            elif key in ("up", "k"):
                self.index = (self.index - 1) % len(self.projects)
            elif key in ("down", "j"):
                self.index = (self.index + 1) % len(self.projects)
            elif key in ("\r", "\n"):
                engine = self._load_song(self.index)
                self._drain_buttons()
                scr.clear()               # limpieza al entrar en la canción
                scr.timeout(100)
                while True:               # vista canción
                    self._ensure_midi_input()
                    try:
                        self._draw_song(scr, curses, engine)
                    except curses.error:
                        pass              # pantalla pequeña: recorte
                    key = self._read_key(scr, curses, "song")
                    if key is None:
                        continue
                    if key == " ":
                        engine.push_event(
                            "pause" if engine.playing else "play")
                    elif key == "n":
                        self.index = (self.index + 1) % len(self.projects)
                        engine = self._load_song(self.index)
                    elif key == "p":
                        self.index = (self.index - 1) % len(self.projects)
                        engine = self._load_song(self.index)
                    elif key in ("q", "esc"):
                        engine.push_event("stop")
                        self.engine_ref["engine"] = None
                        scr.timeout(100)
                        needs_clear = True
                        break

    def _config_view(self, scr, curses):
        """Pantalla de configuración: edita lttileplayer.toml en el propio
        dispositivo (audio, MIDI, botones, pots, delay)."""
        from lgpt_setup import POT_DEFAULT_TARGETS, write_config
        cfg_path = Path(self.args.config)
        cfg = load_config(cfg_path)
        cfg.setdefault("audio", {})
        cfg.setdefault("midi", {})
        cfg.setdefault("buttons", {})
        cfg.setdefault("pots", {})

        def current_values():
            b = cfg["buttons"]
            nb = sum(1 for v in b.values() if v)
            npots = sum(1 for v in cfg["pots"].values()
                        if isinstance(v, dict) and v.get("cc"))
            return [
                ("audio", "Salida de audio",
                 cfg["audio"].get("output") or "(por defecto)"),
                ("midi_out", "Salida MIDI",
                 cfg["midi"].get("output") or "(desactivada)"),
                ("midi_in", "Entrada MIDI",
                 cfg["midi"].get("input") or "(auto)"),
                ("buttons", "Capturar botones", f"{nb}/4 asignados"),
                ("pots", "Capturar potenciómetros", f"{npots}/8 asignados"),
                ("save", "» GUARDAR y volver", ""),
                ("back", "» Volver sin guardar", ""),
            ]

        sel = 0
        while True:
            fields = current_values()
            scr.erase()
            h, w = scr.getmaxyx()
            scr.addstr(1, 2, "CONFIGURACIÓN",
                       curses.color_pair(1) | curses.A_BOLD)
            for i, (_key, label, value) in enumerate(fields):
                attr = curses.color_pair(4) if i == sel else 0
                scr.addstr(3 + i, 2, f"{label:<26}"[:26], attr)
                if value:
                    scr.addstr(3 + i, 29, value[:w - 31], attr)
            scr.addstr(h - 2, 2, "↑↓: moverse   enter: editar   "
                                 "q: volver", curses.color_pair(3))
            scr.addstr(h - 1, 2, "audio/puertos MIDI: se aplican al "
                                 "reiniciar el player", curses.color_pair(3))
            scr.refresh()
            key = self._read_key(scr, curses, "list")
            if key is None:
                continue
            if key in ("q", "esc", "c"):
                return
            if key in ("up", "k"):
                sel = (sel - 1) % len(fields)
            elif key in ("down", "j"):
                sel = (sel + 1) % len(fields)
            elif key in ("\r", "\n"):
                action = fields[sel][0]
                if action == "back":
                    return
                if action == "save":
                    write_config(cfg, cfg_path)
                    self._apply_live_config(cfg)
                    return
                if action == "audio":
                    devs = ["(por defecto del sistema)"] + [
                        d["name"] for d in sd.query_devices()
                        if d["max_output_channels"] > 0]
                    cur = cfg["audio"].get("output") or devs[0]
                    val = self._choose(scr, curses, "Salida de audio",
                                       devs, cur)
                    if val is not None:
                        cfg["audio"]["output"] = "" if val == devs[0] else val
                elif action == "midi_out":
                    val = self._choose_midi(scr, curses, "salida",
                                            cfg["midi"].get("output", ""))
                    if val is not None:
                        cfg["midi"]["output"] = val
                elif action == "midi_in":
                    val = self._choose_midi(scr, curses, "entrada",
                                            cfg["midi"].get("input", ""))
                    if val is not None:
                        cfg["midi"]["input"] = val
                elif action == "buttons":
                    self._capture_view(scr, curses, cfg["buttons"],
                                       [("up", "ARRIBA"), ("down", "ABAJO"),
                                        ("play", "PLAY"),
                                        ("stop", "STOP")], None)
                elif action == "pots":
                    entries = []
                    for n in range(1, 9):
                        e = cfg["pots"].get(f"pot{n}", {})
                        target = (e.get("target")
                                  or POT_DEFAULT_TARGETS.get(n, ""))
                        entries.append((f"pot{n}", f"POT {n} ({target or 'libre'})",
                                        target))
                    self._capture_view(scr, curses, cfg["pots"], entries,
                                       POT_DEFAULT_TARGETS)

    def _load_calib_robots(self):
        """Lee bin/cliente.*.json y devuelve la lista de robots con sus
        motores (nombre, tiempo en ms, delay en ms). El sinte recibe todo el
        árbol versionado por rsync, así que estos ficheros están presentes."""
        import json
        bin_dir = Path(__file__).resolve().parent.parent / "bin"
        robots = []
        for path in sorted(bin_dir.glob("cliente.*.json")):
            try:
                data = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            pines = data.get("pines", {})
            if not pines:
                continue
            motores = [
                {
                    "pin": int(pin),
                    "nombre": info.get("nombre", f"Pin {pin}"),
                    "tiempo_ms": float(info.get("tiempo", 0.05)) * 1000.0,
                    "delay_ms": float(info.get("delay", 0)),
                }
                for pin, info in sorted(pines.items(), key=lambda kv: int(kv[0]))
            ]
            robots.append({
                "nombre": data.get("nombre") or data.get("name") or path.stem,
                "motores": motores,
            })
        return robots

    def _calib_view(self, scr, curses):
        """Calibración de motores manejada con el controlador (Akai LPD8):
        pad1 cambia robot, pad3 cambia motor, knob1/knob2 ajustan
        duración/delay (CALIB en vivo), pad4 arranca/para un pulso repetido
        del motor para ajustarlo de oído, pad2 guarda (CALSAVE). Sale con el
        botón STOP o con 'q'."""
        robots = self._load_calib_robots()
        if not robots:
            scr.erase()
            scr.addstr(1, 2, "No se encontraron ficheros bin/cliente.*.json",
                       curses.color_pair(3))
            scr.addstr(3, 2, "pulsa una tecla para volver")
            scr.refresh()
            scr.timeout(-1)
            scr.getch()
            scr.timeout(100)
            return
        if self.event_server is None:
            scr.erase()
            scr.addstr(1, 2, "Sin servidor de eventos: no se puede calibrar",
                       curses.color_pair(3))
            scr.addstr(3, 2, "pulsa una tecla para volver")
            scr.refresh()
            scr.timeout(-1)
            scr.getch()
            scr.timeout(100)
            return

        ri, mi = 0, 0
        pulse_on = False
        last_pulse = 0.0
        status = ""
        stop_spec = self.buttons.get("stop")

        # Entramos en modo calibración: el callback MIDI desvía TODO al
        # calib_queue (ver open_midi_input) y no dispara botones/pots/engine.
        cq = self.engine_ref.get("calib_queue")
        self._drain_calib_queue()
        self.engine_ref["calib_mode"] = True
        scr.nodelay(True)
        scr.timeout(80)
        try:
            while True:
                robot = robots[ri]
                motor = robot["motores"][mi]

                # Pulso: repite el golpe del motor seleccionado.
                now = time.time()
                if pulse_on and now - last_pulse >= CALIB_PULSE_INTERVAL_S:
                    self._calib_send(robot, motor)
                    self.event_server.emit("CALTEST",
                                           int(now * 1000),
                                           robot["nombre"], motor["pin"])
                    last_pulse = now

                self._calib_draw(scr, curses, robots, ri, mi, pulse_on, status)

                # Teclado (fallback en un PC con teclado).
                kc = scr.getch()
                if kc != -1:
                    if kc in (ord("q"), 27):
                        break
                    if kc in (curses.KEY_LEFT, ord("h")):
                        ri = (ri - 1) % len(robots); mi = 0; status = ""
                    elif kc in (curses.KEY_RIGHT, ord("l")):
                        ri = (ri + 1) % len(robots); mi = 0; status = ""
                    elif kc in (curses.KEY_UP, ord("k")):
                        mi = (mi - 1) % len(robot["motores"]); status = ""
                    elif kc in (curses.KEY_DOWN, ord("j")):
                        mi = (mi + 1) % len(robot["motores"]); status = ""
                    elif kc in (ord(" "), ord("t")):
                        pulse_on = not pulse_on; last_pulse = 0.0
                    elif kc in (ord("s"),):
                        status = self._calib_save(robot, motor)

                # Controlador MIDI (vía calib_queue).
                if cq is not None:
                    while True:
                        try:
                            mtype, ch, num, val = cq.get_nowait()
                        except queue.Empty:
                            break
                        if (stop_spec is not None and mtype == stop_spec[0]
                                and ch == stop_spec[1] and num == stop_spec[2]):
                            # botón STOP -> salir
                            raise _CalibExit
                        if mtype == "note_on" and val > 0 \
                                and ch == CALIB_PAD_CHANNEL:
                            if num == CALIB_PAD_ROBOT:
                                ri = (ri + 1) % len(robots); mi = 0; status = ""
                            elif num == CALIB_PAD_MOTOR:
                                mi = (mi + 1) % len(robot["motores"])
                                status = ""
                            elif num == CALIB_PAD_PULSE:
                                pulse_on = not pulse_on; last_pulse = 0.0
                            elif num == CALIB_PAD_SAVE:
                                status = self._calib_save(robot, motor)
                        elif mtype == "control_change" \
                                and ch == CALIB_KNOB_CHANNEL:
                            if num == CALIB_KNOB_DUR:
                                motor["tiempo_ms"] = _calib_scale(
                                    val, CALIB_DUR_MIN_MS, CALIB_DUR_MAX_MS)
                                self._calib_send(robot, motor); status = ""
                            elif num == CALIB_KNOB_DELAY:
                                motor["delay_ms"] = _calib_scale(
                                    val, CALIB_DELAY_MIN_MS, CALIB_DELAY_MAX_MS)
                                self._calib_send(robot, motor); status = ""
        except _CalibExit:
            pass
        finally:
            self.engine_ref["calib_mode"] = False
            self._drain_calib_queue()
            scr.timeout(100)

    def _drain_calib_queue(self):
        cq = self.engine_ref.get("calib_queue")
        if cq is None:
            return
        while True:
            try:
                cq.get_nowait()
            except queue.Empty:
                return

    def _calib_send(self, robot: dict, motor: dict):
        """Aplica en caliente (CALIB) el tiempo/delay actuales del motor."""
        self.event_server.emit(
            "CALIB", int(time.time() * 1000), robot["nombre"], motor["pin"],
            round(motor["tiempo_ms"]), round(motor["delay_ms"]))

    def _calib_save(self, robot: dict, motor: dict) -> str:
        """CALIB + CALSAVE: persiste el valor en el config.json del robot."""
        self._calib_send(robot, motor)
        self.event_server.emit("CALSAVE", int(time.time() * 1000),
                               robot["nombre"], motor["pin"])
        return f"guardado en {robot['nombre']}: {motor['nombre']}"

    def _calib_draw(self, scr, curses, robots, ri, mi, pulse_on, status):
        robot = robots[ri]
        motor = robot["motores"][mi]
        scr.erase()
        h, w = scr.getmaxyx()
        scr.addstr(1, 2, "CALIBRACIÓN DE MOTORES",
                   curses.color_pair(1) | curses.A_BOLD)
        scr.addstr(3, 2, "Robot:", curses.color_pair(3))
        scr.addstr(3, 12, robot["nombre"], curses.color_pair(2) | curses.A_BOLD)
        scr.addstr(4, 2, "Motor:", curses.color_pair(3))
        scr.addstr(4, 12, f"{motor['nombre']}  (pin {motor['pin']})",
                   curses.color_pair(2) | curses.A_BOLD)
        scr.addstr(6, 4, f"Duración   {motor['tiempo_ms']:6.0f} ms",
                   curses.color_pair(1))
        scr.addstr(7, 4, f"Delay      {motor['delay_ms']:+6.0f} ms",
                   curses.color_pair(1))
        estado = "PULSANDO ●" if pulse_on else "parado"
        scr.addstr(9, 4, f"Pulso: {estado}",
                   curses.color_pair(2 if pulse_on else 3)
                   | (curses.A_BOLD if pulse_on else 0))
        scr.addstr(h - 4, 2, "pad1: robot   pad3: motor",
                   curses.color_pair(3))
        scr.addstr(h - 3, 2, "knob1: duración   knob2: delay",
                   curses.color_pair(3))
        scr.addstr(h - 2, 2, "pad4: pulso on/off   pad2: guardar   "
                             "STOP/q: salir", curses.color_pair(3))
        if status:
            scr.addstr(h - 1, 2, status[:w - 3], curses.color_pair(5))
        scr.refresh()

    def _wait_midi_spec(self, scr, curses) -> str | None:
        """Espera un note on o CC y devuelve el spec; None si se cancela."""
        rq = self.engine_ref.get("raw_queue")
        if rq is not None:
            while True:
                try:
                    rq.get_nowait()
                except queue.Empty:
                    break
        while True:
            key = scr.getch()
            if key in (10, 13, 27, ord("q")):
                return None
            if rq is not None:
                try:
                    mtype, ch, num = rq.get_nowait()
                    if mtype == "note_on":
                        return f"note:{ch}:{num}"
                    if mtype == "control_change":
                        return f"cc:{ch}:{num}"
                except queue.Empty:
                    pass
            time.sleep(0.05)

    def _wait_quiet_midi(self, seconds: float = 0.6):
        """Espera a que deje de llegar MIDI (pot soltado)."""
        rq = self.engine_ref.get("raw_queue")
        quiet_since = None
        while True:
            got = False
            if rq is not None:
                while True:
                    try:
                        rq.get_nowait()
                        got = True
                    except queue.Empty:
                        break
            if got:
                quiet_since = None
            elif quiet_since is None:
                quiet_since = time.time()
            elif time.time() - quiet_since >= seconds:
                return
            time.sleep(0.05)

    def _apply_live_config(self, cfg: dict):
        """Botones y mapeo físico de knobs se aplican en caliente."""
        self.buttons.clear()
        self.buttons.update({
            a: parse_button_spec(s)
            for a, s in cfg.get("buttons", {}).items()})
        self.buttons.setdefault("calib", parse_button_spec(CALIB_OPEN_SPEC))
        self.args.hw_pots = cfg.get("pots", {})

    # -- widgets de la pantalla CONFIG ------------------------------------------

    def _choose(self, scr, curses, title, options, current) -> str | None:
        sel = options.index(current) if current in options else 0
        while True:
            scr.erase()
            scr.addstr(1, 2, title, curses.color_pair(1) | curses.A_BOLD)
            for i, opt in enumerate(options[:12]):
                attr = curses.color_pair(4) if i == sel else 0
                mark = " *" if opt == current else ""
                scr.addstr(3 + i, 2, f"{opt}{mark}"[:70], attr)
            scr.addstr(14, 2, "↑↓ + enter   q: cancelar", curses.color_pair(3))
            scr.refresh()
            key = self._read_key(scr, curses, "list")
            if key in ("q", "esc"):
                return None
            if key in ("up", "k"):
                sel = (sel - 1) % len(options[:12])
            elif key in ("down", "j"):
                sel = (sel + 1) % len(options[:12])
            elif key in ("\r", "\n"):
                return options[sel]

    def _choose_midi(self, scr, curses, kind, current) -> str | None:
        import mido
        if kind == "salida":
            names = mido.get_output_names()
            options = names + ["virtual", "off"]
        else:
            names = mido.get_input_names()
            options = names + ["auto", "off"]
        cur = current if current in options else (
            "virtual" if current == "virtual" else options[0])
        val = self._choose(scr, curses, f"Puerto MIDI de {kind}:", options, cur)
        if val is None:
            return None
        if kind == "salida":
            return "" if val == "off" else val
        return "" if val == "auto" else val

    def _capture_view(self, scr, curses, store: dict, entries, defaults):
        """Captura de botones/pots: lista acciones, enter espera un evento
        MIDI y guarda el spec. store se edita en vivo."""
        sel = 0
        while True:
            scr.erase()
            h, w = scr.getmaxyx()
            scr.addstr(1, 2, "CAPTURA MIDI", curses.color_pair(1) | curses.A_BOLD)
            for i, entry in enumerate(entries):
                key_name, label = entry[0], entry[1]
                cur = store.get(key_name, "")
                if isinstance(cur, dict):
                    cur = cur.get("cc", "")
                attr = curses.color_pair(4) if i == sel else 0
                scr.addstr(3 + i, 2, f"{label:<28}"[:28], attr)
                scr.addstr(3 + i, 31, (cur or "---")[:w - 33], attr)
            scr.addstr(h - 1, 2, "enter: capturar   d: borrar   q: volver",
                       curses.color_pair(3))
            scr.refresh()
            key = self._read_key(scr, curses, "list")
            if key in ("q", "esc"):
                return
            if key in ("up", "k"):
                sel = (sel - 1) % len(entries)
            elif key in ("down", "j"):
                sel = (sel + 1) % len(entries)
            elif key == "d":
                self._store_spec(store, entries[sel], "", defaults)
            elif key in ("\r", "\n"):
                self._capture_one(scr, curses, store, entries[sel], defaults)

    def _store_spec(self, store, entry, spec, defaults):
        key_name = entry[0]
        if key_name.startswith("pot"):
            n = int(key_name[3:])
            target = entry[2] if len(entry) > 2 else \
                (defaults or {}).get(n, "")
            store[key_name] = {"cc": spec, "target": target}
        else:
            store[key_name] = spec

    def _capture_one(self, scr, curses, store, entry, defaults):
        """Espera un evento MIDI y lo guarda; luego aguarda a que el flujo
        pare (para no capturar el mismo pot dos veces)."""
        self.engine_ref["capture_mode"] = True
        rq = self.engine_ref.get("raw_queue")
        try:
            scr.addstr(2, 31, "esperando MIDI... (enter: cancela)",
                       curses.color_pair(5))
            scr.refresh()
            if rq is not None:
                while True:
                    try:
                        rq.get_nowait()
                    except queue.Empty:
                        break
            spec = None
            while spec is None:
                key = scr.getch()
                if key in (10, 13, 27, ord("q")):
                    return
                if rq is not None:
                    try:
                        mtype, ch, num = rq.get_nowait()
                        if mtype == "note_on":
                            spec = f"note:{ch}:{num}"
                        elif mtype == "control_change":
                            spec = f"cc:{ch}:{num}"
                    except queue.Empty:
                        pass
                time.sleep(0.05)
            self._store_spec(store, entry, spec, defaults)
            scr.addstr(2, 31, f"{spec} — suelta el pot...          ")
            scr.refresh()
            # espera a que el flujo MIDI se detenga (0.6 s en silencio)
            quiet_since = None
            while True:
                got = False
                if rq is not None:
                    while True:
                        try:
                            rq.get_nowait()
                            got = True
                        except queue.Empty:
                            break
                if got:
                    quiet_since = None
                elif quiet_since is None:
                    quiet_since = time.time()
                elif time.time() - quiet_since >= 0.6:
                    return
                time.sleep(0.05)
        finally:
            self.engine_ref["capture_mode"] = False
            scr.addstr(2, 31, " " * 40)

    def _read_key(self, scr, curses, context: str) -> str | None:
        key = scr.getch()
        if key != -1:
            if key in (curses.KEY_UP,):
                return "up"
            if key in (curses.KEY_DOWN,):
                return "down"
            if key == 27:
                return "esc"
            try:
                return chr(key)
            except ValueError:
                return None
        return self._poll_buttons(context)

    def _run_headless(self):
        """Sin TTY: solo audio + botones MIDI (modo servicio)."""
        while True:
            self._ensure_midi_input()
            time.sleep(1.0)

    def run(self):
        ev = self.args.events
        if ev.get("enabled", True):
            port = int(ev.get("port", 8888))
            try:
                self.event_server = EventServer(
                    port=port, config=ev)
            except OSError as exc:
                # Caso típico en la Pi: el bridge viejo (servidor.service) ya
                # tiene el 8888. Mejor sonar sin eventos que no sonar.
                print(f"[eventos] no se puede abrir el puerto {port}: {exc}")
                print("[eventos] ¿está corriendo el servidor.service antiguo? "
                      "El player seguirá sin enviar eventos.")
            else:
                self.event_out = EventMidiOut(
                    self.event_server, self.engine_ref,
                    client_delay_ms=int(ev.get("delay", 1000)))
                print(f"[eventos] servidor TCP en el puerto "
                      f"{self.event_server.port}")
        self.engine_ref["raw_queue"] = queue.SimpleQueue()
        self.engine_ref["calib_queue"] = queue.SimpleQueue()
        # Pad fijo que abre la calibración desde la lista (notas fijas, ver
        # constantes CALIB_*). No pisa un mapeo existente del usuario.
        self.buttons.setdefault("calib", parse_button_spec(CALIB_OPEN_SPEC))
        self.midi_in = open_midi_input(
            self.args.midi, self.engine_ref, self.ui_queue, self.buttons,
            self.args.pots, self.args.pots_red)
        if getattr(self.args, "song", None) is not None:
            # --song fuerza selección por CLI: no tiene sentido pedirla y
            # quedarse en silencio esperando un botón MIDI o el menú curses.
            self._load_song(self.index)
        if self.args.record:
            self.recorder = WavRecorder(self.args.record, self.args.samplerate)
            print(f"[audio] grabando salida en {self.args.record}")
        self.stream.start()
        try:
            if sys.stdin.isatty():
                import curses
                curses.wrapper(self._curses_main)
            else:
                self._run_headless()
        finally:
            engine = self.engine_ref.get("engine")
            if engine is not None:
                engine.panic()
            self.stream.stop()
            self.stream.close()
            if self.recorder is not None:
                self.recorder.close()
            if self.event_server is not None:
                self.event_server.close()
            if self.midi_in is not None:
                self.midi_in.close()
        if self._restart:
            # Se relanza AQUÍ, ya fuera del finally: el audio, los sockets y
            # el MIDI están cerrados y curses ha devuelto la terminal, así
            # que el proceso nuevo encuentra libres el dispositivo y el
            # puerto 8888. execv reemplaza el proceso, no deja huérfanos.
            print("[player] reiniciando...")
            sys.stdout.flush()
            time.sleep(0.3)          # deja al SO soltar el audio y el socket
            os.execv(sys.executable, [sys.executable] + sys.argv)



def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=str(CONFIG_PATH),
                        help="archivo TOML de configuración")
    parser.add_argument("--songs", default=None,
                        help="directorio con proyectos lgpt_*")
    parser.add_argument("--device", default=None,
                        help="dispositivo de salida (nombre o índice PortAudio)")
    parser.add_argument("--midi", default=None,
                        help="puerto MIDI de entrada (nombre parcial)")
    parser.add_argument("--midi-out", default=None, dest="midi_out",
                        help="puerto MIDI de salida (nombre parcial o "
                             "'virtual')")
    parser.add_argument("--samplerate", type=int, default=None)
    parser.add_argument("--blocksize", type=int, default=None)
    parser.add_argument("--delay", type=float, default=None,
                        help="retardo de la salida de audio en segundos")
    parser.add_argument("--record", default=None, metavar="WAV",
                        help="graba la salida de audio a un archivo WAV")
    parser.add_argument("--song", default=None,
                        help="subcadena del nombre de la carpeta lgpt_* a "
                             "seleccionar (por defecto, la primera alfabética)")
    parser.add_argument("--mute", default=None, metavar="0,1,4",
                        help="canales a silenciar (0-7), separados por comas; "
                             "sobreescribe el 'mute' de robotraca.json")
    args = parser.parse_args()
    args.mute_override = (
        [int(x) for x in args.mute.split(",") if x.strip() != ""]
        if args.mute else None
    )

    cfg = load_config(Path(args.config))
    audio_cfg = cfg.get("audio", {})
    midi_cfg = cfg.get("midi", {})

    # Prioridad: línea de comandos > lttileplayer.toml > defecto
    args.songs = args.songs or cfg.get("songs_dir", DEFAULT_SONGS_DIR)
    # songs_dir relativo se resuelve contra la carpeta del programa, así el
    # mismo toml sirve en el PC de desarrollo y en la Pi (ambos usan "songs").
    songs_path = Path(args.songs)
    if not songs_path.is_absolute():
        songs_path = CONFIG_PATH.parent / songs_path
    args.songs = str(songs_path)
    args.device = args.device or audio_cfg.get("output") or None
    args.samplerate = args.samplerate or audio_cfg.get("samplerate", SAMPLE_RATE)
    args.blocksize = args.blocksize or audio_cfg.get("blocksize", 512)
    args.delay = args.delay if args.delay is not None else audio_cfg.get(
        "delay", 1.0)
    args.record = args.record or audio_cfg.get("record") or None
    args.midi = args.midi if args.midi is not None else midi_cfg.get("input", "")
    args.midi_out = (
        args.midi_out if args.midi_out is not None
        else midi_cfg.get("output", "")
    )
    args.buttons = {
        action: parse_button_spec(spec)
        for action, spec in cfg.get("buttons", {}).items()
    }
    args.hw_pots = cfg.get("pots", {})     # mapeo físico global (CC por knob)
    args.pots = []                          # targets (se arman por canción)
    args.pots_red = []                      # pots reenviados por red (idem)
    args.mute = cfg.get("channels", {}).get("mute", [])
    wd = audio_cfg.get("wavs_dir") or None
    if wd:                                   # relativo -> junto al programa
        wp = Path(wd)
        if not wp.is_absolute():
            wp = CONFIG_PATH.parent / wp
        wd = str(wp)
    args.wavs_dir = wd
    args.master_fx = cfg.get("master", {})   # EQ + limitador de la mezcla
    args.events = cfg.get("events", {})      # servidor TCP para los clientes
    args.pad_volume = audio_cfg.get("pad_volume", 60)

    prioridad = sube_prioridad()
    print(f"[audio] prioridad: {prioridad}")
    Player(args).run()


if __name__ == "__main__":
    main()
