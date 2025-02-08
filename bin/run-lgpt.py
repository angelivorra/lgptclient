#!/usr/bin/env python3
import subprocess
import sys
import time
import signal
import logging

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

def signal_handler(signum, frame):
    """Handle graceful shutdown on SIGTERM/SIGINT"""
    logging.info(f"Received signal {signum}, shutting down...")
    cleanup()
    sys.exit(0)

def cleanup():
    """Clean up processes before exit"""
    try:
        time.sleep(1)  # Esperar 1 segundo para asegurar que los procesos se detengan
    except Exception as e:
        logging.error(f"Cleanup error: {e}")

def restart_audio():
    """Restart audio subsystem"""
    start_time = time.time()
    try:
        cleanup()

        subprocess.run(["sudo", "systemctl", "restart", "servidor"], check=True)
    except Exception as e:
        logging.error(f"Failed to restart audio: {e}")
        return False
    
    elapsed_time = time.time() - start_time
    logging.info(f"Audio restart took {elapsed_time:.2f} seconds")
    return True

def main():
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    while True:
        try:
            if not restart_audio():
                time.sleep(5)
                continue

            logging.info("Starting LGPT process...")
            with open(EXEC_LOG_FILE, "w") as log_file:
                process = subprocess.run(
                    LGPT,
                    capture_output=True,
                    text=True,
                    check=False
                )

                log_file.write("=== OUTPUT ===\n")
                log_file.write(process.stdout)
                log_file.write("\n=== ERRORS ===\n") 
                log_file.write(process.stderr)
                log_file.write(f"\nEXIT CODE: {process.returncode}\n")

                if process.returncode != 0:
                    logging.error(f"LGPT process failed with code {process.returncode}")
                    time.sleep(3)

        except Exception as e:
            logging.error(f"Main loop error: {e}")
            time.sleep(3)

if __name__ == "__main__":
    main()