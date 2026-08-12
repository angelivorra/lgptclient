"""Reproducción: Engine de sinte detrás de un stream sounddevice perezoso.

El stream solo se crea al pulsar Play por primera vez y cualquier fallo de
audio (máquina sin tarjeta, tests headless) deja la UI funcionando igual;
`audio_error` recoge el motivo para mostrarlo.
"""

from pathlib import Path

from sinte_bridge import Engine

SAMPLE_RATE = 44100


class Player:
    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.engine = Engine(self.project_dir)
        self._stream = None
        self._started = False
        self.audio_error: str | None = None

    # -- stream --------------------------------------------------------------
    def _ensure_stream(self) -> bool:
        if self._stream is not None:
            return True
        try:
            import sounddevice as sd
            self._stream = sd.OutputStream(
                samplerate=SAMPLE_RATE, channels=2, dtype="float32",
                callback=self._audio_callback)
            self._stream.start()
            return True
        except Exception as exc:  # sin dispositivo de audio, etc.
            self.audio_error = str(exc)
            return False

    def _audio_callback(self, outdata, frames, _time_info, _status):
        outdata[:] = self.engine.render(frames)

    # -- transporte ------------------------------------------------------------
    def toggle(self, from_row: int = 0):
        """Play/pausa. La primera vez (o tras stop/fin) arranca la canción
        desde la fila `from_row` de la song; el evento "play" a secas no
        posiciona los canales y sonaría vacío.
        Devuelve False si no hay salida de audio (ver self.audio_error)."""
        if not self._ensure_stream():
            return False
        eng = self.engine
        if not self._started or eng.finished:
            eng.start(from_row)
            self._started = True
        elif eng.playing:
            eng.push_event("pause")
        else:
            eng.push_event("play")
        return True

    def stop(self):
        """Stop: el próximo play arranca de nuevo (desde el cursor en SONG),
        no reanuda donde se quedó."""
        self.engine.push_event("stop")
        self._started = False

    @property
    def playing(self) -> bool:
        return bool(self.engine.playing)

    def close(self):
        if self._stream is not None:
            self.engine.panic()
            self._stream.stop()
            self._stream.close()
            self._stream = None
