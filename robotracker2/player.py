"""Reproducción: Engine de sinte tras un stream sounddevice perezoso.

Toma el `LGPTProject` ya cargado (así la reproducción refleja las ediciones en
memoria y comparte los samples de la canción). El stream solo se crea al pulsar
Play por primera vez; si no hay tarjeta de audio (tests headless) la UI sigue
funcionando y el motivo queda en `audio_error`.
"""

from sinte_bridge import Engine

SAMPLE_RATE = 44100


class Player:
    def __init__(self, project):
        self.engine = Engine(project)
        self._stream = None
        self._started = False
        self.audio_error = None

    def _ensure_stream(self):
        if self._stream is not None:
            return True
        try:
            import sounddevice as sd
            self._stream = sd.OutputStream(
                samplerate=SAMPLE_RATE, channels=2, dtype="float32",
                callback=self._audio_callback)
            self._stream.start()
            return True
        except Exception as exc:          # sin dispositivo de audio, etc.
            self.audio_error = str(exc)
            return False

    def _audio_callback(self, outdata, frames, _time_info, _status):
        outdata[:] = self.engine.render(frames)

    def play_from(self, from_row=0):
        """Arranca (o reanuda) la reproducción desde la fila `from_row`."""
        if not self._ensure_stream():
            return False
        eng = self.engine
        eng.loop_scope = None          # play de canción completa
        if not self._started or eng.finished:
            eng.start(from_row)
            self._started = True
        elif not eng.playing:
            eng.push_event("play")
        return True

    def play_loop(self, kind, track, idx):
        """Reproduce solo una chain o phrase (`kind` = "chain" | "phrase")
        del canal `track` en bucle, ignorando el resto de la canción."""
        if not self._ensure_stream():
            return False
        eng = self.engine
        eng.loop_scope = (kind, track, idx)
        eng.start()
        self._started = True
        return True

    def stop(self):
        self.engine.loop_scope = None
        self.engine.push_event("stop")
        self._started = False


    @property
    def playing(self):
        return bool(self.engine.playing)

    def close(self):
        if self._stream is not None:
            self.engine.panic()
            self._stream.stop()
            self._stream.close()
            self._stream = None
