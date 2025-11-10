#!/usr/bin/env python3
"""Cliente JACK simple que añade delay de audio usando un buffer circular."""

import sys
import os
import time
import collections
import jack
import numpy as np

def main():
    # Log inicial inmediato
    print(f"[DELAY_BUFFER] Iniciando... PID={os.getpid()}", flush=True)
    print(f"[DELAY_BUFFER] Args: {sys.argv}", flush=True)
    print(f"[DELAY_BUFFER] Python: {sys.executable}", flush=True)
    
    if len(sys.argv) < 2:
        print(f"Uso: {sys.argv[0]} <delay_en_segundos>")
        sys.exit(1)
    
    delay_seconds = float(sys.argv[1])
    client_name = sys.argv[2] if len(sys.argv) > 2 else "delay_buffer"
    
    print(f"[DELAY_BUFFER] Delay: {delay_seconds}s, Client: {client_name}", flush=True)
    print(f"[DELAY_BUFFER] Intentando conectar a JACK (no_start_server=True)...", flush=True)
    
    # Conectarse al servidor existente sin iniciar uno nuevo
    # La opción JackNoStartServer evita que se inicie un servidor automáticamente
    try:
        client = jack.Client(client_name, no_start_server=True)
        print(f"[DELAY_BUFFER] ✓ Conectado a JACK exitosamente", flush=True)
    except jack.JackError as e:
        print(f"[DELAY_BUFFER] ERROR: No se puede conectar al servidor JACK: {e}", file=sys.stderr, flush=True)
        print(f"[DELAY_BUFFER] Asegúrate de que jackd esté corriendo.", file=sys.stderr, flush=True)
        sys.exit(1)
    except Exception as e:
        print(f"[DELAY_BUFFER] ERROR INESPERADO: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
    
    samplerate = client.samplerate
    delay_samples = int(delay_seconds * samplerate)
    
    print(f"[DELAY_BUFFER] Samplerate: {samplerate}Hz, Delay samples: {delay_samples}", flush=True)
    print(f"[DELAY_BUFFER] Registrando puertos...", flush=True)
    
    # Crear puertos de entrada y salida estéreo
    try:
        input_left = client.inports.register("input_L")
        input_right = client.inports.register("input_R")
        output_left = client.outports.register("output_L")
        output_right = client.outports.register("output_R")
        print(f"[DELAY_BUFFER] ✓ Puertos registrados: input_L/R, output_L/R", flush=True)
    except Exception as e:
        print(f"[DELAY_BUFFER] ERROR registrando puertos: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
    
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
        print(f"[DELAY_BUFFER] JACK shutdown: {reason}", flush=True)
    
    print(f"[DELAY_BUFFER] Activando cliente JACK...", flush=True)
    
    with client:
        print(f"[DELAY_BUFFER] ✓ Cliente JACK activo. Puertos: {client_name}:input_L/R, {client_name}:output_L/R", flush=True)
        print(f"[DELAY_BUFFER] Listo. Esperando señal...", flush=True)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("[DELAY_BUFFER] Deteniendo...", flush=True)

if __name__ == "__main__":
    main()
