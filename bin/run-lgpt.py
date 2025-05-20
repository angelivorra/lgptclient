#!/usr/bin/env python3
import subprocess
import sys
import time
import signal
import logging
import os
from audio_setup import AudioBridge

# Constants
LGPT = '/home/angel/lgptclient/lgpt/bin/lgpt.rpi-exe'
LOG_FILE = "/home/angel/lgpt.log"
EXEC_LOG_FILE = "/home/angel/lgpt.exec.log"
ARECORD_LOG = "/home/angel/arecord.log"

# Configure logging
logging.basicConfig(
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)

class LGPTRunner:
    def __init__(self):
        self.audio_bridge = AudioBridge()
        self.lgpt_process = None
        self.running = True

    def cleanup(self):
        """Clean up all processes"""
        self.running = False
        logging.info("Cleaning up processes...")
        
        # Stop audio bridge
        if self.audio_bridge:
            self.audio_bridge.stop()
        
        # Kill LGPT process if running
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

def restart_audio(runner):
    """Restart audio subsystem"""
    start_time = time.time()
    try:
        # First restart system service
        subprocess.run(["sudo", "systemctl", "restart", "servidor"], check=True)
        time.sleep(2)
        
        if not runner.audio_bridge.start():
            logging.error("Failed to start audio bridge")
            return False
            
    except Exception as e:
        logging.error(f"Failed to restart audio: {e}")
        return False
    
    elapsed_time = time.time() - start_time
    logging.info(f"Audio restart took {elapsed_time:.2f} seconds")
    return True

def main():
    runner = LGPTRunner()
    signal_handler.runner = runner
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    while runner.running:
        try:
            if not restart_audio(runner):
                runner.audio_bridge.cleanup()
                time.sleep(5)
                continue

            logging.info("Starting LGPT process...")
            runner.lgpt_process = subprocess.Popen(
                ["sudo", LGPT],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=os.setsid  # <-- importante para grupos de procesos
            )

            # Wait for LGPT process to finish
            stdout, stderr = runner.lgpt_process.communicate()
            
            with open(EXEC_LOG_FILE, "w") as log_file:
                log_file.write("=== OUTPUT ===\n")
                log_file.write(stdout)
                log_file.write("\n=== ERRORS ===\n") 
                log_file.write(stderr)
                log_file.write(f"\nEXIT CODE: {runner.lgpt_process.returncode}\n")

            if runner.lgpt_process.returncode != 0:
                logging.error(f"LGPT process failed with code {runner.lgpt_process.returncode}")
                time.sleep(3)

        except Exception as e:
            logging.error(f"Main loop error: {e}")
            runner.cleanup()
            time.sleep(3)

if __name__ == "__main__":
    main()