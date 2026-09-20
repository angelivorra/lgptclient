#!/home/patch/venv/bin/python3
"""Transmite Carla:audio-out1 a stdout como PCM float32 le.

Uso (en la Pi):
  stream_audio.py | aplay -f FLOAT_LE -r 44100 -c 1 -q

tune.sh lo lanza por SSH piped a aplay en el PC para escuchar
la salida del vocoder mientras se ajusta el rack de Carla.
"""
import queue
import signal
import sys
import threading
import time

import jack

SOURCE = "Carla:audio-out1"
CLIENT = "vocoder-audio-stream"

c = jack.Client(CLIENT, no_start_server=True)
port = c.inports.register("in")
q: queue.Queue = queue.Queue(maxsize=200)
stop = threading.Event()


@c.set_process_callback
def _process(frames: int) -> None:
    try:
        q.put_nowait(bytes(port.get_array()))
    except queue.Full:
        pass


def _write() -> None:
    while True:
        data = q.get()
        if data is None:
            break
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()


signal.signal(signal.SIGTERM, lambda *_: stop.set())
signal.signal(signal.SIGINT, lambda *_: stop.set())

writer = threading.Thread(target=_write, daemon=True)
writer.start()

with c:
    deadline = time.monotonic() + 30
    while SOURCE not in [p.name for p in c.get_ports()]:
        if time.monotonic() > deadline:
            sys.stderr.write(f"[audio] {SOURCE} no apareció en 30s\n")
            sys.exit(1)
        time.sleep(1)
    c.connect(SOURCE, port)
    sys.stderr.write(f"[audio] conectado a {SOURCE} ({c.samplerate} Hz)\n")
    sys.stderr.flush()
    stop.wait()

q.put(None)
writer.join(timeout=2)
