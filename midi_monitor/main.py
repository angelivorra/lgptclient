#!/usr/bin/env python3
"""
MIDI Monitor - Punto de entrada de la aplicación
"""

from app import MidiMonitorApp


def main():
    app = MidiMonitorApp()
    app.run()


if __name__ == "__main__":
    main()
