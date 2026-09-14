"""Grabación de la mezcla a WAV sin bloquear el callback de audio.

El callback encola bloques; un hilo escritor los vuelca a disco. close()
es idempotente y rechaza writes posteriores (robotracker deja el stream
abierto entre play y stop).
"""

from __future__ import annotations

import queue
import threading


class WavRecorder:
    """Graba la salida de audio a un WAV sin bloquear el callback."""

    def __init__(self, path: str, samplerate: int):
        import soundfile as sf
        self._sf = sf.SoundFile(path, "w", samplerate=samplerate,
                                channels=2, subtype="PCM_16")
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._closed = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while True:
            block = self._queue.get()
            if block is None:
                break
            self._sf.write(block)
        self._sf.close()

    def write(self, block):
        with self._lock:
            if self._closed:
                return
            self._queue.put(block.copy())

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._queue.put(None)
        self._thread.join()
