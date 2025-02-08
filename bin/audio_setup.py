import sounddevice as sd
import numpy as np
from collections import deque
import time

# Configuración de audio
SAMPLE_RATE = 44100
CHANNELS = 1
DTYPE = np.float32
BUFFER_DURATION = 1.0  # 1 segundo de retardo
BUFFER_SIZE = int(SAMPLE_RATE * BUFFER_DURATION)

# Buffer FIFO para almacenar 1 segundo de audio
audio_buffer = deque(maxlen=BUFFER_SIZE)

# Callback de entrada
def input_callback(indata, frames, time, status):
    audio_buffer.extend(indata[:, 0])  # Asume mono

# Callback de salida
def output_callback(outdata, frames, time, status):
    if len(audio_buffer) >= frames:
        # Tomar los frames más antiguos
        outdata[:] = np.array([audio_buffer.popleft() for _ in range(frames)]).reshape(-1, 1)
    else:
        outdata.fill(0)

# Configurar dispositivos
def setup_audio():
    print("Iniciando streams de audio...")
    return sd.Streams(
        input_device='hw:Loopback,1',
        output_device='IQaudIODAC',
        samplerate=SAMPLE_RATE,
        blocksize=1024,
        dtype=DTYPE,
        channels=CHANNELS,
        callback=input_callback,
        output_callback=output_callback
    )

# Manejo de señales
def signal_handler(sig, frame):
    print("\nDeteniendo streams...")
    streams.stop()
    streams.close()
    exit(0)

if __name__ == "__main__":
    streams = setup_audio()
    
    with streams:
        print("Sistema de retardo activo (1 segundo exacto)")
        print("Presiona Ctrl+C para detener")        
        while True:
            time.sleep(1)