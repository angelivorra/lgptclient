"""
Backend PySide6 — expone estado TCP y señales a QML
"""

import logging
import platform
from collections import deque
from datetime import datetime

from PySide6.QtCore import QObject, Signal, Slot, QTimer

from tcp_handler import TcpHandler
from config import QUEUE_UPDATE_INTERVAL_MS, LATE_THRESHOLD_MS, TCP_HOST, TCP_PORT

log = logging.getLogger(__name__)

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def note_name(n: int) -> str:
    return f"{NOTE_NAMES[n % 12]}{(n // 12) - 1}"


class TcpBackend(QObject):
    # timestamp, text, tag
    tcpEvent          = Signal(str, str, str)
    # connected, host:port
    connectionChanged = Signal(bool, str)
    # bpm actual (0 = parado / desconectado)
    bpmChanged        = Signal(float)
    # True = playing, False = stopped
    playStateChanged  = Signal(bool)
    # latencia media en ms
    latencyChanged    = Signal(float)
    # note (0-127), channel
    noteHit           = Signal(int, int)
    # controller, channel, value
    ccReceived        = Signal(int, int, int)
    # texto de error/warning
    errorEvent        = Signal(str, str)   # texto, tag ("warning"|"error")
    # estadísticas: notas, cc, bpm_msgs desde último START
    statsChanged      = Signal(int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._connected = False
        self._playing = False
        self._last_bpm = 0.0
        self._last_latency = 0.0
        self._stats = [0, 0, 0]   # [notas, cc, bpm_msgs]
        self._error_count = 0

        self.tcp = TcpHandler()
        self.tcp.add_listener(self._on_message)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(QUEUE_UPDATE_INTERVAL_MS)

    # ------------------------------------------------------------------ tick

    def _on_tick(self) -> None:
        self.tcp.process_messages()

        lat_avg, _ = self.tcp.get_latency_ms()
        if abs(lat_avg - self._last_latency) >= 1.0:
            self._last_latency = lat_avg
            self.latencyChanged.emit(lat_avg)

    # ------------------------------------------------------------------ message handler

    def _on_message(self, msg: dict) -> None:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        t = msg["type"]

        # Eventos de conexión internos
        if t == "_connected":
            self._connected = True
            addr = f"{self.tcp._host}:{self.tcp._port}"
            self.connectionChanged.emit(True, addr)
            self.tcpEvent.emit(ts, f"Conectado a {addr}", "success")
            return
        if t == "_disconnected":
            self._connected = False
            self.connectionChanged.emit(False, "")
            self._reset_play_state(ts)
            self.tcpEvent.emit(ts, "Conexión perdida, reconectando...", "warning")
            return
        if t == "_error":
            self.tcpEvent.emit(ts, f"Error: {msg['raw']}", "error")
            return

        lat = msg.get("latency_ms", 0.0)
        if lat > LATE_THRESHOLD_MS:
            self._error_count += 1
            self.errorEvent.emit(
                f"Latencia alta: {lat:.0f} ms ({t})", "warning"
            )

        if t == "START":
            self._playing = True
            self._stats = [0, 0, 0]
            self.playStateChanged.emit(True)
            self.tcpEvent.emit(ts, f"▶  START  (lat {lat:.0f} ms)", "success")

        elif t == "END":
            self._reset_play_state(ts)
            self.tcpEvent.emit(ts, f"■  END  (lat {lat:.0f} ms)", "warning")

        elif t == "BPM":
            bpm = msg["bpm"]
            self._stats[2] += 1
            if abs(bpm - self._last_bpm) >= 0.5:
                self._last_bpm = bpm
                self.bpmChanged.emit(bpm)
            self.tcpEvent.emit(ts, f"BPM  {bpm:.1f}  (lat {lat:.0f} ms)", "info")
            self.statsChanged.emit(*self._stats)

        elif t == "NOTA":
            note, ch, vel = msg["note"], msg["channel"], msg["velocity"]
            self._stats[0] += 1
            self.noteHit.emit(note, ch)
            self.tcpEvent.emit(
                ts,
                f"NOTA {note:3d} ({note_name(note)})  Ch {ch+1:2d}  Vel {vel:3d}"
                f"  (lat {lat:.0f} ms)",
                "midi_note",
            )
            self.statsChanged.emit(*self._stats)

        elif t == "CC":
            ctrl, ch, val = msg["controller"], msg["channel"], msg["value"]
            self._stats[1] += 1
            self.ccReceived.emit(ctrl, ch, val)
            self.tcpEvent.emit(
                ts,
                f"CC   {ctrl:3d}  Ch {ch+1:2d}  Val {val:3d}"
                f"  (lat {lat:.0f} ms)",
                "midi_cc",
            )
            self.statsChanged.emit(*self._stats)

        elif t == "SYNC":
            pass  # heartbeat — no se muestra en el log

        elif t == "CONFIG":
            self.tcpEvent.emit(
                ts,
                f"CONFIG  delay={msg.get('delay')}  debug={msg.get('debug')}"
                f"  ruido={msg.get('ruido')}  pantalla={msg.get('pantalla')}",
                "info",
            )

        elif t == "UNKNOWN":
            self._error_count += 1
            self.errorEvent.emit(f"Mensaje desconocido: {msg['raw']}", "error")
            self.tcpEvent.emit(ts, f"? {msg['raw']}", "error")

    def _reset_play_state(self, ts: str) -> None:
        if self._playing:
            self._playing = False
            self.playStateChanged.emit(False)
        self._last_bpm = 0.0
        self.bpmChanged.emit(0.0)

    # ------------------------------------------------------------------ slots QML

    @Slot(str, int)
    def connectToServer(self, host: str, port: int) -> None:
        log.info("connectToServer(%s, %d)", host, port)
        try:
            self.tcp.connect(host, port)
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.tcpEvent.emit(ts, f"Conectando a {host}:{port}...", "info")
        except Exception as e:
            log.exception("Error al conectar: %s", e)
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.tcpEvent.emit(ts, f"Error al conectar: {e}", "error")

    @Slot()
    def disconnectFromServer(self) -> None:
        self.tcp.disconnect()
        self._connected = False
        self.connectionChanged.emit(False, "")
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.tcpEvent.emit(ts, "Desconectado manualmente", "warning")
        self._reset_play_state(ts)

    @Slot(result=bool)
    def isConnected(self) -> bool:
        return self._connected

    @Slot(result=str)
    def getSystemInfo(self) -> str:
        return f"{platform.system()} {platform.release()}"

    @Slot(result=str)
    def getDefaultHost(self) -> str:
        return TCP_HOST

    @Slot(result=int)
    def getDefaultPort(self) -> int:
        return TCP_PORT

    @Slot(result=int)
    def getErrorCount(self) -> int:
        return self._error_count

    @Slot()
    def shutdown(self) -> None:
        self._timer.stop()
        self.tcp.disconnect()
