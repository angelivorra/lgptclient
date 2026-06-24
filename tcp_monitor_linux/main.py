#!/usr/bin/env python3
"""
TCP Monitor — Linux/Kirigami
Punto de entrada: inicializa el engine QML y expone el backend Python.
"""

import sys
import os
import logging

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtCore import QUrl

from app_backend import TcpBackend
from log_model import LogModel

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tcp_monitor.log")


def _setup_logging() -> None:
    fmt = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
    handlers = [
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ]
    logging.basicConfig(level=logging.DEBUG, format=fmt, handlers=handlers)
    logging.getLogger("__main__").info("=== TCP Monitor arrancando ===")


def main():
    _setup_logging()
    app = QGuiApplication(sys.argv)
    app.setOrganizationName("TcpMonitor")
    app.setApplicationName("TCP Monitor")

    engine = QQmlApplicationEngine()

    engine.addImportPath("/usr/lib/x86_64-linux-gnu/qt6/qml")
    pyside6_qml = os.path.join(os.path.dirname(__import__("PySide6").__file__), "Qt", "qml")
    engine.addImportPath(pyside6_qml)

    backend = TcpBackend()
    log_model = LogModel()

    backend.tcpEvent.connect(log_model.addEntry)
    app.aboutToQuit.connect(backend.shutdown)

    ctx = engine.rootContext()
    ctx.setContextProperty("tcpBackend", backend)
    ctx.setContextProperty("logModel", log_model)

    qml_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qml", "main.qml")
    engine.load(QUrl.fromLocalFile(qml_file))

    if not engine.rootObjects():
        sys.exit(-1)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
