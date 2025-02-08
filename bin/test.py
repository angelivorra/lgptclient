import subprocess
import signal
import sys

# Definir los dispositivos de entrada (loopback) y salida (IQaudIODAC)
input_device = "hw:Loopback,1,0"
output_device = "hw:IQaudIODAC,0"

# Comandos con formatos de audio específicos
arecord_cmd = [
    "arecord",
    "-D", input_device,
    "-f", "S16_LE",
    "-c", "2",
    "-r", "44100",
    "-B", "32768"
]

aplay_cmd = [
    "aplay",
    "-D", output_device,
    "-f", "S16_LE",
    "-c", "2",
    "-r", "44100",
    "-B", "32768"
]

# Variables globales para los procesos
arecord_process = None
aplay_process = None

def cleanup(processes):
    """Terminar todos los procesos de manera limpia"""
    for process in processes:
        if process:
            try:
                process.terminate()
                process.wait(timeout=1)
            except:
                process.kill()

def signal_handler(sig, frame):
    """Manejador de señales para terminar limpiamente"""
    print("\nDeteniendo procesos...")
    cleanup([arecord_process, aplay_process])
    sys.exit(0)

try:
    print("Iniciando puente de audio...")
    
    # Registrar el manejador de señales
    signal.signal(signal.SIGINT, signal_handler)
    
    # Crear los procesos y conectar los pipes directamente
    arecord_process = subprocess.Popen(arecord_cmd, stdout=subprocess.PIPE)
    aplay_process = subprocess.Popen(aplay_cmd, stdin=arecord_process.stdout)
    
    # Esperar a que termine el proceso de reproducción
    aplay_process.wait()

except Exception as e:
    print(f"Error: {e}")
    cleanup([arecord_process, aplay_process])
    sys.exit(1)