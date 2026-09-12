"""Reproducción: Engine de sinte tras un stream sounddevice perezoso.

Toma el `LGPTProject` ya cargado (así la reproducción refleja las ediciones en
memoria y comparte los samples de la canción). El stream solo se crea al pulsar
Play por primera vez, o al disparar un pad sin reproducción (los pads suenan
porque su Voice se renderiza en el callback del stream); si no hay tarjeta de
audio (tests headless) la UI sigue funcionando y el motivo queda en
`audio_error`.
"""

import os
import threading

from host import is_handheld
from sinte_bridge import Engine

SAMPLE_RATE = 44100
# 2048 como lttileplayer.toml (Pi). En la Odin el callback pelea el GIL con
# Kivy y ondemand deja los núcleos bajos: 4096 da ~93 ms de presupuesto.
BLOCKSIZE_DESKTOP = 2048
BLOCKSIZE_HANDHELD = 4096
# Salto del reloj del DAC por encima de esto = xrun real (igual que el sinte).
_DAC_JUMP_S = 0.002


def audio_blocksize() -> int:
    return BLOCKSIZE_HANDHELD if is_handheld() else BLOCKSIZE_DESKTOP


def _boost_audio_thread():
    """Prioridad del hilo de PortAudio. Solo en la Odin (root + handheld)."""
    if not is_handheld():
        return
    try:
        os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(20))
    except (OSError, PermissionError, AttributeError):
        try:
            os.nice(-5)
        except OSError:
            pass


class Player:
    def __init__(self, project, wavs_dir=None):
        # wavs_dir: banco GLOBAL de WAVs de los pads (wavs_dir/pads.json,
        # solo lo usa el mixer). robotracker2 no lo usa: los pads son por
        # canción (robotraca.json "pads" contra la biblioteca pads/,
        # aplicado por MidiControl.set_song) y los botones sampleN suenan
        # lo que la canción tenga asignado.
        self.engine = Engine(project, wavs_dir=wavs_dir)
        self.engine.play_log.set_source("robotracker2")
        self.engine.play_log.set_blocksize(audio_blocksize())
        self._stream = None
        self._started = False
        self.audio_error = None
        self._stream_lock = threading.Lock()
        self._expected_dac = None
        self._prio_done = False

    def _ensure_stream(self):
        # Se llama desde el hilo de la UI (play) y desde el hilo del
        # callback MIDI (disparo de un pad sin reproducción): lock.
        with self._stream_lock:
            if self._stream is not None:
                return True
            try:
                import sounddevice as sd
                bs = audio_blocksize()
                self.engine.play_log.set_blocksize(bs)
                kwargs = dict(
                    samplerate=SAMPLE_RATE, channels=2, dtype="float32",
                    blocksize=bs, callback=self._audio_callback)
                if is_handheld():
                    kwargs["latency"] = "high"
                try:
                    self._stream = sd.OutputStream(**kwargs)
                except Exception:
                    kwargs.pop("latency", None)
                    self._stream = sd.OutputStream(**kwargs)
                self._stream.start()
                return True
            except Exception as exc:      # sin dispositivo de audio, etc.
                self.audio_error = str(exc)
                return False

    def _audio_callback(self, outdata, frames, time_info, status):
        if not self._prio_done:
            self._prio_done = True
            _boost_audio_thread()
        log = self.engine.play_log
        if status:
            log.note_xrun(str(status))
        dac = getattr(time_info, "outputBufferDacTime", None)
        if dac is not None:
            expected = self._expected_dac
            if expected is not None:
                drift = dac - expected
                if drift > _DAC_JUMP_S:
                    # Igual que el sinte: adelanta el secuenciador para que
                    # el compás no quede desplazado tras el silencio del
                    # driver. El engine anota el salto en play_stats.
                    self.engine.catch_up(drift)
            self._expected_dac = dac + frames / SAMPLE_RATE
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

    def play_loop(self, kind, track, idx, from_step=0):
        """Reproduce solo una chain o phrase (`kind` = "chain" | "phrase")
        del canal `track` en bucle, ignorando el resto de la canción.
        `from_step` es el step de la chain desde el que arranca (el cursor);
        al terminar vuelve al 0. En phrase se ignora."""
        if not self._ensure_stream():
            return False
        eng = self.engine
        eng.loop_scope = (kind, track, idx)
        eng.start(from_step=from_step)
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
            self.engine.play_log.finish("close")
            self.engine.panic()
            self._stream.stop()
            self._stream.close()
            self._stream = None
