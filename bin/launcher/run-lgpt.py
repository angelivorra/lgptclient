#!/usr/bin/env python3
import subprocess
import sys
import time
import signal
import logging
import os

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
    """Runner: inicia delay ALSA y luego LGPT con reinicio en fallo."""
    def __init__(self):
        self.lgpt_process = None
        self.running = True
        self.delay_bridge = ALSADelayBridge()

    def cleanup(self):
        self.running = False
        logging.info("Cleaning up LGPT process...")
        # Stop delay bridge first so playback device is released
        try:
            self.delay_bridge.stop()
        except Exception:
            pass

        if self.lgpt_process and self.lgpt_process.poll() is None:
            try:
                self.lgpt_process.terminate()
                self.lgpt_process.wait(timeout=3)
            except Exception:
                pass
            if self.lgpt_process.poll() is None:
                try:
                    os.killpg(os.getpgid(self.lgpt_process.pid), signal.SIGKILL)
                except Exception as e:
                    logging.error(f"Failed to kill LGPT process group: {e}")

def signal_handler(signum, frame):
    """Handle graceful shutdown on SIGTERM/SIGINT"""
    logging.info(f"Received signal {signum}, shutting down...")
    if hasattr(signal_handler, 'runner'):
        signal_handler.runner.cleanup()
    sys.exit(0)

def launch_lgpt(runner):
    """Launch LGPT process with sudo (ALSA direct)."""
    logging.info("Starting LGPT process (sudo, ALSA direct)...")
    env_vars = [f"HOME={os.path.expanduser('~')}"]
    cmd = ["sudo", "env"] + env_vars + [LGPT]
    logging.debug("Command: %s", ' '.join(cmd))
    runner.lgpt_process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        preexec_fn=os.setsid
    )

def main():
    runner = LGPTRunner()
    signal_handler.runner = runner
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start delay bridge once outside restart loop
    if not runner.delay_bridge.start():
        logging.error("No se pudo iniciar delay bridge; abortando")
        return

    retry_delay = 3
    while runner.running:
        try:
            launch_lgpt(runner)
            stdout, stderr = runner.lgpt_process.communicate()

            with open(EXEC_LOG_FILE, "w") as log_file:
                log_file.write("=== OUTPUT ===\n")
                log_file.write(stdout)
                log_file.write("\n=== ERRORS ===\n")
                log_file.write(stderr)
                log_file.write(f"\nEXIT CODE: {runner.lgpt_process.returncode}\n")

            code = runner.lgpt_process.returncode
            if code == 0:
                logging.info("LGPT exited cleanly (code 0). Stopping loop.")
                break
            else:
                logging.error(f"LGPT exited with code {code}. Restarting in {retry_delay}s...")
                time.sleep(retry_delay)
        except Exception as e:
            logging.error(f"Main loop error: {e}")
            time.sleep(retry_delay)

if __name__ == "__main__":
    main()