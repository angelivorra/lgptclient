"""Entrada MIDI de notas para pintar en vivo en la phrase y preview.

Envuelve `mido.open_input` en un hilo daemon propio: los `note_on` /
`note_off` llegan a una cola y la app los drena desde su hilo principal
(Kivy Clock), así no hay acceso cruzado a la UI ni bloqueos, y no se
depende del hilo interno que cada backend de mido pueda (o no) arrancar
al usar callback.
"""

import queue
import threading

POLL_SLEEP = 0.005      # 5 ms entre lecturas del puerto


def midi_port_base(name: str) -> str:
    """Quita el `client:port` ALSA final (`16:0`), que cambia de puerto USB."""
    if not name:
        return name
    head, sep, tail = name.rpartition(" ")
    if not sep or ":" not in tail:
        return name
    a, _, b = tail.partition(":")
    if a.isdigit() and b.isdigit():
        return head
    return name


def resolve_midi_port(names: list[str], wanted: str | None) -> str | None:
    """Elige un puerto por nombre parcial, ignorando el id de cliente ALSA.

    `wanted` puede ser el nombre completo guardado (`LPK25:LPK25 MIDI 1 16:0`)
    o el de otro arranque/puerto USB (`… 24:0`): ambos resuelven al dispositivo
    que esté enchufado ahora. None/vacío no elige nada (sin auto).
    """
    if not names or not wanted:
        return None
    wanted_l = wanted.lower()
    base_l = midi_port_base(wanted).lower()
    for n in names:
        nl = n.lower()
        if wanted_l in nl or base_l in nl:
            return n
        if midi_port_base(n).lower() == base_l:
            return n
    return None


def midi_input_names() -> list[str]:
    """Puertos MIDI de entrada disponibles (vacío si mido/rtmidi falla)."""
    try:
        import mido
        return mido.get_input_names()
    except Exception:                       # noqa: BLE001
        return []


def midi_note_event(msg):
    """Convierte un mensaje mido en `("on", nota, vel)` / `("off", nota, 0)`.

    `note_on` con velocity 0 es note off (running status). El resto de
    tipos (CC, program change, …) se ignoran.
    """
    typ = getattr(msg, "type", None)
    if typ == "note_on":
        note = int(msg.note) & 0x7F
        vel = int(msg.velocity) & 0x7F
        if vel > 0:
            return ("on", note, vel)
        return ("off", note, 0)
    if typ == "note_off":
        return ("off", int(msg.note) & 0x7F, 0)
    return None


class MidiNotesInput:
    """Cola de notas MIDI desde la interfaz configurada.

    `open_port` arranca un hilo daemon que lee el puerto sin bloquear
    (`iter_pending`) y encola `("on", nota, vel)` / `("off", nota, 0)`.
    `poll` drena la cola desde el hilo principal. `close` corta, para el
    hilo y limpia lo pendiente.
    """

    def __init__(self):
        self._port = None
        self._thread = None
        self._stop = threading.Event()
        self._queue = queue.Queue()
        self.error = None

    @property
    def active(self) -> bool:
        t = self._thread
        return self._port is not None and t is not None and t.is_alive()

    def open_port(self, port_name: str) -> bool:
        """Abre la interfaz `port_name` (nombre parcial / id ALSA distinto
        vale) y arranca el hilo de lectura."""
        self.close()
        try:
            import mido
            chosen = resolve_midi_port(mido.get_input_names(), port_name)
            if chosen is None:
                self.error = "no disponible"
                return False
            port = mido.open_input(chosen)
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
                    ev = midi_note_event(msg)
                    if ev is not None:
                        self._queue.put(ev)
            except Exception:               # noqa: BLE001
                return                      # puerto roto/cerrado
            self._stop.wait(POLL_SLEEP)

    def poll(self) -> list[tuple[str, int, int]]:
        """Drena la cola: eventos `("on", nota, vel)` / `("off", nota, 0)`."""
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
