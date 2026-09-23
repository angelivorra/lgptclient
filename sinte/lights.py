"""Luces DMX de la pista LUCES (canal LGPT 9, `LIGHTS_TRACK`).

Hardware (probado a mano, ver README): cable Eurolite USB-DMX512 = FTDI
FT232R "tonto" (protocolo Open DMX: 250 kbaud 8N2, break + MAB + start code
0 + canales, refrescado sin parar) y dos PAR U'King 36 LED en modo DMX de 7
canales:

    +0 dimmer · +1 R · +2 G · +3 B · +4 estrobo · +5 modo · +6 velocidad

(+5/+6 se dejan a 0: control manual, sin los programas internos).

Qué significa cada campo de un step de la pista LUCES (el formato LGPT no
cambia, se reinterpretan los mismos bytes):

- **nota** -> COLOR: índice en `PALETTE` (0 = APAGA). Vacía = no cambia.
- **instrumento** -> LUZ: vacío o 0 = todas; n = la luz n-ésima de la
  configuración (1 = IZQ, 2 = DER).
- **FX1/FX2**: `BRIL xx` brillo (dimmer 00-FF), `FADE xx` fundido al color
  nuevo en xx steps (0 = corte), `STRB xx` estrobo (00 = apagado).

Cada luz conserva su estado hasta que otro step lo cambia; al parar o
empezar la canción, todo se apaga.
"""

from __future__ import annotations

import heapq
import threading
import time
from typing import Iterable, Optional

EMPTY = 0xFF

# (nombre, (R, G, B)); el índice es el byte de nota guardado en la phrase.
PALETTE = (
    ("APAGA", (0, 0, 0)),
    ("ROJO", (255, 0, 0)),
    ("NARANJA", (255, 80, 0)),
    ("AMARILLO", (255, 200, 0)),
    ("VERDE", (0, 255, 0)),
    ("CIAN", (0, 255, 255)),
    ("AZUL", (0, 0, 255)),
    ("VIOLETA", (120, 0, 255)),
    ("MAGENTA", (255, 0, 255)),
    ("ROSA", (255, 60, 120)),
    ("BLANCO", (255, 255, 255)),
    ("CALIDO", (255, 150, 60)),
)

LIGHT_FX = ("BRIL", "FADE", "STRB")
LIGHT_FX_HELP = {
    "BRIL": "brillo de la luz (00 apagada, FF a tope)",
    "FADE": "fundido al color nuevo en xx steps (00 = corte)",
    "STRB": "estrobo: 00 apagado, más alto = más rápido",
}

DEFAULT_FIXTURES = {"IZQ": 1, "DER": 8}      # nombre -> dirección DMX
FIXTURE_CHANNELS = 7                          # U'King PAR en modo 7 canales
MIN_FRAME = 24                                # canales mínimos por trama
FPS = 40


def color_label(note) -> str:
    if note is None or note == EMPTY or not 0 <= note < len(PALETTE):
        return "----"
    return PALETTE[note][0]


def color_rgb(note):
    if note is None or not 0 <= note < len(PALETTE):
        return None
    return PALETTE[note][1]


def luz_label(instr, names: Iterable[str] = tuple(DEFAULT_FIXTURES)) -> str:
    """Etiqueta del campo LUZ: vacío/0 = TODAS, n = la luz n-ésima."""
    names = list(names)
    if instr is None or instr in (EMPTY, 0):
        return "TODAS"
    if 1 <= instr <= len(names):
        return names[instr - 1]
    return f"L{instr:02X}"


def luz_targets(instr, n_fixtures: int) -> Optional[list[int]]:
    """Índices de luz a los que afecta el step (None = todas)."""
    if instr is None or instr in (EMPTY, 0):
        return None
    i = instr - 1
    return [i] if 0 <= i < n_fixtures else []


class _Fixture:
    __slots__ = ("address", "rgb_from", "rgb_to", "t0", "dur", "dim",
                 "strobe")

    def __init__(self, address: int):
        self.address = address
        self.reset()

    def reset(self):
        self.rgb_from = (0, 0, 0)
        self.rgb_to = (0, 0, 0)
        self.t0 = 0.0
        self.dur = 0.0
        self.dim = 255
        self.strobe = 0

    def rgb(self, now_ms: float):
        if self.dur <= 0 or now_ms >= self.t0 + self.dur:
            return self.rgb_to
        k = max(0.0, (now_ms - self.t0) / self.dur)
        return tuple(round(a + (b - a) * k)
                     for a, b in zip(self.rgb_from, self.rgb_to))


