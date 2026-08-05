#!/usr/bin/env python3
"""Host LADSPA mínimo (ctypes) para el motor de audio de sinte.

Carga plugins LADSPA directamente del .so (sin servidor JACK ni host
externo) y los ejecuta en el hilo de audio.

Los efectos de canal se retiraron en una limpieza previa; el catálogo se
reconstruye desde cero empezando por `LadspaAutoFilter`/
`LadspaStereoAutoFilter` (filtro acid), sin alternativa en numpy — si el
.so no está instalado, el efecto falla al crearse en vez de aproximarse a
mano. Ver `EFECTOS_LADSPA.md` para el resto del catálogo de plugins de la
Pi.

Referencia: ladspa.h (LADSPA SDK).
"""

from __future__ import annotations

import ctypes
from pathlib import Path

import numpy as np


class _Descriptor(ctypes.Structure):
    _fields_ = [
        ("UniqueID", ctypes.c_ulong),
        ("Label", ctypes.c_char_p),
        ("Properties", ctypes.c_int),
        ("Name", ctypes.c_char_p),
        ("Maker", ctypes.c_char_p),
        ("Copyright", ctypes.c_char_p),
        ("PortCount", ctypes.c_ulong),
        ("PortDescriptors", ctypes.POINTER(ctypes.c_int)),
        ("PortNames", ctypes.POINTER(ctypes.c_char_p)),
        ("PortRangeHints", ctypes.c_void_p),
        ("ImplementationData", ctypes.c_void_p),
        ("instantiate", ctypes.c_void_p),
        ("connect_port", ctypes.c_void_p),
        ("activate", ctypes.c_void_p),
        ("run", ctypes.c_void_p),
        ("run_adding", ctypes.c_void_p),
        ("set_run_adding_gain", ctypes.c_void_p),
        ("deactivate", ctypes.c_void_p),
        ("cleanup", ctypes.c_void_p),
    ]


class LadspaPlugin:
    """Instancia genérica de un plugin LADSPA (un canal de audio)."""

    def __init__(self, path: str, unique_id: int, sample_rate: int):
        if not Path(path).is_file():
            raise FileNotFoundError(path)
        self._lib = ctypes.CDLL(path)
        desc_fn = self._lib.ladspa_descriptor
        desc_fn.restype = ctypes.POINTER(_Descriptor)
        desc_fn.argtypes = [ctypes.c_ulong]
        desc_ptr = None
        for i in range(512):
            d = desc_fn(i)
            if not d:
                break
            if d.contents.UniqueID == unique_id:
                desc_ptr = d
                break
        if desc_ptr is None:
            raise RuntimeError(f"plugin {unique_id} no encontrado en {path}")
        self._desc_ptr = desc_ptr
        desc = desc_ptr.contents

        instantiate = ctypes.CFUNCTYPE(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)(
            desc.instantiate)
        self._handle = instantiate(desc_ptr, sample_rate)
        if not self._handle:
            raise RuntimeError("instantiate falló")

        self._connect = ctypes.CFUNCTYPE(
            None, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p)(
            desc.connect_port)
        self._run = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_ulong)(
            desc.run)
        if desc.activate:
            activate = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(desc.activate)
            activate(self._handle)
        self._controls: dict[int, ctypes.c_float] = {}
        # Conecta TODOS los puertos de control, de entrada y de salida: el
        # plugin lee los de entrada y ESCRIBE en los de salida (latencia,
        # atenuación...) aunque no los usemos. Puntero sin conectar = segfault.
        LADSPA_PORT_INPUT = 0x1
        LADSPA_PORT_CONTROL = 0x4
        for port in range(desc.PortCount):
            flags = desc.PortDescriptors[port]
            if flags & LADSPA_PORT_CONTROL:
                self.set_control(port, 0.0)

    def set_control(self, port: int, value: float):
        f = self._controls.get(port)
        if f is None:
            f = ctypes.c_float(float(value))
            self._controls[port] = f
            self._connect(self._handle, port, ctypes.byref(f))
        else:
            f.value = float(value)

    def run(self, buf: np.ndarray, in_port: int, out_port: int):
        data = buf.ctypes.data_as(ctypes.c_void_p)
        self._connect(self._handle, in_port, data)
        self._connect(self._handle, out_port, data)
        self._run(self._handle, len(buf))


