"""Cliente TCP persistente para recibir eventos del servidor LGPT.

Protocolo: líneas de texto UTF-8 terminadas en \\n, campos separados por coma.
  START,<ts_ms>        → canción arrancada
  END,<ts_ms>          → canción parada
  BPM,<ts_ms>,<bpm>    → tempo actual (entero, solo llega cuando cambia)
"""

from __future__ import annotations

import socket
import threading
import time

import liblo


SERVER_HOST = "192.168.0.2"
SERVER_PORT = 8888
_BACKOFF_INITIAL = 2
_BACKOFF_MAX = 30

# OSC hacia Carla (lanzado por flask/app.py, escucha en 22752).
# Cambia el parámetro BPM del Calf Vintage Delay (7º plugin del rack en
# prod/template01.carxp, pluginId=6; control-port index 24 = "bpm").
# El plugin ya está en modo "Timing=BPM" (Index 23 = 0), así que basta con
# enviarle el nuevo BPM.
_CARLA_OSC_HOST = "127.0.0.1"
_CARLA_OSC_PORT = 22752
_DELAY_PLUGIN_ID = 6
_DELAY_BPM_PARAM_IDX = 24
_DELAY_BPM_MIN = 30.0  # límites del puerto LV2 'bpm' del Calf Vintage Delay
_DELAY_BPM_MAX = 300.0


class _CarlaBpmSink:
    """Envía el BPM al delay de Carla por OSC. Tolerante a Carla caído."""

    def __init__(self) -> None:
        self._addr = liblo.Address(_CARLA_OSC_HOST, _CARLA_OSC_PORT, liblo.TCP)
        self._last_sent: float | None = None

    def set_bpm(self, bpm: float) -> None:
        clamped = max(_DELAY_BPM_MIN, min(_DELAY_BPM_MAX, float(bpm)))
        if self._last_sent is not None and abs(clamped - self._last_sent) < 0.01:
            return
        try:
            liblo.send(
                self._addr,
                f"/Carla/{_DELAY_PLUGIN_ID}/set_parameter_value",
                _DELAY_BPM_PARAM_IDX,
                clamped,
            )
            self._last_sent = clamped
        except (OSError, IOError) as exc:
            # Carla puede estar reiniciándose por el supervisor; no abortar.
            print(f"[tcp] OSC a Carla falló (BPM={clamped}): {exc}", flush=True)


class BpmState:
    """Estado compartido thread-safe entre el cliente TCP y Flask."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.bpm: int | None = None
        self.connected: bool = False
        self.playing: bool = False
        self.last_sync_ms: int | None = None

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "bpm": self.bpm,
                "connected": self.connected,
                "playing": self.playing,
                "last_sync_ms": self.last_sync_ms,
            }


class _TCPClient:
    def __init__(self, state: BpmState) -> None:
        self._state = state
        self._carla = _CarlaBpmSink()

    def _handle_line(self, line: str) -> None:
        if not line:
            return
        parts = line.split(",")
        tag = parts[0]
        if tag == "BPM" and len(parts) >= 3:
            try:
                bpm_f = float(parts[2])
                bpm = round(bpm_f)
                ts = int(parts[1])
                with self._state._lock:
                    self._state.bpm = bpm
                    self._state.last_sync_ms = ts
                self._carla.set_bpm(bpm_f)
            except ValueError:
                pass
        elif tag == "SYNC" and len(parts) >= 2:
            try:
                with self._state._lock:
                    self._state.last_sync_ms = int(parts[1])
            except ValueError:
                pass
        elif tag == "START" and len(parts) >= 2:
            try:
                ts = int(parts[1])
                with self._state._lock:
                    self._state.playing = True
                    self._state.last_sync_ms = ts
                print("[tcp] START")
            except ValueError:
                pass
        elif tag == "END" and len(parts) >= 2:
            try:
                ts = int(parts[1])
                with self._state._lock:
                    self._state.playing = False
                    self._state.last_sync_ms = ts
                print("[tcp] END")
            except ValueError:
                pass

    def _connect_and_read(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((SERVER_HOST, SERVER_PORT))
            sock.settimeout(300)  # 5 min — detecta conexiones muertas sin falsos positivos
            with self._state._lock:
                self._state.connected = True
            print(f"[tcp] Conectado a {SERVER_HOST}:{SERVER_PORT}")
            buf = ""
            while True:
                chunk = sock.recv(1024).decode("utf-8", errors="replace")
                if not chunk:
                    break
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    self._handle_line(line.strip())

    def run(self) -> None:
        backoff = _BACKOFF_INITIAL
        while True:
            t_start = time.monotonic()
            try:
                self._connect_and_read()
            except Exception as exc:
                print(f"[tcp] Desconectado: {exc}")
            with self._state._lock:
                self._state.connected = False
                self._state.playing = False
            # Resetear backoff si la conexión duró más de 10 s (no fue un fallo inmediato)
            if time.monotonic() - t_start > 10:
                backoff = _BACKOFF_INITIAL
            time.sleep(backoff)
            backoff = min(backoff * 2, _BACKOFF_MAX)


_singleton: BpmState | None = None
_singleton_lock = threading.Lock()


def start_tcp_client() -> BpmState:
    """Lanza el cliente TCP en un hilo daemon y devuelve el estado compartido.

    Singleton para que gunicorn (master + worker) no abra dos conexiones.
    """
    global _singleton
    with _singleton_lock:
        if _singleton is not None:
            return _singleton
        state = BpmState()
        client = _TCPClient(state)
        thread = threading.Thread(target=client.run, daemon=True, name="tcp-bpm-client")
        thread.start()
        _singleton = state
        return state
