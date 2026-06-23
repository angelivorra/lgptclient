"""
Manejador de conexiones MIDI
"""

import os
import threading
import queue
import time
from collections import deque
from typing import Callable, Optional, List

try:
    import mido
    MIDO_AVAILABLE = True
except ImportError:
    MIDO_AVAILABLE = False

from config import FILTERED_MESSAGES

# --- Detección de BPM desde MIDI Clock --------------------------------------
# MIDI Clock envía 24 pulsos por negra (PPQN). Medimos la duración de cada negra
# COMPLETA (24 pulsos): como el groove/swing de LGPT es periódico dentro de la
# negra, una negra entera dura siempre lo mismo y el groove se anula.
#
# La negra suelta aún tiene jitter de temporización (±2 BPM), así que:
#   1) suavizamos con un filtro EMA,
#   2) si el cambio supera JUMP_THRESHOLD adoptamos el valor al instante
#      (sin rampa al cambiar de tempo),
#   3) el valor mostrado es entero con histéresis para que no parpadee ±1.
PULSES_PER_BEAT = 24
EMA_ALPHA = 0.2           # 0..1; menor = más suave pero más lento
JUMP_THRESHOLD_BPM = 7.0  # salto mayor a esto → adopción inmediata
HYSTERESIS_BPM = 0.75     # margen para cambiar el entero mostrado

# Log de depuración (BPM_DEBUG=1 para activarlo)
BPM_DEBUG = os.environ.get("BPM_DEBUG", "0") == "1"
BPM_DEBUG_FILE = os.environ.get("BPM_DEBUG_FILE", "/tmp/bpm_debug.log")


class MidiHandler:
    """Gestiona la conexión y lectura de eventos MIDI"""

    def __init__(self):
        self.port: Optional[object] = None
        self.port_name: Optional[str] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.message_queue = queue.Queue()
        self.listeners: List[Callable] = []
        # BPM desde MIDI Clock (ver constantes arriba)
        self.bpm: float = 0.0       # valor mostrado (entero, con histéresis)
        self._ema: float = 0.0      # estimación suavizada interna
        self._clock_times: deque = deque(maxlen=PULSES_PER_BEAT + 1)
        self._pulse_count: int = 0
        self._last_clock_time: float = 0.0
        self._bpm_log = None

    @staticmethod
    def is_available() -> bool:
        return MIDO_AVAILABLE

    @staticmethod
    def get_backend_name() -> str:
        if MIDO_AVAILABLE:
            return mido.backend.name
        return "No disponible"

    @staticmethod
    def get_input_ports() -> List[str]:
        if not MIDO_AVAILABLE:
            return []
        try:
            return mido.get_input_names()
        except Exception:
            return []

    def add_listener(self, callback: Callable) -> None:
        if callback not in self.listeners:
            self.listeners.append(callback)

    def remove_listener(self, callback: Callable) -> None:
        if callback in self.listeners:
            self.listeners.remove(callback)

    def connect(self, port_name: str) -> bool:
        if not MIDO_AVAILABLE:
            return False
        self.disconnect()
        self.reset_bpm()
        if BPM_DEBUG:
            try:
                self._bpm_log = open(BPM_DEBUG_FILE, "w", buffering=1)
                self._bpm_log.write("# t_mono\tbeat_dur_s\tbeat_bpm\treported_bpm\tn_median\n")
            except Exception:
                self._bpm_log = None
        self.port = mido.open_input(port_name)
        self.port_name = port_name
        self.running = True
        self.thread = threading.Thread(target=self._listen, daemon=True)
        self.thread.start()
        return True

    def disconnect(self) -> None:
        # Señalar parada y esperar a que el hilo MIDI termine ANTES de cerrar el
        # puerto, para no tocar Python desde el hilo durante el cierre (evita el
        # fallo "PyGILState_Release" al finalizar el intérprete).
        self.running = False
        t = self.thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=1.0)
        self.thread = None
        if self.port:
            try:
                self.port.close()
            except Exception:
                pass
            self.port = None
            self.port_name = None
        self.reset_bpm()
        if self._bpm_log:
            try:
                self._bpm_log.close()
            except Exception:
                pass
            self._bpm_log = None

    def is_connected(self) -> bool:
        return self.port is not None and self.running

    def _listen(self) -> None:
        while self.running and self.port:
            try:
                for msg in self.port.iter_pending():
                    if msg.type == 'clock':
                        self._on_clock()
                        continue
                    if msg.type not in FILTERED_MESSAGES:
                        self.message_queue.put(msg)
                threading.Event().wait(0.001)
            except Exception:
                break

    def _on_clock(self) -> None:
        """Calcula el BPM a partir de los pulsos de MIDI Clock (24 PPQN).

        Mide la duración de cada negra completa (24 pulsos) — inmune al groove,
        que es periódico dentro de la negra — y reporta la mediana de las
        últimas MEDIAN_BEATS negras. Ante un salto grande de tempo vacía la
        ventana para adoptar el nuevo BPM de inmediato.
        """
        now = time.monotonic()
        self._last_clock_time = now
        self._clock_times.append(now)
        self._pulse_count += 1

        # Solo evaluamos al completar una negra (cada 24 pulsos)
        if self._pulse_count % PULSES_PER_BEAT != 0:
            return
        if len(self._clock_times) <= PULSES_PER_BEAT:
            return  # aún no hay una negra completa de historial

        beat_dur = self._clock_times[-1] - self._clock_times[-1 - PULSES_PER_BEAT]
        if beat_dur <= 0:
            return
        beat_bpm = 60.0 / beat_dur

        # 1) EMA, con adopción inmediata si el salto es grande (cambio de tempo)
        if self._ema == 0.0 or abs(beat_bpm - self._ema) > JUMP_THRESHOLD_BPM:
            self._ema = beat_bpm
        else:
            self._ema += EMA_ALPHA * (beat_bpm - self._ema)

        # 2) Entero mostrado con histéresis (evita parpadeo ±1 cerca de .5)
        if self.bpm == 0.0 or abs(self._ema - self.bpm) >= HYSTERESIS_BPM:
            self.bpm = float(round(self._ema))

        if self._bpm_log:
            try:
                self._bpm_log.write(
                    f"{now:.4f}\t{beat_dur:.4f}\t{beat_bpm:.2f}\t{self._ema:.2f}\t{self.bpm:.0f}\n"
                )
            except Exception:
                pass

    def get_bpm(self) -> float:
        """Devuelve el BPM actual, o 0 si no llegan pulsos de clock (parado)."""
        if self._last_clock_time and (time.monotonic() - self._last_clock_time) > 1.5:
            self.bpm = 0.0
        return self.bpm

    def reset_bpm(self) -> None:
        """Reinicia el cálculo de BPM (al parar la canción)."""
        self._clock_times.clear()
        self._pulse_count = 0
        self.bpm = 0.0
        self._ema = 0.0
        self._last_clock_time = 0.0

    def process_messages(self) -> None:
        try:
            while True:
                msg = self.message_queue.get_nowait()
                for listener in self.listeners:
                    try:
                        listener(msg)
                    except Exception:
                        pass
        except queue.Empty:
            pass


