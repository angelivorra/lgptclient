#!/usr/bin/env python3
import subprocess
import sys
import time
import signal
import logging
import os
import select

from alsa_delay_bridge import ALSADelayBridge

# Constants
LGPT = '/home/angel/lgptclient/lgpt/bin/lgpt.rpi-exe'
LOG_FILE = "/home/angel/lgpt.log"
EXEC_LOG_FILE = "/home/angel/lgpt.exec.log"


# Configure logging
logging.basicConfig(
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)

class LGPTRunner:
    """Runner: inicia delay ALSA y luego LGPT con reinicio en fallo.

    Mejora apagado:
      - Lee stdout/stderr en streaming para no bloquear.
      - Al recibir señal marca running=False y envía SIGTERM al grupo.
      - Escala a SIGKILL si no termina en timeout.
    """
    def __init__(self):
        self.lgpt_process: subprocess.Popen | None = None
        self.running = True
        self.delay_bridge = ALSADelayBridge()
        self.restart_count = 0
        self.last_stdout = []  # lines
        self.last_stderr = []

    def start_process(self):
        logging.info("Starting LGPT process (sudo, ALSA direct)...")
        env_vars = [f"HOME={os.path.expanduser('~')}"]
        cmd = ["sudo", "env"] + env_vars + [LGPT]
        logging.debug("Command: %s", ' '.join(cmd))
        # start_new_session crea nuevo grupo de procesos (similar a setsid)
        self.lgpt_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True
        )

    def stream_until_exit(self):
        """Lee stdout/stderr hasta que el proceso termina o se solicita parada."""
        if not self.lgpt_process:
            return 0
        p = self.lgpt_process
        stdout_fd = p.stdout.fileno() if p.stdout else None
        stderr_fd = p.stderr.fileno() if p.stderr else None
        fds = [fd for fd in (stdout_fd, stderr_fd) if fd is not None]
        # Usamos poll con timeout pequeño para permitir chequeo running
        poller = select.poll()
        for fd in fds:
            poller.register(fd, select.POLLIN | select.POLLHUP | select.POLLERR)
        start_time = time.time()
        while self.running and p.poll() is None:
            events = poller.poll(300)  # ms
            for fd, ev in events:
                if ev & (select.POLLIN | select.POLLHUP):
                    try:
                        if fd == stdout_fd and p.stdout:
                            line = p.stdout.readline()
                            if line:
                                self.last_stdout.append(line)
                        elif fd == stderr_fd and p.stderr:
                            line = p.stderr.readline()
                            if line:
                                self.last_stderr.append(line)
                    except Exception:
                        pass
        # Drain restante (por si acabó solo)
        try:
            if p.stdout:
                for line in p.stdout.readlines():
                    self.last_stdout.append(line)
        except Exception:
            pass
        try:
            if p.stderr:
                for line in p.stderr.readlines():
                    self.last_stderr.append(line)
        except Exception:
            pass
        return p.returncode if p.returncode is not None else 0

    def terminate_process(self, timeout=3.0):
        if not self.lgpt_process:
            return
        p = self.lgpt_process
        if p.poll() is not None:
            return
        try:
            logging.info("Enviando SIGTERM a LGPT (grupo)...")
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except Exception as e:
            logging.warning(f"No se pudo enviar SIGTERM al grupo: {e}; intento terminate()")
            try:
                p.terminate()
            except Exception:
                pass
        # Espera escalonada
        end = time.time() + timeout
        while time.time() < end:
            if p.poll() is not None:
                break
            time.sleep(0.1)
        if p.poll() is None:
            logging.warning("Forzando SIGKILL a LGPT (grupo)...")
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except Exception as e:
                logging.error(f"Fallo SIGKILL grupo: {e}")
            # última espera corta
            time.sleep(0.3)

    def cleanup(self):
        self.running = False
        logging.info("Cleaning up LGPT process...")
        try:
            self.terminate_process()
        except Exception:
            pass
        try:
            self.delay_bridge.stop()
        except Exception:
            pass
        self.lgpt_process = None

def signal_handler(signum, frame):
    """Handle graceful shutdown on SIGTERM/SIGINT"""
    logging.info(f"Received signal {signum}, shutting down...")
    if hasattr(signal_handler, 'runner'):
        signal_handler.runner.cleanup()
    sys.exit(0)

def launch_lgpt(runner: LGPTRunner):
    runner.start_process()

def main():
    runner = LGPTRunner()
    signal_handler.runner = runner
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start delay bridge once outside restart loop
    if not runner.delay_bridge.start():
        logging.error("No se pudo iniciar delay bridge; abortando")
        return

    retry_delay = float(os.environ.get("LGPT_RETRY_DELAY", "3"))
    max_restarts = int(os.environ.get("LGPT_MAX_RESTARTS", "-1"))  # -1 = infinito
    while runner.running and (max_restarts < 0 or runner.restart_count <= max_restarts):
        try:
            runner.start_process()
            code = runner.stream_until_exit()

            # Escribir logs capturados
            try:
                with open(EXEC_LOG_FILE, "w") as log_file:
                    log_file.write("=== OUTPUT ===\n")
                    log_file.writelines(runner.last_stdout)
                    log_file.write("\n=== ERRORS ===\n")
                    log_file.writelines(runner.last_stderr)
                    log_file.write(f"\nEXIT CODE: {code}\n")
            except Exception as e:
                logging.error(f"No se pudo escribir EXEC_LOG_FILE: {e}")
            runner.last_stdout.clear()
            runner.last_stderr.clear()

            if not runner.running:
                logging.info("Salida solicitada; no se relanza.")
                break
            runner.restart_count += 1
            logging.info(f"LGPT terminó (code={code}) -> reinicio #{runner.restart_count} en {retry_delay:.1f}s")
            if max_restarts >= 0 and runner.restart_count > max_restarts:
                logging.warning("Alcanzado LGPT_MAX_RESTARTS. Fin del loop.")
                break
            time.sleep(retry_delay)
        except Exception as e:
            logging.error(f"Main loop error: {e}")
            if not runner.running:
                break
            time.sleep(retry_delay)
    logging.info("Loop principal finalizado.")

if __name__ == "__main__":
    main()