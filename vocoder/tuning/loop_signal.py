#!/home/patch/venv/bin/python3
"""Señal de prueba para ajustar el vocoder sin depender del sinte ni del micro.

Sustituye el micro (modulador) por un WAV en bucle, y dispara acordes MIDI
en progresión al carrier (Noize Mak3r) por `Carla:events-in`. Las transiciones
son legato: el note-on del acorde nuevo llega antes del note-off del anterior,
así siempre hay alguna nota sonando.

Uso:
  loop_signal.py [--wav RUTA] [--progression let_it_be] [--bpm 90] [--vel 90]
  loop_signal.py --list-progressions
  loop_signal.py --notes 60,63,67   # notas sueltas custom (legato)

Para: Ctrl+C, o SIGTERM (kill / stop-tuning.sh).
"""

from __future__ import annotations

import argparse
import queue
import signal
import threading
import time

import jack
import numpy as np
import soundfile as sf

CLIENT_NAME = "vocoder-tune-loop"
CARLA_AUDIO_IN = ("Carla:audio-in1", "Carla:audio-in2")
CARLA_MIDI_IN = "Carla:events-in"
MIC_SOURCE = "system:capture_1"
CH = 0  # canal MIDI

DEFAULT_WAV = "/home/patch/pivocoder/mic_test.wav"
DEFAULT_BPM = 60.0
DEFAULT_VEL = 90

# Progresiones: lista de acordes (listas de notas MIDI), beats por acorde.
PROGRESSIONS: dict[str, dict] = {
    "let_it_be": {
        "desc": "Let It Be — The Beatles  (C – G – Am – F)",
        "beats": 4,
        "chords": [
            [60, 64, 67],        # C maj  (C4 E4 G4)
            [55, 59, 62, 67],    # G maj  (G3 B3 D4 G4)
            [57, 60, 64],        # A min  (A3 C4 E4)
            [53, 57, 60, 65],    # F maj  (F3 A3 C4 F4)
        ],
    },
    "andaluza": {
        "desc": "Cadencia andaluza  (Am – G – F – E)",
        "beats": 4,
        "chords": [
            [57, 60, 64],        # Am  (A3 C4 E4)
            [55, 59, 62],        # G   (G3 B3 D4)
            [53, 57, 60],        # F   (F3 A3 C4)
            [52, 56, 59],        # E   (E3 G#3 B3)
        ],
    },
    "fifties": {
        "desc": "Años 50  (C – Am – F – G)",
        "beats": 4,
        "chords": [
            [60, 64, 67],        # C
            [57, 60, 64],        # Am
            [53, 57, 60],        # F
            [55, 59, 62],        # G
        ],
    },
    "jazz_251": {
        "desc": "Jazz ii–V–I  (Dm7 – G7 – Cmaj7)",
        "beats": 2,
        "chords": [
            [62, 65, 69, 72],    # Dm7  (D4 F4 A4 C5)
            [55, 59, 62, 65],    # G7   (G3 B3 D4 F4)
            [60, 64, 67, 71],    # Cmaj7 (C4 E4 G4 B4)
            [60, 64, 67, 71],    # Cmaj7 sostenido
        ],
    },
    "creep": {
        "desc": "Creep — Radiohead  (G – B – C – Cm)",
        "beats": 4,
        "chords": [
            [55, 59, 62],        # G   (G3 B3 D4)
            [59, 63, 66],        # B   (B3 D#4 F#4)
            [60, 64, 67],        # C   (C4 E4 G4)
            [60, 63, 67],        # Cm  (C4 Eb4 G4)
        ],
    },
    "escala": {
        "desc": "Escala Do mayor ida y vuelta — nota individual 2s c/u (BPM=60)",
        "beats": 2,
        "chords": [
            [48], [50], [52], [53], [55], [57], [59], [60],  # C3→C4
            [59], [57], [55], [53], [52], [50],               # B3→D3
        ],
    },
}


