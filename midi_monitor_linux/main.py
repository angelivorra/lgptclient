#!/usr/bin/env python3
"""
MIDI Monitor — Linux/Kirigami
Punto de entrada: inicializa el engine QML y expone el backend Python.
"""

import sys
import os

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtCore import QUrl

from app_backend import MidiBackend
from log_model import LogModel


def main():
    app = QGuiApplication(sys.argv)
    app.setOrganizationName("MidiMonitor")
    app.setApplicationName("MIDI Monitor")

    engine = QQmlApplicationEngine()

    # Orden: primero sistema (Kirigami), luego PySide6 (toma prioridad sobre Qt modules).
    # addImportPath() prepende, así que el último añadido queda primero en la búsqueda.
    engine.addImportPath("/usr/lib/x86_64-linux-gnu/qt6/qml")
    pyside6_qml = os.path.join(os.path.dirname(__import__("PySide6").__file__), "Qt", "qml")
    engine.addImportPath(pyside6_qml)

    backend = MidiBackend()
    log_model = LogModel()

    backend.midiEvent.connect(log_model.addEntry)
    # Cierre limpio del hilo MIDI antes de finalizar el intérprete (evita el
    # fallo "PyGILState_Release" al cerrar el programa).
    app.aboutToQuit.connect(backend.shutdown)

    ctx = engine.rootContext()
    ctx.setContextProperty("midiBackend", backend)
    ctx.setContextProperty("logModel", log_model)

    qml_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qml", "main.qml")
    engine.load(QUrl.fromLocalFile(qml_file))

    if not engine.rootObjects():
        sys.exit(-1)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