class MidiMessage:
    """Utilidades para formatear mensajes MIDI"""

    NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    @classmethod
    def note_name(cls, note_number: int) -> str:
        octave = (note_number // 12) - 1
        note = cls.NOTE_NAMES[note_number % 12]
        return f"{note}{octave}"

    @classmethod
    def format_message(cls, msg) -> tuple:
        if msg.type == 'note_on':
            text = f"NOTE ON  | Ch: {msg.channel:2d} | Nota: {msg.note:3d} ({cls.note_name(msg.note)}) | Vel: {msg.velocity:3d}"
            return text, "midi_note"

        elif msg.type == 'note_off':
            text = f"NOTE OFF | Ch: {msg.channel:2d} | Nota: {msg.note:3d} ({cls.note_name(msg.note)}) | Vel: {msg.velocity:3d}"
            return text, "midi_note"

        elif msg.type == 'control_change':
            text = f"CC       | Ch: {msg.channel:2d} | CC: {msg.control:3d} | Val: {msg.value:3d}"
            return text, "midi_cc"

        elif msg.type == 'program_change':
            text = f"PROGRAM  | Ch: {msg.channel:2d} | Prog: {msg.program:3d}"
            return text, "midi_cc"

        elif msg.type == 'pitchwheel':
            text = f"PITCH    | Ch: {msg.channel:2d} | Val: {msg.pitch}"
            return text, "midi_cc"

        elif msg.type == 'aftertouch':
            text = f"ATOUCH   | Ch: {msg.channel:2d} | Val: {msg.value:3d}"
            return text, "midi_other"

        elif msg.type == 'polytouch':
            text = f"PTOUCH   | Ch: {msg.channel:2d} | Nota: {msg.note:3d} | Val: {msg.value:3d}"
            return text, "midi_other"

        else:
            text = f"{msg.type.upper():8s} | {msg}"
            return text, "midi_other"