def load_wav_mono(path: str, sr: int) -> np.ndarray:
    data, file_sr = sf.read(path, dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if file_sr != sr:
        n_out = int(round(len(mono) * sr / file_sr))
        x_old = np.linspace(0.0, 1.0, num=len(mono), endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
        mono = np.interp(x_new, x_old, mono).astype(np.float32)
    return mono


class LoopSignal:
    def __init__(self, wav_path: str, chords: list[list[int]],
                 bpm: float, velocity: int, beats: int) -> None:
        self.client = jack.Client(CLIENT_NAME, no_start_server=True)
        self.audio_out = self.client.outports.register("loop_out")
        self.midi_out = self.client.midi_outports.register("pattern")
        self._pending: queue.SimpleQueue = queue.SimpleQueue()
        self._pos = 0
        self.wav = load_wav_mono(wav_path, self.client.samplerate)
        self.chords = chords
        self.bpm = bpm
        self.velocity = velocity
        self.beats = beats
        self.client.set_process_callback(self._process)

    def _process(self, frames: int) -> None:
        buf = self.audio_out.get_array()
        n = len(self.wav)
        end = self._pos + frames
        if end <= n:
            buf[:] = self.wav[self._pos:end]
        else:
            first = n - self._pos
            buf[:first] = self.wav[self._pos:]
            rest = frames - first
            reps, tail = divmod(rest, n)
            off = first
            for _ in range(reps):
                buf[off:off + n] = self.wav
                off += n
            if tail:
                buf[off:off + tail] = self.wav[:tail]
        self._pos = end % n
        self.midi_out.clear_buffer()
        while True:
            try:
                offset, event = self._pending.get_nowait()
            except queue.Empty:
                break
            try:
                self.midi_out.write_midi_event(min(offset, frames - 1), event)
            except jack.JackError:
                pass

    def _sequencer_loop(self, stop: threading.Event) -> None:
        beat_s = 60.0 / self.bpm
        chord_dur = beat_s * self.beats
        prev: list[int] = []
        i = 0
        while not stop.is_set():
            chord = self.chords[i % len(self.chords)]
            # note-off primero (evita polyphony cuando los acordes son notas sueltas)
            for note in prev:
                if note not in chord:
                    self._pending.put((0, bytes((0x80 | CH, note, 0))))
            # note-on a continuación
            for note in chord:
                self._pending.put((1, bytes((0x90 | CH, note, self.velocity))))
            prev = chord
            stop.wait(chord_dur)
            i += 1
        for note in prev:
            self._pending.put((0, bytes((0x80 | CH, note, 0))))

    def _connect(self) -> None:
        deadline = time.monotonic() + 60
        while "Carla:audio-in1" not in [p.name for p in self.client.get_ports()]:
            if time.monotonic() > deadline:
                raise RuntimeError("Carla:audio-in1 no apareció tras 60s — "
                                   "¿está Carla corriendo?")
            print("[loop] esperando a Carla...", flush=True)
            time.sleep(2)
        for dst in CARLA_AUDIO_IN:
            try:
                self.client.disconnect(MIC_SOURCE, dst)
            except jack.JackError:
                pass
            self.client.connect(self.audio_out, dst)
        self.client.connect(self.midi_out, CARLA_MIDI_IN)

    def _restore_mic(self) -> None:
        for dst in CARLA_AUDIO_IN:
            try:
                self.client.disconnect(self.audio_out, dst)
            except jack.JackError:
                pass
            try:
                self.client.connect(MIC_SOURCE, dst)
            except jack.JackError:
                pass

    def run(self) -> None:
        self.client.activate()
        self._connect()
        print(f"[loop] wav={len(self.wav)/self.client.samplerate:.1f}s  "
              f"bpm={self.bpm}  beats/acorde={self.beats}  "
              f"acordes={len(self.chords)}  -> Carla conectado",
              flush=True)
        stop = threading.Event()
        threading.Thread(target=self._sequencer_loop, args=(stop,),
                         daemon=True).start()
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        stop.wait()
        print("[loop] cerrando: desconecta y devuelve el micro...", flush=True)
        self._restore_mic()
        self.client.deactivate()
        self.client.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--wav", default=DEFAULT_WAV)
    p.add_argument("--bpm", type=float, default=DEFAULT_BPM)
    p.add_argument("--vel", type=int, default=DEFAULT_VEL)
    p.add_argument("--beats", type=int, default=None,
                   help="Beats por acorde (sobreescribe el de la progresión)")
    p.add_argument("--progression", choices=PROGRESSIONS, default="escala",
                   help="Progresión de acordes predefinida")
    p.add_argument("--notes", default=None,
                   help="Notas custom separadas por coma (ej: 60,63,67); "
                        "cada nota es un acorde de 1 nota, en ciclo legato")
    p.add_argument("--list-progressions", action="store_true",
                   help="Lista las progresiones disponibles y sale")
    args = p.parse_args()

    if args.list_progressions:
        for key, val in PROGRESSIONS.items():
            print(f"  {key:<12} {val['desc']}")
        return

    if args.notes is not None:
        chords = [[int(n)] for n in args.notes.split(",") if n.strip()]
        beats = args.beats or 1
    else:
        prog = PROGRESSIONS[args.progression]
        chords = prog["chords"]
        beats = args.beats or prog["beats"]
        print(f"[loop] {prog['desc']}", flush=True)

    LoopSignal(args.wav, chords, args.bpm, args.vel, beats).run()


if __name__ == "__main__":
    main()
