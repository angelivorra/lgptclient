"""Reproducción: Engine de sinte tras un stream sounddevice perezoso.

Toma el `LGPTProject` ya cargado (así la reproducción refleja las ediciones en
memoria y comparte los samples de la canción). El stream solo se crea al pulsar
Play por primera vez, o al disparar un pad sin reproducción (los pads suenan
porque su Voice se renderiza en el callback del stream); si no hay tarjeta de
audio (tests headless) la UI sigue funcionando y el motivo queda en
`audio_error`.
"""

import threading

from sinte_bridge import Engine

SAMPLE_RATE = 44100


class Player:
    def __init__(self, project, wavs_dir=None):
        # wavs_dir: banco GLOBAL de WAVs de los pads (wavs_dir/pads.json,
        # solo lo usa el mixer). robotracker2 no lo usa: los pads son por
        # canción (robotraca.json "pads" contra la biblioteca pads/,
        # aplicado por MidiControl.set_song) y los botones sampleN suenan
        # lo que la canción tenga asignado.
        self.engine = Engine(project, wavs_dir=wavs_dir)
        self._stream = None
        self._started = False
        self.audio_error = None
        self._stream_lock = threading.Lock()

    def _ensure_stream(self):
        # Se llama desde el hilo de la UI (play) y desde el hilo del
        # callback MIDI (disparo de un pad sin reproducción): lock.
        with self._stream_lock:
            if self._stream is not None:
                return True
            try:
                import sounddevice as sd
                # 2048 como lttileplayer.toml: scream y otros LADSPA pesados
                # con el blocksize por defecto (~512) se pasan de presupuesto.
                self._stream = sd.OutputStream(
                    samplerate=SAMPLE_RATE, channels=2, dtype="float32",
                    blocksize=2048,
                    callback=self._audio_callback)
                self._stream.start()
                return True
            except Exception as exc:      # sin dispositivo de audio, etc.
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
