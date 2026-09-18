#!/usr/bin/env python3
"""Señal de prueba para ajustar el vocoder sin depender del sinte ni del micro.

Sustituye el micro (modulador) por un WAV en bucle, y dispara un patrón MIDI
rítmico al carrier (Noize Mak3r) por `Carla:events-in`, igual que hace
`carla_runner.py` con el ACRD del sinte. Pensado para sesiones de ajuste con
la GUI de Carla (ver start-tuning.sh/stop-tuning.sh de este mismo
directorio): deja el vocoder sonando solo, en bucle y en compás, mientras se
añaden/quitan plugins o se mueven knobs.

Uso:
  loop_signal.py [--wav RUTA] [--notes 60,63,67] [--bpm 100] [--vel 100]

Para: Ctrl+C, o SIGTERM (systemctl/kill) — desconecta limpio y devuelve el
micro a Carla:audio-in1/2.
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
CHORD_MIDI_CHANNEL = 0

DEFAULT_WAV = "/home/patch/pivocoder/mic_test.wav"
DEFAULT_NOTES = [60, 63, 67]     # acorde por defecto (Cm), cambia con --notes
DEFAULT_BPM = 100.0
DEFAULT_VEL = 100
NOTE_HOLD_FRAC = 0.6             # la nota suena el 60% del pulso, luego note-off


def load_wav_mono(path: str, sr: int) -> np.ndarray:
    data, file_sr = sf.read(path, dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if file_sr != sr:
        # Resample lineal: de sobra para una señal de prueba, sin tirar de
        # scipy/librosa (no están en el venv de la Pi).
        n_out = int(round(len(mono) * sr / file_sr))
        x_old = np.linspace(0.0, 1.0, num=len(mono), endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
        mono = np.interp(x_new, x_old, mono).astype(np.float32)
    return mono


class LoopSignal:
    def __init__(self, wav_path: str, notes: list[int], bpm: float,
                velocity: int) -> None:
        self.client = jack.Client(CLIENT_NAME, no_start_server=True)
        self.audio_out = self.client.outports.register("loop_out")
        self.midi_out = self.client.midi_outports.register("pattern")
        self._pending: queue.SimpleQueue = queue.SimpleQueue()
        self._pos = 0
        self.wav = load_wav_mono(wav_path, self.client.samplerate)
        self.notes = notes
        self.bpm = bpm
        self.velocity = velocity
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
        i = 0
        while not stop.is_set():
            note = self.notes[i % len(self.notes)]
            self._pending.put((0, bytes((0x90 | CHORD_MIDI_CHANNEL, note,
                                         self.velocity))))
            stop.wait(beat_s * NOTE_HOLD_FRAC)
            self._pending.put((0, bytes((0x80 | CHORD_MIDI_CHANNEL, note, 0))))
            stop.wait(beat_s * (1 - NOTE_HOLD_FRAC))
            i += 1

    def _connect(self) -> None:
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
        print(f"[loop] wav={len(self.wav) / self.client.samplerate:.1f}s  "
             f"notas={self.notes}  bpm={self.bpm}  -> Carla conectado (mic "
             "desconectado)", flush=True)
        stop = threading.Event()
        threading.Thread(target=self._sequencer_loop, args=(stop,),
                         daemon=True).start()
        signal.signal(signal.SIGTERM, lambda *_a: stop.set())
        signal.signal(signal.SIGINT, lambda *_a: stop.set())
        stop.wait()
        print("[loop] cerrando: desconecta y devuelve el micro...", flush=True)
        self._restore_mic()
        self.client.deactivate()
        self.client.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wav", default=DEFAULT_WAV)
    p.add_argument("--notes", default=",".join(str(n) for n in DEFAULT_NOTES))
    p.add_argument("--bpm", type=float, default=DEFAULT_BPM)
    p.add_argument("--vel", type=int, default=DEFAULT_VEL)
    args = p.parse_args()
    notes = [int(n) for n in args.notes.split(",") if n.strip()]
    LoopSignal(args.wav, notes, args.bpm, args.vel).run()


if __name__ == "__main__":
    main()