CAPS_PATH = "/usr/lib/ladspa/caps.so"
CAPS_AUTOFILTER_ID = 2593

# Puertos del C* AutoFilter
AF_MODE = 0
AF_FILTER = 1
AF_FREQ = 2             # 20-3800 Hz (log)
AF_Q = 3                # 0-1
AF_DEPTH = 4
AF_LFOENV = 5           # 0 = cutoff manual
AF_RATE = 6
AF_SHAPE = 7
AF_INPUT = 8
AF_OUTPUT = 9


class LadspaAutoFilter(LadspaPlugin):
    """C* AutoFilter (caps.so): filtro resonante acid, un canal.

    Configurado en modo manual (lfo/env a 0): el cutoff lo controla el pot,
    no una envolvente automática del propio plugin.
    """

    def __init__(self, sample_rate: int, path: str = CAPS_PATH):
        super().__init__(path, CAPS_AUTOFILTER_ID, sample_rate)
        self.set_control(AF_MODE, 0.0)         # 0 = low-pass (1 es HP)
        self.set_control(AF_FILTER, 0.0)
        self.set_control(AF_DEPTH, 1.0)
        self.set_control(AF_LFOENV, 0.0)
        self.set_control(AF_RATE, 0.25)
        self.set_control(AF_SHAPE, 1.0)

    def set(self, freq_hz: float, res: float):
        self.set_control(AF_FREQ, min(max(freq_hz, 20.0), 3800.0))
        self.set_control(AF_Q, min(max(res, 0.0), 1.0))

    def run(self, buf: np.ndarray):
        super().run(buf, AF_INPUT, AF_OUTPUT)


class LadspaStereoAutoFilter:
    """Dos instancias mono del AutoFilter para el buffer estéreo del canal."""

    def __init__(self, sample_rate: int):
        self.left = LadspaAutoFilter(sample_rate)
        self.right = LadspaAutoFilter(sample_rate)

    def set(self, freq_hz: float, res: float):
        self.left.set(freq_hz, res)
        self.right.set(freq_hz, res)

    def run(self, buf: np.ndarray):
        """buf (n, 2) float32, in-place."""
        left = np.ascontiguousarray(buf[:, 0])
        self.left.run(left)
        buf[:, 0] = left
        right = np.ascontiguousarray(buf[:, 1])
        self.right.run(right)
        buf[:, 1] = right


DECIMATOR_PATH = "/usr/lib/ladspa/decimator_1202.so"
DECIMATOR_ID = 1202

# Puertos del Decimator (confirmados con `analyseplugin`)
DEC_BITS = 0        # 1-24
DEC_SRATE = 1       # 0.001*sr - 1*sr
DEC_INPUT = 2
DEC_OUTPUT = 3


class LadspaDecimator(LadspaPlugin):
    """Decimator (decimator_1202.so): bitcrush digital, un canal.

    Medido con senoidal y con el bajo real: bajar el sample rate por sí
    solo no cambia nada en un fundamental grave (queda muy por encima de
    Nyquist aunque se baje al 2% del sample rate), así que aquí solo se
    controla la profundidad de bits (sample rate fijo). Por encima de 10
    bits es prácticamente transparente; entre 8 y 4 se oye crujido
    creciente; por debajo de 3 la onda queda casi cuadrada (crest factor
    1.0), demasiado roto para uso normal."""

    def __init__(self, sample_rate: int, path: str = DECIMATOR_PATH):
        super().__init__(path, DECIMATOR_ID, sample_rate)
        self.set_control(DEC_SRATE, float(sample_rate))

    def set(self, bits: float):
        self.set_control(DEC_BITS, min(max(bits, 1.0), 24.0))

    def run(self, buf: np.ndarray):
        super().run(buf, DEC_INPUT, DEC_OUTPUT)


