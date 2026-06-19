"""
Backend PySide6 — expone estado MIDI y señales a QML
"""

import json
import os
import platform
from datetime import datetime

from PySide6.QtCore import QObject, Signal, Slot, QTimer

from midi_handler import MidiHandler, MidiMessage
from srt_recorder import SrtRecorder, TEXT_CC
from config import BATERIA_CONFIG_FILE, IMAGES_DIR


class MidiBackend(QObject):
    # timestamp, text, tag
    midiEvent = Signal(str, str, str)
    # connected, port_name
    connectionChanged = Signal(bool, str)
    # pad_name
    padHit = Signal(str)
    # image_path (vacío si no existe), channel, cc, value
    visualChanged = Signal(str, int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._connected = False
        self._bateria_config = self._load_bateria_config()

        self.srt = SrtRecorder()

        self.midi = MidiHandler()
        self.midi.add_listener(self._on_midi)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.midi.process_messages)
        self._timer.start(10)

    # ------------------------------------------------------------------ config

    def _load_bateria_config(self) -> dict:
        try:
            with open(BATERIA_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error cargando bateria_config.json: {e}")
            return {
                "channel": 0,
                "events": {},
                "labels": {"bombo": "Bombo", "caja1": "Caja 1", "caja2": "Caja 2", "crash": "Crash"},
                "colors": {"bombo": "#e74c3c", "caja1": "#3498db", "caja2": "#2ecc71", "crash": "#f39c12"},
            }

    # ------------------------------------------------------------------ MIDI listener (hilo MIDI → señales Qt)

    def _on_midi(self, msg) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        text, tag = MidiMessage.format_message(msg)
        self.midiEvent.emit(timestamp, text, tag)

        if msg.type == "note_on" and msg.velocity > 0:
            ch = self._bateria_config.get("channel", 0)
            if msg.channel == ch:
                events = self._bateria_config.get("events", {})
                for pad in events.get(str(msg.note), []):
                    self.padHit.emit(pad)

        if msg.type == "control_change" and 0 <= msg.channel <= 5 and msg.control != 7:
            image_path = self._find_image(msg.control, msg.value)
            self.visualChanged.emit(image_path, msg.channel, msg.control, msg.value)
            # Banco 002 (CC nº 2): registrar el texto como subtítulo si estamos grabando.
            if msg.control == TEXT_CC:
                self.srt.add_text(msg.value)

        # Transporte MIDI: 'start' inicia la grabación de subtítulos; 'stop' la vuelca a .srt.
        if msg.type == "start":
            self.srt.start()
            self.midiEvent.emit(timestamp, "▶ Grabando subtítulos (banco 002)...", "success")
        elif msg.type == "stop":
            path = self.srt.stop()
            if path:
                self.midiEvent.emit(timestamp, f"■ Subtítulos guardados: {path}", "success")
            else:
                self.midiEvent.emit(timestamp, "■ Grabación detenida (sin subtítulos)", "warning")

    # ------------------------------------------------------------------ image lookup

    def _find_image(self, cc_num: int, cc_val: int) -> str:
        folder_main = f"{cc_num:03d}"
        folder_sub = f"{cc_val:03d}"
        base_path = os.path.join(IMAGES_DIR, folder_main, folder_sub)
        extensions = (".png", ".jpg", ".jpeg", ".gif")

        if os.path.isdir(base_path):
            try:
                files = sorted(f for f in os.listdir(base_path) if f.lower().endswith(extensions))
                if files:
                    return os.path.join(base_path, files[0])
            except Exception:
                pass
        else:
            for ext in extensions:
                path = base_path + ext
                if os.path.exists(path):
                    return path
            parent = os.path.join(IMAGES_DIR, folder_main)
            if os.path.isdir(parent):
                for ext in extensions:
                    path = os.path.join(parent, folder_sub + ext)
                    if os.path.exists(path):
                        return path
        return ""

    # ------------------------------------------------------------------ slots llamados desde QML

    @Slot(result=bool)
    def isMidiAvailable(self) -> bool:
        return MidiHandler.is_available()

    @Slot(result=str)
    def getMidiBackendName(self) -> str:
        if MidiHandler.is_available():
            return MidiHandler.get_backend_name()
        return "No disponible"

    @Slot(result=str)
    def getSystemInfo(self) -> str:
        return f"{platform.system()} {platform.release()}"

    @Slot(result="QStringList")
    def getPorts(self) -> list:
        return MidiHandler.get_input_ports()

    @Slot(str)
    def connectPort(self, port_name: str) -> None:
        try:
            self.midi.connect(port_name)
            self._connected = True
            self.connectionChanged.emit(True, port_name)
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.midiEvent.emit(ts, f"Conectado a '{port_name}'", "success")
        except Exception as exc:
            self.connectionChanged.emit(False, "")
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.midiEvent.emit(ts, f"Error al conectar: {exc}", "error")

    @Slot()
    def disconnectPort(self) -> None:
        self.midi.disconnect()
        self._connected = False
        self.connectionChanged.emit(False, "")
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.midiEvent.emit(ts, "Desconectado", "warning")

    @Slot(result=bool)
    def isConnected(self) -> bool:
        return self._connected

    # -- batería config helpers

    @Slot(str, result=str)
    def getPadLabel(self, pad_name: str) -> str:
        return self._bateria_config.get("labels", {}).get(pad_name, pad_name)

    @Slot(str, result=str)
    def getPadColor(self, pad_name: str) -> str:
        return self._bateria_config.get("colors", {}).get(pad_name, "#888888")

    @Slot(result=int)
    def getBateriaChannel(self) -> int:
        return self._bateria_config.get("channel", 0) + 1
