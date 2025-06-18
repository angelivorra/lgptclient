import subprocess
import signal
import sys
import logging

class AudioBridge:
    def __init__(self, input_device="hw:Loopback,1,0", output_device="hw:IQaudIODAC,0"):
        self.input_device = input_device
        self.output_device = output_device
        self.arecord_process = None
        self.sox_process = None
        self.aplay_process = None
        self.running = False

    def cleanup(self):
        """Clean up all audio processes"""
        self.running = False
        for process in [self.arecord_process, self.sox_process, self.aplay_process]:
            if process:
                try:
                    process.terminate()
                    process.wait(timeout=1)
                except:
                    try:
                        if process.poll() is None:
                            process.kill()
                            process.wait(timeout=1)
                    except:
                        pass
        
        self.arecord_process = None
        self.sox_process = None
        self.aplay_process = None

    def signal_handler(self, sig, frame):
        """Manejador de señales para terminar limpiamente"""
        print("\nDeteniendo procesos...")
        self.cleanup()
        sys.exit(0)

    def start(self):
        """Start audio bridge"""
        if self.running:
            return True
            
        try:
            logging.info("Starting audio bridge with 1 second delay...")
            
            # Remove signal handler registration from here as it's handled in run-lgpt.py
            
            arecord_cmd = [
                "arecord",
                "-D", self.input_device,
                "-f", "S16_LE",
                "-c", "2",
                "-r", "44100",
                "-B", "65536"
            ]

            sox_cmd = [
                "sox",
                "-t", "raw",        # Formato de entrada
                "-r", "44100",      # Sample rate
                "-b", "16",         # Bits por muestra
                "-c", "2",          # Canales
                "-e", "signed",     # Codificación
                "-",                # Entrada desde stdin
                "-t", "raw",        # Formato de salida
                "-r", "44100",      # Sample rate
                "-b", "16",         # Bits por muestra
                "-c", "2",          # Canales
                "-e", "signed",     # Codificación
                "-",                # Salida a stdout
                "delay", "1", "1",   # Efecto de delay de 0.5 segundos
                "equalizer", "60", "10q", "6",      # Realce graves
                "equalizer", "1000", "5q", "-6",    # Atenúa medios (1kHz)
                "equalizer", "12000", "10q", "6"    # Realce agudos
            ]

            aplay_cmd = [
                "aplay",
                "-D", self.output_device,
                "-f", "S16_LE",
                "-c", "2",
                "-r", "44100",
                "-B", "65536"
            ]

            self.arecord_process = subprocess.Popen(arecord_cmd, stdout=subprocess.PIPE)
            self.sox_process = subprocess.Popen(sox_cmd, stdin=self.arecord_process.stdout, stdout=subprocess.PIPE)
            self.aplay_process = subprocess.Popen(aplay_cmd, stdin=self.sox_process.stdout)
            
            # Don't close stdout pipes immediately
            self.running = True
            return True

        except Exception as e:
            logging.error(f"Audio bridge error: {e}")
            self.cleanup()
            return False

    def stop(self):
        """Stop the audio bridge"""
        logging.info("Stopping audio bridge...")
        self.cleanup()