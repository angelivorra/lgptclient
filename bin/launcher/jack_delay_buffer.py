#!/usr/bin/env python3
"""Cliente JACK simple que añade delay de audio usando un buffer circular."""

import sys
import time
import collections
import jack
import numpy as np

def main():
    if len(sys.argv) < 2:
        print(f"Uso: {sys.argv[0]} <delay_en_segundos>")
        sys.exit(1)
    
    delay_seconds = float(sys.argv[1])
    client_name = sys.argv[2] if len(sys.argv) > 2 else "delay_buffer"
    
    client = jack.Client(client_name)
    samplerate = client.samplerate
    delay_samples = int(delay_seconds * samplerate)
    
    print(f"Iniciando buffer de delay: {delay_seconds}s ({delay_samples} samples @ {samplerate}Hz)")
    
    # Crear puertos de entrada y salida estéreo
    input_left = client.inports.register("input_L")
    input_right = client.inports.register("input_R")
    output_left = client.outports.register("output_L")
    output_right = client.outports.register("output_R")
    
    # Buffers circulares para cada canal
    buffer_left = collections.deque([0.0] * delay_samples, maxlen=delay_samples)
    buffer_right = collections.deque([0.0] * delay_samples, maxlen=delay_samples)
    
    @client.set_process_callback
    def process(frames):
        # Leer entrada
        in_l = input_left.get_array()
        in_r = input_right.get_array()
        
        # Obtener buffers de salida
        out_l = output_left.get_array()
        out_r = output_right.get_array()
        
        # Procesar cada frame
        for i in range(frames):
            # Añadir entrada al buffer
            buffer_left.append(float(in_l[i]))
            buffer_right.append(float(in_r[i]))
            
            # Escribir salida (el valor más antiguo del buffer)
            out_l[i] = buffer_left[0]
            out_r[i] = buffer_right[0]
    
    @client.set_shutdown_callback
    def shutdown(status, reason):
        print(f"JACK shutdown: {reason}")
    
    with client:
        print(f"Cliente JACK activo. Puertos: {client_name}:input_L/R, {client_name}:output_L/R")
        print("Presiona Ctrl+C para salir...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nDeteniendo...")

if __name__ == "__main__":
    main()
