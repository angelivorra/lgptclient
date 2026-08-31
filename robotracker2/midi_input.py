"""Entrada MIDI de notas para pintar en vivo en la phrase.

Envuelve `mido.open_input` en un hilo daemon propio: los `note_on` llegan a
una cola y la app los drena desde su hilo principal (Kivy Clock), así no hay
acceso cruzado a la UI ni bloqueos, y no se depende del hilo interno que cada
backend de mido pueda (o no) arrancar al usar callback.
"""

import queue
import threading

POLL_SLEEP = 0.005      # 5 ms entre lecturas del puerto


def midi_input_names() -> list[str]:
    """Puertos MIDI de entrada disponibles (vacío si mido/rtmidi falla)."""
    try:
        import mido
        return mido.get_input_names()
    except Exception:                       # noqa: BLE001
        return []


class MidiNotesInput:
    """Cola de notas MIDI (note_on) desde la interfaz configurada.

    `open_port` arranca un hilo daemon que lee el puerto sin bloquear
    (`iter_pending`) y encola `(nota, velocity)`. `poll` drena la cola desde
    el hilo principal. `close` corta, para el hilo y limpia lo pendiente.
    """

    def __init__(self):
        self._port = None
        self._thread = None
        self._stop = threading.Event()
        self._queue = queue.Queue()
        self.error = None

    @property
    def active(self) -> bool:
        return self._port is not None

    def open_port(self, port_name: str) -> bool:
        """Abre la interfaz `port_name` y arranca el hilo de lectura."""
        self.close()
        try:
            import mido
            port = mido.open_input(port_name)
        except Exception as exc:            # noqa: BLE001
            self.error = str(exc)
            return False
        self._port = port
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.error = None
        return True

    def _run(self):
        port = self._port
        while not self._stop.is_set():
            try:
                for msg in port.iter_pending():
                    if self._stop.is_set():
                        return
                    if msg.type == "note_on" and msg.velocity > 0:
                        self._queue.put((msg.note & 0x7F, msg.velocity & 0x7F))
            except Exception:               # noqa: BLE001
                return                      # puerto roto/cerrado
            self._stop.wait(POLL_SLEEP)

    def poll(self) -> list[tuple[int, int]]:
        """Drena la cola: devuelve las notas pendientes (nota, velocity)."""
        notes = []
        while True:
            try:
                notes.append(self._queue.get_nowait())
            except queue.Empty:
                return notes

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.2)
            self._thread = None
        if self._port is not None:
            try:
                self._port.close()
            except Exception:               # noqa: BLE001
                pass
            self._port = None
        while True:                         # descarta lo que quedara encolado
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
