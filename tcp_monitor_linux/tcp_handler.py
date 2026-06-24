"""
Cliente TCP para el servidor de eventos LGPT (server-midi.py, puerto 8888).

Protocolo recibido (líneas ASCII terminadas en \\n):
  CONFIG,<debug>,<ruido>,<pantalla>
  SYNC,<ts_ms>
  START,<ts_ms>
  END,<ts_ms>
  BPM,<ts_ms>,<bpm>
  NOTA,<ts_ms>,<note>,<channel>,<velocity>
  CC,<ts_ms>,<value>,<channel>,<controller>

Usa un hilo daemon con un socket bloqueante (igual que MidiHandler),
sin asyncio. Los mensajes parseados van a una queue.Queue que el
QTimer de Qt drena cada 10 ms llamando a process_messages().
"""

import logging
import queue
import socket
import threading
import time
from collections import deque
from typing import Callable, List, Optional

from config import RECONNECT_DELAY_S, LATENCY_WINDOW

log = logging.getLogger(__name__)


class TcpHandler:
    def __init__(self):
        self._host: str = ""
        self._port: int = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None

        self.message_queue: queue.Queue = queue.Queue()
        self.listeners: List[Callable] = []
        self._latency_samples: deque = deque(maxlen=LATENCY_WINDOW)

    # ------------------------------------------------------------------ API

    def add_listener(self, callback: Callable) -> None:
        if callback not in self.listeners:
            self.listeners.append(callback)

    def connect(self, host: str, port: int) -> None:
        self.disconnect()
        self._host = host
        self._port = port
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def disconnect(self) -> None:
        self._running = False
        # Cerrar el socket para desbloquear el recv del hilo
        sock = self._sock
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
            except Exception:
                pass
        t = self._thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=2.0)
        self._thread = None
        self._sock = None
        self._latency_samples.clear()

    def is_connected(self) -> bool:
        return self._running and self._sock is not None

    def process_messages(self) -> None:
        """Drena la queue y llama a los listeners. Llamar desde el hilo Qt."""
        try:
            while True:
                msg = self.message_queue.get_nowait()
                for listener in self.listeners:
                    try:
                        listener(msg)
                    except Exception as e:
                        log.exception("Error en listener: %s", e)
        except queue.Empty:
            pass

    def get_latency_ms(self) -> tuple:
        """Devuelve (media_ms, max_ms) de las últimas muestras."""
        if not self._latency_samples:
            return 0.0, 0.0
        s = list(self._latency_samples)
        return sum(s) / len(s), max(s)

    # ------------------------------------------------------------------ hilo

    def _run(self) -> None:
        log.info("Hilo TCP iniciado para %s:%s", self._host, self._port)
        while self._running:
            try:
                self._connect_and_read()
            except Exception as e:
                log.exception("Error inesperado en _connect_and_read: %s", e)
                self._put({"type": "_error", "raw": str(e)})

            if not self._running:
                break
            self._put({"type": "_disconnected", "raw": ""})
            log.info("Reconectando en %.1f s...", RECONNECT_DELAY_S)
            for _ in range(int(RECONNECT_DELAY_S * 10)):
                if not self._running:
                    log.info("Hilo TCP detenido")
                    return
                time.sleep(0.1)

    def _connect_and_read(self) -> None:
        log.debug("Intentando conectar a %s:%s", self._host, self._port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        try:
            sock.connect((self._host, self._port))
        except (OSError, ConnectionRefusedError) as e:
            log.warning("Conexión fallida: %s", e)
            sock.close()
            return

        sock.settimeout(None)
        self._sock = sock
        log.info("Conectado a %s:%s", self._host, self._port)
        self._put({"type": "_connected", "raw": ""})

        buf = ""
        lines_received = 0
        try:
            while self._running:
                try:
                    data = sock.recv(4096)
                except OSError as e:
                    log.warning("Socket cerrado: %s", e)
                    break
                if not data:
                    log.info("Servidor cerró la conexión")
                    break
                buf += data.decode(errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        lines_received += 1
                        msg = self._parse(line)
                        log.debug("< %s", line[:120])
                        self._put(msg)
        finally:
            log.info("Sesión TCP terminada tras %d líneas", lines_received)
            self._sock = None
            try:
                sock.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ parser

    def _parse(self, line: str) -> dict:
        now_ms = time.time() * 1000
        parts = line.split(",")
        msg_type = parts[0].upper()
        base = {"type": msg_type, "raw": line, "latency_ms": 0.0, "ts": 0}

        try:
            if msg_type in ("START", "END", "SYNC") and len(parts) >= 2:
                ts = int(parts[1])
                lat = max(0.0, now_ms - ts)
                self._latency_samples.append(lat)
                return {**base, "ts": ts, "latency_ms": lat}

            if msg_type == "BPM" and len(parts) >= 3:
                ts = int(parts[1])
                lat = max(0.0, now_ms - ts)
                self._latency_samples.append(lat)
                return {**base, "ts": ts, "latency_ms": lat,
                        "bpm": float(parts[2])}

            if msg_type == "NOTA" and len(parts) >= 5:
                ts = int(parts[1])
                lat = max(0.0, now_ms - ts)
                self._latency_samples.append(lat)
                return {**base, "ts": ts, "latency_ms": lat,
                        "note":     int(parts[2]),
                        "channel":  int(parts[3]),
                        "velocity": int(parts[4])}

            if msg_type == "CC" and len(parts) >= 5:
                ts = int(parts[1])
                lat = max(0.0, now_ms - ts)
                self._latency_samples.append(lat)
                return {**base, "ts": ts, "latency_ms": lat,
                        "value":      int(parts[2]),
                        "channel":    int(parts[3]),
                        "controller": int(parts[4])}

            if msg_type == "CONFIG" and len(parts) >= 2:
                return {**base,
                        "debug":    parts[1] if len(parts) > 1 else "",
                        "ruido":    parts[2] if len(parts) > 2 else "",
                        "pantalla": parts[3] if len(parts) > 3 else ""}

        except (ValueError, IndexError):
            pass

        return {**base, "type": "UNKNOWN"}

    def _put(self, msg: dict) -> None:
        self.message_queue.put_nowait(msg)
