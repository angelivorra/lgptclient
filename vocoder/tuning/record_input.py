#!/usr/bin/env python3
"""Graba lo que entra a Carla (system:capture_1, el mismo micro que usa el
vocoder en producción) a un WAV, para usarlo luego como señal de prueba más
real que un WAV sintético (ver loop_signal.py --wav).

No para producción: es solo otro cliente JACK escuchando el mismo puerto,
así que puedes grabar mientras el sinte suena de verdad y alguien habla al
micro (lo más realista posible).

Uso: record_input.py [--seconds 20] [--out RUTA]
Para antes de tiempo: Ctrl+C (guarda lo grabado hasta ese momento).
"""

from __future__ import annotations

import argparse
import signal
import threading
import time
from pathlib import Path

import jack
import numpy as np
import soundfile as sf

CLIENT_NAME = "vocoder-tune-record"
SOURCE = "system:capture_1"
DEFAULT_SECONDS = 20.0
DEFAULT_DIR = Path(__file__).resolve().parent / "recordings"


class Recorder:
    def __init__(self, seconds: float, out_path: Path) -> None:
        self.client = jack.Client(CLIENT_NAME, no_start_server=True)
        self.inport = self.client.inports.register("in")
        self.seconds = seconds
        self.out_path = out_path
        self._chunks: list[np.ndarray] = []
        self._frames = 0
        self.client.set_process_callback(self._process)

    def _process(self, frames: int) -> None:
        buf = self.inport.get_array()
        self._chunks.append(buf.copy())
        self._frames += frames

    def run(self) -> None:
        self.client.activate()
        try:
            self.client.connect(SOURCE, self.inport)
        except jack.JackError as exc:
            print(f"No se pudo conectar a {SOURCE}: {exc}")
            self.client.deactivate()
            self.client.close()
            return
        stop = threading.Event()
        signal.signal(signal.SIGINT, lambda *_a: stop.set())
        signal.signal(signal.SIGTERM, lambda *_a: stop.set())
        sr = self.client.samplerate
        target_frames = int(self.seconds * sr)
        print(f"[record] grabando de {SOURCE} hasta {self.seconds:.0f}s "
             "(Ctrl+C para cortar antes)...", flush=True)
        while self._frames < target_frames and not stop.is_set():
            stop.wait(0.2)
        self.client.deactivate()
        self.client.close()
        data = (np.concatenate(self._chunks) if self._chunks
               else np.zeros(0, dtype=np.float32))
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(self.out_path), data, sr)
        print(f"[record] {len(data) / sr:.1f}s guardados en {self.out_path}",
             flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seconds", type=float, default=DEFAULT_SECONDS)
    p.add_argument("--out", default=None,
                   help="ruta del WAV de salida (por defecto, "
                        "recordings/<timestamp>.wav)")
    args = p.parse_args()
    out_path = Path(args.out) if args.out else DEFAULT_DIR / f"{int(time.time())}.wav"
    Recorder(args.seconds, out_path).run()


if __name__ == "__main__":
    main()
