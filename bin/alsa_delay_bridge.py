#!/usr/bin/env python3
"""
ALSA delay bridge: toma el audio que LGPT envía al Loopback y lo reproduce en la
salida física aplicando un retardo EXACTO de 1.000 s (a 44.1 kHz) antes de
entregarlo.

Estrategia:
- LGPT se configura con ALSA y AUDIODEVICE hw:Loopback,0 (playback).
- Capturamos desde el lado de captura correspondiente del Loopback
  (por defecto hw:Loopback,1,0 recoge lo que se reproduce en hw:Loopback,0).
- Mantenemos una cola (buffer) de exactamente 1 segundo de audio (44100 frames)
  en memoria antes de empezar a volcar datos a la salida real (hw:IQaudIODAC,0).
- Tras “llenar” la cola, cada chunk capturado se encola y simultáneamente se
  desencola el bloque más antiguo para reproducirlo => retardo estable de 1 s.

Precisión:
- El retardo es sample-exacto salvo la granularidad de bloque (period_size).
- Variación máxima: ± period_size/44100 s. Con period_size=512 => ±11.6 ms.
  Puedes bajar period_size (256 / 128) para reducir jitter a cambio de más
  llamadas al sistema y posible XRUN.

Requisitos:
  pip install pyalsaaudio

Uso:
  1. Ajusta config.xml de LGPT a ALSA + hw:Loopback,0.
  2. Ejecuta este script (ideal en otra terminal):
       python3 bin/alsa_delay_bridge.py
  3. Arranca LGPT (sudo si lo necesitas) y deberías oír audio retardado 1 s.

Parada limpia: Ctrl+C.
"""
import alsaaudio
import time
import signal
import sys
from collections import deque

# Parámetros configurables
CAPTURE_DEVICE = 'hw:Loopback,1,0'   # Captura lo que se reproduce en hw:Loopback,0
PLAYBACK_DEVICE = 'hw:IQaudIODAC,0'  # Salida física
RATE = 44100
CHANNELS = 2
FORMAT = alsaaudio.PCM_FORMAT_S16_LE
PERIOD_SIZE_FRAMES = 512            # Tamaño de bloque (frames)
DELAY_SECONDS = 1.0                 # Retardo objetivo

# Cálculos derivados
BYTES_PER_FRAME = 2 * CHANNELS      # 16 bits = 2 bytes por canal
TARGET_DELAY_BYTES = int(RATE * DELAY_SECONDS * BYTES_PER_FRAME)
SILENCE_CHUNK = b'\x00' * (PERIOD_SIZE_FRAMES * BYTES_PER_FRAME)

running = True


def handle_signal(sig, frame):
    global running
    running = False


def open_capture():
    pcm = alsaaudio.PCM(type=alsaaudio.PCM_CAPTURE, mode=alsaaudio.PCM_NORMAL, device=CAPTURE_DEVICE)
    pcm.setchannels(CHANNELS)
    pcm.setrate(RATE)
    pcm.setformat(FORMAT)
    pcm.setperiodsize(PERIOD_SIZE_FRAMES)
    return pcm


def open_playback():
    pcm = alsaaudio.PCM(type=alsaaudio.PCM_PLAYBACK, mode=alsaaudio.PCM_NORMAL, device=PLAYBACK_DEVICE)
    pcm.setchannels(CHANNELS)
    pcm.setrate(RATE)
    pcm.setformat(FORMAT)
    pcm.setperiodsize(PERIOD_SIZE_FRAMES)
    return pcm


def main():
    print(f"Iniciando puente ALSA con retardo {DELAY_SECONDS:.3f}s | period={PERIOD_SIZE_FRAMES} frames")
    print(f"Captura: {CAPTURE_DEVICE} -> Reproducción: {PLAYBACK_DEVICE}")
    capture = open_capture()
    playback = open_playback()

    # Cola de bytes (primer en entrar, primero en salir)
    queue = deque()
    queued_bytes = 0

    last_report = time.time()
    total_frames_in = 0
    total_frames_out = 0

    # Prefill / ejecución
    while running:
        length, data = capture.read()  # length en frames, data en bytes
        if length <= 0:
            # Pequeña espera para no saturar CPU
            time.sleep(0.001)
            continue

        total_frames_in += length
        queue.append(data)
        queued_bytes += len(data)

        if queued_bytes < TARGET_DELAY_BYTES:
            # Aún llenando retardo: reproducimos silencio del mismo tamaño que el chunk
            playback.write(SILENCE_CHUNK[:len(data)])
            total_frames_out += length
        else:
            # Emitir chunk más antiguo (retardo completo conseguido)
            oldest = queue.popleft()
            queued_bytes -= len(oldest)
            playback.write(oldest)
            total_frames_out += len(oldest) // BYTES_PER_FRAME

        # Log periódico simple (cada ~5 s)
        now = time.time()
        if now - last_report > 5:
            delay_ms = queued_bytes / BYTES_PER_FRAME / RATE * 1000
            print(f"Estado: delay_buffer ~{delay_ms:.1f} ms | in_frames={total_frames_in} out_frames={total_frames_out}")
            last_report = now

    print("Deteniendo...")


if __name__ == '__main__':
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
