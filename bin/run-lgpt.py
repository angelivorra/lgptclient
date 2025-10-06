#!/usr/bin/env python3
import subprocess
import sys
import time
import signal
import logging
import os
import shutil
from typing import List, Tuple

"""
Script de arranque orquestado:
 1. Arranca jackd (si no está ya corriendo)
 2. Arranca alsa_in para capturar Loopback (LGPT → JACK)
 3. Conecta puertos LGPT:capture_* a system:playback_*
 4. Lanza el binario de LGPT

 Ajusta las constantes JACKD_CMD, ALSA_IN_CMD y CONNECTIONS a tu hardware.
 Usa sudo sólo si realmente lo necesitas (ideal: correr todo como usuario en grupo 'audio').
"""

# ===================== CONFIGURACIÓN =====================
LGPT = '/home/angel/lgptclient/lgpt/bin/lgpt.rpi-exe'
LOG_FILE = "/home/angel/lgpt.log"
EXEC_LOG_FILE = "/home/angel/lgpt.exec.log"

# Dispositivo físico (playback) y loopback (captura) — ajusta si cambian enumeraciones
JACK_SAMPLE_RATE = '44100'
JACK_PERIOD = '512'
JACK_NPERIODS = '3'
HW_PLAYBACK = 'hw:IQaudIODAC'   # Tarjeta de salida real
HW_LOOPBACK_CAPTURE = 'hw:2,1,0'  # Loopback capture (LGPT audio)

# Comando jackd (sin sudo idealmente). Añade 'sudo' al principio si sigues necesitando root.
JACKD_CMD: List[str] = [
    'jackd', '-R', '-P70', '-d', 'alsa', '-d', HW_PLAYBACK,
    '-r', JACK_SAMPLE_RATE, '-p', JACK_PERIOD, '-n', JACK_NPERIODS, '-S'
]

# Comando alsa_in alineado con parámetros JACK
ALSA_IN_CMD: List[str] = [
    'alsa_in', '-j', 'LGPT', '-d', HW_LOOPBACK_CAPTURE,
    '-r', JACK_SAMPLE_RATE, '-c', '2', '-p', JACK_PERIOD, '-n', JACK_NPERIODS, '-q', '1'
]

# Conexiones a forzar (fuente, destino)
CONNECTIONS: List[Tuple[str, str]] = [
    ('LGPT:capture_1', 'system:playback_1'),
    ('LGPT:capture_2', 'system:playback_2'),
]

# Tiempo máximo de espera (segundos)
JACK_START_TIMEOUT = 10
ALSA_IN_PORT_TIMEOUT = 10
RETRY_DELAY = 3
CHECK_INTERVAL = 0.5

# Variables de entorno adicionales para JACK (opcional)
JACK_ENV = {
    'JACK_NO_AUDIO_RESERVATION': '1',
    'JACK_PROMISCUOUS_SERVER': '1',
}

# Configure logging
logging.basicConfig(
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)