class LadspaStereoDecimator:
    """Dos instancias mono del Decimator para el buffer estéreo."""

    def __init__(self, sample_rate: int):
        self.left = LadspaDecimator(sample_rate)
        self.right = LadspaDecimator(sample_rate)

    def set(self, bits: float):
        self.left.set(bits)
        self.right.set(bits)

    def run(self, buf: np.ndarray):
        """buf (n, 2) float32, in-place."""
        left = np.ascontiguousarray(buf[:, 0])
        self.left.run(left)
        buf[:, 0] = left
        right = np.ascontiguousarray(buf[:, 1])
        self.right.run(right)
        buf[:, 1] = right


DELAYORAMA_PATH = "/usr/lib/ladspa/delayorama_1402.so"
DELAYORAMA_ID = 1402

# Puertos del Delayorama (confirmados con `analyseplugin`)
DRM_SEED = 0
DRM_INPUT_GAIN = 1      # dB
DRM_FEEDBACK = 2        # %
DRM_TAPS = 3
DRM_FIRST_DELAY = 4     # s
DRM_DELAY_RANGE = 5     # s
DRM_DELAY_CHANGE = 6
DRM_DELAY_RANDOM = 7    # %
DRM_AMP_CHANGE = 8
DRM_AMP_RANDOM = 9      # %
DRM_MIX = 10            # 0-1, dry/wet
DRM_INPUT = 11
DRM_OUTPUT = 12


class LadspaDelayorama(LadspaPlugin):
    """Delayorama (delayorama_1402.so): 3 ecos a 0.4/0.8/1.2s, cada uno
    más flojo que el anterior, un canal.

    Primera versión: 2 taps al mismo nivel, sin caída — sobre una pista
    que suena todo el rato (no un solo golpe) eso amontona muchos ecos
    igual de fuertes y satura de repeticiones. `Amplitude change` a 0.4
    hace que cada tap sea menos de la mitad de fuerte que el anterior
    (medido con un pulso: 0.0425 -> 0.033 -> 0.0196), así que a partir del
    tercero ya es casi inaudible — "resuena 2-3 veces" en vez de un eco
    plano sin fin. `feedback` se deja en 0: los taps son fijos (3), no una
    realimentación que pueda alargarse sola."""

    def __init__(self, sample_rate: int, path: str = DELAYORAMA_PATH):
        super().__init__(path, DELAYORAMA_ID, sample_rate)
        self.set_control(DRM_SEED, 0.0)
        self.set_control(DRM_INPUT_GAIN, 0.0)
        self.set_control(DRM_FEEDBACK, 0.0)
        self.set_control(DRM_TAPS, 3.0)
        self.set_control(DRM_FIRST_DELAY, 0.4)
        self.set_control(DRM_DELAY_RANGE, 0.8)     # taps a 0.4, 0.8 y 1.2s
        self.set_control(DRM_DELAY_CHANGE, 1.0)
        self.set_control(DRM_DELAY_RANDOM, 0.0)
        self.set_control(DRM_AMP_CHANGE, 0.4)      # cada tap decae a <mitad del anterior
        self.set_control(DRM_AMP_RANDOM, 0.0)

    def set(self, mix: float):
        self.set_control(DRM_MIX, min(max(mix, 0.0), 1.0))

    def run(self, buf: np.ndarray):
        super().run(buf, DRM_INPUT, DRM_OUTPUT)


class LadspaStereoDelayorama:
    """Dos instancias mono del Delayorama para el buffer estéreo."""

    def __init__(self, sample_rate: int):
        self.left = LadspaDelayorama(sample_rate)
        self.right = LadspaDelayorama(sample_rate)

    def set(self, mix: float):
        self.left.set(mix)
        self.right.set(mix)

    def run(self, buf: np.ndarray):
        """buf (n, 2) float32, in-place."""
        left = np.ascontiguousarray(buf[:, 0])
        self.left.run(left)
        buf[:, 0] = left
        right = np.ascontiguousarray(buf[:, 1])
        self.right.run(right)
        buf[:, 1] = right


COMB_PATH = "/usr/lib/ladspa/comb_1190.so"
COMB_ID = 1190

# Puertos del Comb filter (confirmados con `analyseplugin`)
COMB_SEPARATION = 0     # Hz, 16-640
COMB_FEEDBACK = 1       # -0.99 a 0.99
COMB_INPUT = 2
COMB_OUTPUT = 3