class DmxOut:
    """Estado de las luces + hilo que manda la trama DMX por el cable.

    El engine llama a `event()` con el instante audible (ms de reloj,
    `Engine.event_time_ms`); el hilo aplica cada evento cuando llega su
    hora, así la luz cae con el golpe que se oye aunque haya audio_delay.
    Sin cable (o sin pyserial) sigue funcionando en memoria y reintenta
    abrir el puerto cada pocos segundos (hotplug)."""

    def __init__(self, port: str = "/dev/ttyUSB0",
                 fixtures: Optional[dict] = None, serial_factory=None):
        self.port = port
        fixtures = dict(fixtures or DEFAULT_FIXTURES)
        self.names = list(fixtures)
        self.fixtures = [_Fixture(int(a)) for a in fixtures.values()]
        self._serial_factory = serial_factory or _open_serial
        self._lock = threading.Lock()
        self._pending: list = []
        self._seq = 0
        self._ser = None
        self._next_open = 0.0
        self._stop = threading.Event()
        self._thread = None
        self.error: Optional[str] = None
        top = max((f.address + FIXTURE_CHANNELS - 1 for f in self.fixtures),
                  default=0)
        self.frame_len = max(MIN_FRAME, min(512, top))

    @classmethod
    def from_config(cls, cfg: Optional[dict]):
        """`[luces]` del TOML / "luces" del config.json de robotracker2:
        {"puerto": "/dev/ttyUSB0", "luces": {"IZQ": 1, "DER": 8}}.
        Sin sección o con `activo = false` devuelve None."""
        if not cfg or not cfg.get("activo", True):
            return None
        return cls(port=cfg.get("puerto", "/dev/ttyUSB0"),
                   fixtures=cfg.get("luces") or DEFAULT_FIXTURES)

    # -- API del engine -------------------------------------------------
    def event(self, t_ms: float, targets: Optional[list], color=None,
              bril=None, strobe=None, fade_s: float = 0.0):
        with self._lock:
            self._seq += 1
            heapq.heappush(self._pending, (t_ms, self._seq, targets, color,
                                           bril, strobe, fade_s))

    def blackout(self):
        """Todo apagado ya, y fuera los eventos pendientes."""
        with self._lock:
            self._pending.clear()
            for f in self.fixtures:
                f.reset()

    def transport_start(self):
        self.blackout()

    def transport_stop(self, finished: bool = False):
        self.blackout()

    # -- trama ------------------------------------------------------------
    def _apply_due(self, now_ms: float):
        while self._pending and self._pending[0][0] <= now_ms:
            t_ms, _seq, targets, color, bril, strobe, fade_s = \
                heapq.heappop(self._pending)
            idxs = (range(len(self.fixtures)) if targets is None
                    else targets)
            for i in idxs:
                f = self.fixtures[i]
                if color is not None:
                    f.rgb_from = f.rgb(t_ms)
                    f.rgb_to = tuple(color)
                    f.t0 = t_ms
                    f.dur = max(0.0, fade_s * 1000.0)
                if bril is not None:
                    f.dim = bril & 0xFF
                if strobe is not None:
                    f.strobe = strobe & 0xFF

    def frame(self, now_ms: Optional[float] = None) -> bytes:
        """Canales DMX 1..frame_len en el instante `now_ms`."""
        if now_ms is None:
            now_ms = time.time() * 1000.0
        levels = bytearray(self.frame_len)
        with self._lock:
            self._apply_due(now_ms)
            for f in self.fixtures:
                base = f.address - 1
                r, g, b = f.rgb(now_ms)
                vals = (f.dim, r, g, b, f.strobe, 0, 0)
                for k, v in enumerate(vals):
                    if 0 <= base + k < self.frame_len:
                        levels[base + k] = v
        return bytes(levels)

    # -- hilo de salida ----------------------------------------------------
    def start(self):
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="dmx",
                                            daemon=True)
            self._thread.start()
        return self

    def close(self):
        self.blackout()
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._ser is not None:
            try:
                self._send(bytes(self.frame_len))
                self._ser.close()
            except Exception:                         # noqa: BLE001
                pass
            self._ser = None

    @property
    def connected(self) -> bool:
        return self._ser is not None

    def _send(self, levels: bytes):
        ser = self._ser
        ser.break_condition = True
        time.sleep(0.00012)                  # break >= 88 us
        ser.break_condition = False
        time.sleep(0.000012)                 # mark after break >= 8 us
        ser.write(b"\x00" + levels)
        ser.flush()

    def _run(self):
        period = 1.0 / FPS
        while not self._stop.is_set():
            t0 = time.monotonic()
            levels = self.frame()
            if self._ser is None and t0 >= self._next_open:
                try:
                    self._ser = self._serial_factory(self.port)
                    self.error = None
                except Exception as e:                # noqa: BLE001
                    self.error = str(e)
                    self._next_open = t0 + 3.0
            if self._ser is not None:
                try:
                    self._send(levels)
                except Exception as e:                # noqa: BLE001
                    self.error = str(e)
                    try:
                        self._ser.close()
                    except Exception:                 # noqa: BLE001
                        pass
                    self._ser = None
                    self._next_open = t0 + 3.0
            self._stop.wait(max(0.0, period - (time.monotonic() - t0)))


def _open_serial(port: str):
    import serial                               # pyserial (opcional)
    return serial.Serial(port, baudrate=250000, bytesize=8, parity="N",
                         stopbits=2, timeout=0, write_timeout=0.5)
