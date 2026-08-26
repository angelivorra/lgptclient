"""Cliente TCP persistente para recibir eventos del servidor LGPT.

Protocolo: líneas de texto UTF-8 terminadas en \\n, campos separados por coma.
  START,<ts_ms>                       → canción arrancada
  END,<ts_ms>                         → canción parada
  BPM,<ts_ms>,<bpm>                   → tempo actual (entero, solo llega cuando cambia)
  SYNC,<ts_ms>                        → heartbeat, también sincroniza el reloj (ver abajo)
  CC,<ts_ms>,<valor>,<canal>,<control> → pots de red (canal 9, ver _NETCC_CHANNEL)
"""

from __future__ import annotations

import socket
import subprocess
import threading
import time

import liblo


SERVER_HOST = "192.168.0.2"
SERVER_PORT = 8888
_BACKOFF_INITIAL = 2
_BACKOFF_MAX = 30

# El vocoder no tiene NTP (misma red aislada que el sinte, ver
# bin/cliente_final/main.py:sync_clock_to_server): sin esto su reloj deriva
# libremente y los timestamps absolutos de NOTA/CC/ACRD (comparados contra
# time.time() local, p.ej. en carla_runner.py) pueden acabar apuntando al
# pasado o a semanas en el futuro. Mismo mecanismo que ya usan maleta y
# sombrilla: ajustar con 'date -s' al recibir cada SYNC si el desfase supera
# el umbral.
TIME_SYNC_THRESHOLD_MS = 200

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

# Pots de red (`pots_red` en el JSON de la canción, ver NETCC_CHANNEL en
# sinte/lgpt_engine.py): llegan como CC,<ts>,<valor>,<canal=9>,<control>, y a
# diferencia de NOTA/ACRD se aplican EN CUANTO llegan, sin la programación
# `ts + delay_ms` de carla_runner.py — es un gesto de control en directo, no
# algo que deba cuadrar con el ritmo de la canción.
_NETCC_CHANNEL = 9
_NETCC_REVERB_DELAY = 3   # knob 3: reverb + delay a la vez
_NETCC_DISTORTION = 7     # knob 7: distorsión (Calf Saturator, antes Temper)

_REVERB_PLUGIN_ID = 4
_REVERB_WET_PARAM_IDX = 7
# "de cero a la posición actual": el tope no es 1.0, es lo que ya hay
# mezclado en prod/template01.carxp (Calf Reverb, Wet Amount) — el knob
# funciona como un send, nunca por encima de lo que el preset ya mezcla.
_REVERB_WET_MAX = 0.244094491004944

_DELAY_WET_PARAM_IDX = 15
_DELAY_WET_MAX = 0.25   # Calf Vintage Delay, Wet — mismo criterio

# Distorsión: Calf Saturator (id 3 del rack, sustituye a Temper). El knob 7
# controla el "amount" = parámetro "Saturation" (symbol drive), idx 12 de Carla,
# rango del puerto 0.1 (limpio) .. 10 (fuerte). Mix queda fijo a 1 en el preset.
_DIST_PLUGIN_ID = 3
_SAT_DRIVE_PARAM_IDX = 12
_SAT_DRIVE_MIN = 0.1
_SAT_DRIVE_MAX = 10.0


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


class _NetPotSink:
    """Aplica los pots de red (ver `_NETCC_*` arriba) a Carla por OSC,
    inmediato y sin estado — cada mensaje pisa al anterior."""

    def __init__(self) -> None:
        self._addr = liblo.Address(_CARLA_OSC_HOST, _CARLA_OSC_PORT, liblo.TCP)

    def _set(self, plugin_id: int, param_idx: int, value: float) -> None:
        try:
            liblo.send(
                self._addr, f"/Carla/{plugin_id}/set_parameter_value",
                param_idx, value,
            )
        except (OSError, IOError) as exc:
            print(f"[tcp] OSC a Carla falló (pot de red, plugin {plugin_id}): "
                  f"{exc}", flush=True)

    def apply(self, control: int, value: int) -> None:
        frac = max(0, min(127, value)) / 127.0
        if control == _NETCC_REVERB_DELAY:
            reverb_wet = frac * _REVERB_WET_MAX
            delay_wet = frac * _DELAY_WET_MAX
            # TEMP: traza de net-pot (quitar tras depurar el "delay a 0 sigue
            # oyéndose"). Muestra el valor que llega y los wet que se mandan.
            print(f"[netpot] ctrl={control} val={value} frac={frac:.3f} "
                  f"reverb_wet={reverb_wet:.4f} delay_wet={delay_wet:.4f}",
                  flush=True)
            self._set(_REVERB_PLUGIN_ID, _REVERB_WET_PARAM_IDX, reverb_wet)
            self._set(_DELAY_PLUGIN_ID, _DELAY_WET_PARAM_IDX, delay_wet)
        elif control == _NETCC_DISTORTION:
            drive = _SAT_DRIVE_MIN + frac * (_SAT_DRIVE_MAX - _SAT_DRIVE_MIN)
            print(f"[netpot] ctrl={control} val={value} frac={frac:.3f} "
                  f"sat_drive={drive:.3f}", flush=True)
            self._set(_DIST_PLUGIN_ID, _SAT_DRIVE_PARAM_IDX, drive)


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
        self._net_pots = _NetPotSink()

    def _sync_clock_to_server(self, server_ts_ms: int) -> None:
        """Ajusta el reloj del sistema a la hora del servidor, igual que
        bin/cliente_final/main.py:sync_clock_to_server (mismo umbral, misma
        llamada 'sudo -n date -s'): el usuario 'patch' del vocoder ya tiene
        NOPASSWD:ALL, así que no hace falta tocar sudoers."""
        local_ms = time.time() * 1000
        drift_ms = server_ts_ms - local_ms
        if abs(drift_ms) < TIME_SYNC_THRESHOLD_MS:
            return
        epoch = server_ts_ms / 1000.0
        try:
            result = subprocess.run(
                ["sudo", "-n", "date", "-s", f"@{epoch:.3f}"],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                print(f"[tcp] Reloj ajustado al servidor (desfase {drift_ms/1000:.1f}s)", flush=True)
            else:
                print(f"[tcp] No se pudo ajustar el reloj: {result.stderr.decode().strip()}", flush=True)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"[tcp] Error ajustando el reloj: {exc}", flush=True)

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
                ts = int(parts[1])
                with self._state._lock:
                    self._state.last_sync_ms = ts
                self._sync_clock_to_server(ts)
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
        elif tag == "CC" and len(parts) >= 5:
            # CC,<ts_ms>,<valor>,<canal>,<control> (event_server.py). Solo nos
            # interesa el canal virtual de pots de red (ver _NETCC_CHANNEL);
            # el resto de CC (MDCC del tracker, etc.) no son para nosotros.
            try:
                value = int(parts[2])
                channel = int(parts[3])
                control = int(parts[4])
            except ValueError:
                return
            if channel == _NETCC_CHANNEL:
                self._net_pots.apply(control, value)

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
