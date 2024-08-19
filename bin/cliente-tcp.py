import asyncio
import RPi.GPIO as GPIO
import time
import logging
import signal
import json
import csv
import os
from datetime import datetime

# Constants
CONFIG_PATH = '/home/angel/config.json'
CSV_FILENAME = '/home/angel/midi_notes_log.csv'
SERVER_ADDR = '10.42.0.1'
SERVER_PORT = 8888  # Replace with the correct port
RETRY_DELAY = 5  # Time to wait before retrying a failed connection



# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Load configuration
with open(CONFIG_PATH) as f:
    config = json.load(f)

# Extract instruments and TIEMPO from the configuration
instruments = config["instruments"]
TIEMPO = config["tiempo"]

# Initialize GPIO
GPIO.setmode(GPIO.BCM)
for pin in instruments.values():
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)

def initialize_csv(filename):
    """Initialize CSV file with headers if it doesn't exist."""
    if os.path.exists(filename):
        os.unlink(filename)
    with open(filename, mode='w', newline='') as file:        
        writer = csv.writer(file)
        writer.writerow(['tiempo', 'nota'])

async def activate_instrument(ins):
    """Activate the instrument for the configured duration."""
    GPIO.output(ins, GPIO.HIGH)
    await asyncio.sleep(TIEMPO)
    GPIO.output(ins, GPIO.LOW)

async def handle_event(reader):
    """Handle incoming events from the TCP connection."""
    while True:
        try:
            data = await reader.read(1024)
            if not data:
                logger.info("Connection closed by the server")
                break
            note = data.decode('utf-8').strip()
            timestamp_ms = int(datetime.now().timestamp() * 1000)
            with open(CSV_FILENAME, mode='a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow([timestamp_ms, "60"])
            if note in instruments:
                await log_event_to_csv(note)
                asyncio.ensure_future(activate_instrument(instruments[note]))
        except Exception as e:
            logger.error(f"Error handling event: {e}")
            break

async def tcp_client(addr, port):
    """TCP client that connects to the server and handles events."""
    while True:
        try:
            logger.info(f"Attempting to connect to {addr}:{port}")
            reader, writer = await asyncio.open_connection(addr, port)
            logger.info("Connected to server")
            await handle_event(reader)
        except (ConnectionError, OSError) as e:
            logger.info(f"Connection failed: {e}. Retrying in {RETRY_DELAY} seconds...")
            await asyncio.sleep(RETRY_DELAY)
        except Exception as e:
            logger.info(f"An unexpected error occurred: {e}. Retrying in {RETRY_DELAY} seconds...")
            await asyncio.sleep(RETRY_DELAY)
        finally:
            if 'writer' in locals():
                writer.close()
                await writer.wait_closed()

async def log_event_to_csv(note):
    """Log the note and timestamp to a CSV file."""
    timestamp_ms = int(datetime.now().timestamp() * 1000)
    with open(CSV_FILENAME, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([timestamp_ms, note])

def cleanup():
    """Clean up GPIO settings."""
    logger.info('Cleaning up GPIO')
    GPIO.cleanup()

def signal_handler(signum, frame):
    """Handle termination signals to ensure proper cleanup."""
    cleanup()
    exit(0)

if __name__ == '__main__':
    # Initialize CSV logging
    initialize_csv(CSV_FILENAME)

    # Register signal handlers for graceful termination
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        asyncio.run(tcp_client(SERVER_ADDR, SERVER_PORT))
    except KeyboardInterrupt:
        logger.error("Program interrupted")
    finally:
        cleanup()