class LGPTRunner:
    def __init__(self):
        self.lgpt_process = None
        self.jackd_process = None
        self.alsa_in_process = None
        self.running = True

    # -------------------- UTILIDADES --------------------
    def _which_or_fail(self, cmd: str):
        if shutil.which(cmd) is None:
            logging.error(f"No se encontró el comando requerido: {cmd}")
            raise FileNotFoundError(cmd)

    def _run_simple(self, args: List[str], env_add: dict = None, **popen_kwargs):
        env = os.environ.copy()
        if env_add:
            env.update(env_add)
        return subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid,
            env=env,
            **popen_kwargs
        )

    def _jack_lsp(self) -> List[str]:
        try:
            out = subprocess.check_output(['jack_lsp'], text=True, stderr=subprocess.DEVNULL)
            return [l.strip() for l in out.splitlines() if l.strip()]
        except Exception:
            return []

    def _jack_lsp_connections(self) -> List[str]:
        try:
            out = subprocess.check_output(['jack_lsp', '-c'], text=True, stderr=subprocess.DEVNULL)
            return out.splitlines()
        except Exception:
            return []

    # -------------------- JACK --------------------
    def start_jackd(self):
        # Detectar si ya está corriendo (jack_lsp debe devolver código 0)
        if subprocess.call(['jack_lsp'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
            logging.info("jackd ya está en ejecución. No se relanza.")
            return True

        self._which_or_fail(JACKD_CMD[0])
        logging.info("Arrancando jackd: %s", ' '.join(JACKD_CMD))
        try:
            self.jackd_process = self._run_simple(JACKD_CMD, env_add=JACK_ENV)
        except Exception as e:
            logging.error(f"Fallo al lanzar jackd: {e}")
            return False

        # Esperar a que responda jack_lsp
        start = time.time()
        while time.time() - start < JACK_START_TIMEOUT:
            if subprocess.call(['jack_lsp'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
                logging.info("jackd operativo.")
                return True
            time.sleep(CHECK_INTERVAL)

        logging.error("Timeout esperando a jackd")
        return False

    # -------------------- ALSA_IN --------------------
    def start_alsa_in(self):
        # Si ya existen los puertos evita duplicar
        ports = self._jack_lsp()
        if any(p.startswith('LGPT:capture_1') for p in ports):
            logging.info("alsa_in ya parece activo (puertos LGPT:capture_* detectados).")
            return True

        self._which_or_fail(ALSA_IN_CMD[0])
        logging.info("Arrancando alsa_in: %s", ' '.join(ALSA_IN_CMD))
        try:
            self.alsa_in_process = self._run_simple(ALSA_IN_CMD)
        except Exception as e:
            logging.error(f"Fallo al lanzar alsa_in: {e}")
            return False

        # Esperar aparición de puertos
        start = time.time()
        while time.time() - start < ALSA_IN_PORT_TIMEOUT:
            ports = self._jack_lsp()
            if 'LGPT:capture_1' in ports and 'LGPT:capture_2' in ports:
                logging.info("Puertos LGPT:capture_* disponibles.")
                return True
            # Comprobar si el proceso murió
            if self.alsa_in_process.poll() is not None:
                out, err = self.alsa_in_process.communicate()
                logging.error(f"alsa_in terminó prematuramente. stdout: {out}\nstderr: {err}")
                return False
            time.sleep(CHECK_INTERVAL)

        logging.error("Timeout esperando a puertos de alsa_in")
        return False

    # -------------------- Conexiones --------------------
    def ensure_connections(self):
        for src, dst in CONNECTIONS:
            if self._is_connected(src, dst):
                continue
            self._connect(src, dst)

    def _is_connected(self, src: str, dst: str) -> bool:
        lines = self._jack_lsp_connections()
        # Formato típico: 'LGPT:capture_1' luego indentaciones con conexiones
        current = None
        connections = []
        for line in lines:
            if not line.startswith('    '):
                current = line.strip()
            else:
                if current:
                    connections.append((current, line.strip()))
        return any(a == src and b == dst for a, b in connections)

    def _connect(self, src: str, dst: str):
        logging.info(f"Conectando {src} -> {dst}")
        try:
            subprocess.check_call(['jack_connect', src, dst])
        except subprocess.CalledProcessError as e:
            logging.error(f"No se pudo conectar {src} -> {dst}: {e}")

    # -------------------- LGPT --------------------
    def start_lgpt(self):
        if not os.path.isfile(LGPT):
            logging.error(f"Binario LGPT no encontrado en {LGPT}")
            return False
        cmd = ['sudo', LGPT] if os.geteuid() != 0 else [LGPT]
        logging.info("Lanzando LGPT: %s", ' '.join(cmd))
        try:
            self.lgpt_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=os.setsid
            )
            return True
        except Exception as e:
            logging.error(f"No se pudo lanzar LGPT: {e}")
            return False

    def cleanup(self):
        """Clean up all processes"""
        self.running = False
        logging.info("Cleaning up processes...")
        
        # Procesos (orden inverso)
        self._terminate_process(self.lgpt_process, 'LGPT')
        self._terminate_process(self.alsa_in_process, 'alsa_in')
        self._terminate_process(self.jackd_process, 'jackd')

    def _terminate_process(self, proc, name: str):
        if not proc:
            return
        if proc.poll() is None:
            logging.info(f"Terminando {name}...")
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                pass
            if proc.poll() is None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception as e:
                    logging.error(f"No se pudo forzar cierre de {name}: {e}")

def signal_handler(signum, frame):
    """Handle graceful shutdown on SIGTERM/SIGINT"""
    logging.info(f"Received signal {signum}, shutting down...")
    if hasattr(signal_handler, 'runner'):
        signal_handler.runner.cleanup()
    sys.exit(0)

def prepare_audio_stack(runner: LGPTRunner) -> bool:
    start_time = time.time()
    logging.info("Preparando pila de audio (jackd + alsa_in + conexiones)...")

    if not runner.start_jackd():
        return False
    if not runner.start_alsa_in():
        return False
    runner.ensure_connections()

    elapsed = time.time() - start_time
    logging.info(f"Pila de audio lista en {elapsed:.2f}s")
    return True

def main():
    runner = LGPTRunner()
    signal_handler.runner = runner
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Preparar pila audio una vez (o reintentos si falla)
    audio_ready = False
    attempts = 0
    while not audio_ready and attempts < 3 and runner.running:
        audio_ready = prepare_audio_stack(runner)
        if not audio_ready:
            attempts += 1
            logging.error(f"Fallo preparando audio. Reintentando ({attempts}/3) en {RETRY_DELAY}s")
            time.sleep(RETRY_DELAY)

    if not audio_ready:
        logging.critical("No se pudo preparar la pila de audio. Abortando.")
        runner.cleanup()
        sys.exit(1)

    # Lanzar LGPT
    if not runner.start_lgpt():
        runner.cleanup()
        sys.exit(1)

    # Esperar a que termine LGPT y registrar salida
    stdout, stderr = runner.lgpt_process.communicate()
    with open(EXEC_LOG_FILE, 'w') as f:
        f.write('=== OUTPUT ===\n')
        f.write(stdout or '')
        f.write('\n=== ERRORS ===\n')
        f.write(stderr or '')
        f.write(f"\nEXIT CODE: {runner.lgpt_process.returncode}\n")

    if runner.lgpt_process.returncode != 0:
        logging.error(f"LGPT terminó con código {runner.lgpt_process.returncode}")
    else:
        logging.info("LGPT terminó correctamente.")

    runner.cleanup()

if __name__ == "__main__":
    main()