class LadspaComb(LadspaPlugin):
    """Comb filter (comb_1190.so): peine de resonancias, un canal.

    Se probó antes Ringmod with LFO para el mismo hueco (textura
    metálica): el plugin resultó inestable en este host — mismo código,
    misma entrada, y en 5 ejecuciones seguidas el pico pasaba de 0.15 a
    ~1e27 sin motivo determinista (memoria sin inicializar dentro del
    propio plugin). El comb filter, comprobado igual 5 veces seguidas, da
    siempre el mismo resultado.

    Separación de bandas fija; el pot solo mueve el feedback (0 = sin
    efecto, cerca de 0.99 = resonancia metálica sostenida)."""

    def __init__(self, sample_rate: int, path: str = COMB_PATH,
                 separation_hz: float = 200.0):
        super().__init__(path, COMB_ID, sample_rate)
        self.set_control(COMB_SEPARATION,
                          min(max(separation_hz, 16.0), 640.0))

    def set(self, feedback: float):
        self.set_control(COMB_FEEDBACK, min(max(feedback, -0.99), 0.99))

    def run(self, buf: np.ndarray):
        super().run(buf, COMB_INPUT, COMB_OUTPUT)


class LadspaStereoComb:
    """Dos instancias mono del Comb filter para el buffer estéreo."""

    def __init__(self, sample_rate: int, separation_hz: float = 200.0):
        self.left = LadspaComb(sample_rate, separation_hz=separation_hz)
        self.right = LadspaComb(sample_rate, separation_hz=separation_hz)

    def set(self, feedback: float):
        self.left.set(feedback)
        self.right.set(feedback)

    def run(self, buf: np.ndarray):
        """buf (n, 2) float32, in-place."""
        left = np.ascontiguousarray(buf[:, 0])
        self.left.run(left)
        buf[:, 0] = left
        right = np.ascontiguousarray(buf[:, 1])
        self.right.run(right)
        buf[:, 1] = right


BODE_PATH = "/usr/lib/ladspa/bode_shifter_1431.so"
BODE_ID = 1431

# Puertos del Bode frequency shifter (confirmados con `analyseplugin`)
BODE_SHIFT = 0      # Hz, 0-5000
BODE_INPUT = 1
BODE_DOWN_OUT = 2   # no se usa, hace falta un buffer válido igualmente
BODE_UP_OUT = 3
BODE_LATENCY = 4    # control de salida, se ignora (ya lo conecta el init genérico)


class LadspaBodeShifter(LadspaPlugin):
    """Bode frequency shifter (bode_shifter_1431.so): desplaza todas las
    frecuencias una cantidad fija en Hz (no multiplica, como un pitch
    shifter), así que las relaciones armónicas se rompen — timbre
    inarmónico/alienígena. Un canal, usa solo la salida "Up".

    A diferencia de un plugin normal de un único par entrada/salida, este
    tiene DOS salidas de audio (Down/Up) más un puerto de latencia; no
    puede reutilizar `LadspaPlugin.run()` (que conecta el mismo buffer a
    entrada y salida) porque aquí entrada y salidas son buffers distintos.

    Probado con senoidal y con el bajo real en todo el rango 0-5000 Hz:
    estable, RMS/pico prácticamente constantes (solo cambia el timbre)."""

    def __init__(self, sample_rate: int, path: str = BODE_PATH):
        super().__init__(path, BODE_ID, sample_rate)
        self._down = np.zeros(0, dtype=np.float32)
        self._up = np.zeros(0, dtype=np.float32)

    def set(self, shift_hz: float):
        self.set_control(BODE_SHIFT, min(max(shift_hz, 0.0), 5000.0))

    def run(self, buf: np.ndarray):
        """buf (n,) float32, in-place: se sustituye por la salida Up."""
        n = len(buf)
        if len(self._down) != n:
            self._down = np.zeros(n, dtype=np.float32)
            self._up = np.zeros(n, dtype=np.float32)
        self._connect(self._handle, BODE_INPUT,
                      buf.ctypes.data_as(ctypes.c_void_p))
        self._connect(self._handle, BODE_DOWN_OUT,
                      self._down.ctypes.data_as(ctypes.c_void_p))
        self._connect(self._handle, BODE_UP_OUT,
                      self._up.ctypes.data_as(ctypes.c_void_p))
        self._run(self._handle, n)
        buf[:] = self._up


