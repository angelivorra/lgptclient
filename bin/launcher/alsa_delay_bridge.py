#!/usr/bin/env python3
"""ALSA Delay Bridge

Proporciona la clase ALSADelayBridge que aplica un retardo fijo (por defecto 1.0 s)
entre un dispositivo de captura ALSA (ej. Loopback) y uno de reproducción físico.

Se usa por `run-lgpt.py` para conseguir una latencia controlada sin depender de
PipeWire/JACK. Basado en la versión integrada previa, extraído para separar
responsabilidades.
"""
import time
import logging
import threading
from collections import deque

try:
    import alsaaudio  # Requiere pyalsaaudio
except ImportError:  # pragma: no cover
    alsaaudio = None

# Valores por defecto (pueden sobreescribirse al instanciar)
DEFAULT_CAPTURE_DEVICE = 'hw:Loopback,1,0'
DEFAULT_PLAYBACK_DEVICE = 'hw:IQaudIODAC,0'
DEFAULT_RATE = 44100
DEFAULT_CHANNELS = 2
DEFAULT_FORMAT = 'S16_LE'
DEFAULT_PERIOD = 512
DEFAULT_DELAY = 1.0
DEFAULT_REPORT_INTERVAL = 5.0


class ALSADelayBridge:
    """Puente ALSA con retardo exacto configurado mediante cola FIFO.

    Estrategia: se llena un buffer objetivo (delay) y luego por cada bloque
    que entra se reproduce el bloque más antiguo, manteniendo retardo constante.
    """

    def __init__(self,
                 capture_device=DEFAULT_CAPTURE_DEVICE,
                 playback_device=DEFAULT_PLAYBACK_DEVICE,
                 rate=DEFAULT_RATE,
                 channels=DEFAULT_CHANNELS,
                 fmt=DEFAULT_FORMAT,
                 period=DEFAULT_PERIOD,
                 delay=DEFAULT_DELAY,
                 report_interval=DEFAULT_REPORT_INTERVAL):
        self.capture_device = capture_device
        self.playback_device = playback_device
        self.rate = rate
        self.channels = channels
        self.fmt = fmt
        self.period = period
        self.delay = delay
        self.report_interval = report_interval

        self.capture_pcm = None
        self.playback_pcm = None
        self.thread = None
        self.stop_event = threading.Event()
        self.queue = deque()
        self.bytes_per_frame = 2 * channels  # 16-bit
        self.target_delay_bytes = int(rate * delay * self.bytes_per_frame)
        self.queued_bytes = 0
        self.total_in = 0
        self.total_out = 0
        self.last_report = time.time()

    # --- Internos ---------------------------------------------------------
    def _pcm_format(self):
        if alsaaudio is None:
            return None
        mapping = {
            'S16_LE': alsaaudio.PCM_FORMAT_S16_LE,
            'S32_LE': alsaaudio.PCM_FORMAT_S32_LE,
        }
        return mapping.get(self.fmt, alsaaudio.PCM_FORMAT_S16_LE)

    def _open_devices(self):
        self.capture_pcm = alsaaudio.PCM(type=alsaaudio.PCM_CAPTURE, mode=alsaaudio.PCM_NORMAL, device=self.capture_device)
        self.capture_pcm.setchannels(self.channels)
        self.capture_pcm.setrate(self.rate)
        self.capture_pcm.setformat(self._pcm_format())
        self.capture_pcm.setperiodsize(self.period)

        self.playback_pcm = alsaaudio.PCM(type=alsaaudio.PCM_PLAYBACK, mode=alsaaudio.PCM_NORMAL, device=self.playback_device)
        self.playback_pcm.setchannels(self.channels)
        self.playback_pcm.setrate(self.rate)
        self.playback_pcm.setformat(self._pcm_format())
        self.playback_pcm.setperiodsize(self.period)

    def _loop(self):
        silence_chunk = b'\x00' * (self.period * self.bytes_per_frame)
        while not self.stop_event.is_set():
            try:
                length, data = self.capture_pcm.read()
            except Exception as e:
                logging.warning(f"Fallo lectura capture: {e}")
                time.sleep(0.01)
                continue
            if length <= 0:
                time.sleep(0.001)
                continue

            self.total_in += length
            self.queue.append(data)
            self.queued_bytes += len(data)

            if self.queued_bytes < self.target_delay_bytes:
                out = silence_chunk[:len(data)]
                try:
                    self.playback_pcm.write(out)
                    self.total_out += len(out) // self.bytes_per_frame
                except Exception as e:
                    logging.warning(f"Fallo write (silencio): {e}")
            else:
                oldest = self.queue.popleft()
                self.queued_bytes -= len(oldest)
                try:
                    self.playback_pcm.write(oldest)
                    self.total_out += len(oldest) // self.bytes_per_frame
                except Exception as e:
                    logging.warning(f"Fallo write audio: {e}")

            now = time.time()
            if now - self.last_report >= self.report_interval:
                delay_ms = self.queued_bytes / self.bytes_per_frame / self.rate * 1000
                logging.info(f"DelayBuffer ~{delay_ms:.1f} ms in_frames={self.total_in} out_frames={self.total_out}")
                self.last_report = now

    # --- API pública ------------------------------------------------------
    def start(self):
        if alsaaudio is None:
            logging.error("pyalsaaudio no instalado; no se puede iniciar ALSADelayBridge")
            return False
        try:
            self._open_devices()
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._loop, name="ALSADelayBridge", daemon=True)
            self.thread.start()
            logging.info("ALSADelayBridge iniciado: %s -> %s delay=%.3fs", self.capture_device, self.playback_device, self.delay)
            return True
        except Exception as e:
            logging.error(f"Error iniciando ALSADelayBridge: {e}")
            self.stop()
            return False

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.5)
        for pcm in [self.capture_pcm, self.playback_pcm]:
            try:
                if pcm:
                    pcm.close()
            except Exception:
                pass
        self.capture_pcm = None
        self.playback_pcm = None
        self.thread = None
        self.queue.clear()
        self.queued_bytes = 0
        logging.info("ALSADelayBridge detenido")
