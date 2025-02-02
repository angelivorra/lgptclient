#!/usr/bin/env python3
import subprocess
import sys
import time
import signal
import logging
from pathlib import Path

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
        subprocess.run(["sudo", "pkill", "arecord"], check=False)
        subprocess.run(["sudo", "pkill", "aplay"], check=False)
        subprocess.run(["sudo", "/etc/init.d/alsa-utils", "stop"], check=False)
    except Exception as e:
        logging.error(f"Cleanup error: {e}")

def is_process_running(process_name):
    """Check if a process is already running"""
    try:
        output = subprocess.run(["pgrep", process_name], capture_output=True, text=True)
        return output.returncode == 0
    except Exception as e:
        logging.error(f"Error checking process {process_name}: {e}")
        return False

def restart_audio():
    """Restart audio subsystem"""
    try:
        cleanup()
        subprocess.run(["sudo", "/etc/init.d/alsa-utils", "start"], check=True)
        
        # Check if arecord and aplay are already running
        if not is_process_running("arecord") and not is_process_running("aplay"):
            # Start arecord and aplay as separate processes
            arecord_process = subprocess.Popen(
                ["sudo", "arecord", "-D", "hw:Loopback,1", "-f", "cd"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            aplay_process = subprocess.Popen(
                ["sudo", "aplay", "-D", "movida"],
                stdin=arecord_process.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        
        # Restart server service
        subprocess.run(["sudo", "systemctl", "restart", "servidor"], check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to restart audio: {e}")
        return False
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