class LadspaStereoBodeShifter:
    """Dos instancias mono del Bode frequency shifter para el buffer
    estéreo."""

    def __init__(self, sample_rate: int):
        self.left = LadspaBodeShifter(sample_rate)
        self.right = LadspaBodeShifter(sample_rate)

    def set(self, shift_hz: float):
        self.left.set(shift_hz)
        self.right.set(shift_hz)

    def run(self, buf: np.ndarray):
        """buf (n, 2) float32, in-place."""
        left = np.ascontiguousarray(buf[:, 0])
        self.left.run(left)
        buf[:, 0] = left
        right = np.ascontiguousarray(buf[:, 1])
        self.right.run(right)
        buf[:, 1] = right


DJ_EQ_PATH = "/usr/lib/ladspa/dj_eq_1901.so"
DJ_EQ_ID = 1901
DJ_EQ_LO, DJ_EQ_MID, DJ_EQ_HI = 0, 1, 2
DJ_EQ_IN_L, DJ_EQ_IN_R, DJ_EQ_OUT_L, DJ_EQ_OUT_R = 3, 4, 5, 6

LIMITER_PATH = "/usr/lib/ladspa/fast_lookahead_limiter_1913.so"
LIMITER_ID = 1913
LIM_GAIN, LIM_LIMIT, LIM_RELEASE = 0, 1, 2
LIM_IN_L, LIM_IN_R, LIM_OUT_L, LIM_OUT_R = 4, 5, 6, 7


class _StereoInOut(LadspaPlugin):
    """Plugin estéreo con puertos separados de entrada y salida (no puede
    usar LadspaPlugin.run(), que conecta el mismo buffer a ambos)."""

    _PORTS: tuple = ()          # (in_l, in_r, out_l, out_r)

    def process(self, left: np.ndarray, right: np.ndarray,
                out_l: np.ndarray, out_r: np.ndarray):
        il, ir, ol, orr = self._PORTS
        self._connect(self._handle, il, left.ctypes.data_as(ctypes.c_void_p))
        self._connect(self._handle, ir, right.ctypes.data_as(ctypes.c_void_p))
        self._connect(self._handle, ol, out_l.ctypes.data_as(ctypes.c_void_p))
        self._connect(self._handle, orr, out_r.ctypes.data_as(ctypes.c_void_p))
        self._run(self._handle, len(left))


class LadspaDjEq(_StereoInOut):
    """EQ de 3 bandas tipo DJ (dj_eq_1901.so): graves, medios y agudos en dB."""

    _PORTS = (DJ_EQ_IN_L, DJ_EQ_IN_R, DJ_EQ_OUT_L, DJ_EQ_OUT_R)

    def __init__(self, sample_rate: int, path: str = DJ_EQ_PATH):
        super().__init__(path, DJ_EQ_ID, sample_rate)

    def set(self, lo_db: float, mid_db: float, hi_db: float):
        self.set_control(DJ_EQ_LO, min(max(lo_db, -70.0), 6.0))
        self.set_control(DJ_EQ_MID, min(max(mid_db, -70.0), 6.0))
        self.set_control(DJ_EQ_HI, min(max(hi_db, -70.0), 6.0))


class LadspaLimiter(_StereoInOut):
    """Limitador con lookahead (fast_lookahead_limiter_1913.so): red de
    seguridad del master, para que ningún pico llegue a fondo de escala."""

    _PORTS = (LIM_IN_L, LIM_IN_R, LIM_OUT_L, LIM_OUT_R)

    def __init__(self, sample_rate: int, path: str = LIMITER_PATH):
        super().__init__(path, LIMITER_ID, sample_rate)

    def set(self, gain_db: float, limit_db: float, release_s: float):
        self.set_control(LIM_GAIN, min(max(gain_db, -20.0), 20.0))
        self.set_control(LIM_LIMIT, min(max(limit_db, -20.0), 0.0))
        self.set_control(LIM_RELEASE, min(max(release_s, 0.01), 2.0))
