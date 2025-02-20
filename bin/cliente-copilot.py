import asyncio
import re
import signal
import subprocess
from typing import List, Union
import RPi.GPIO as GPIO
import time
import logging
import os
import json
import csv
from datetime import datetime

logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)

CSV_FILENAME = '/home/angel/midi_notes_log.csv'
DEBUG_NOTES = False
TMP_FILE = '/tmp/debug_notes.tmp'
WIFI_FILE = '/home/angel/wifi.json'

with open('/home/angel/config.json') as f:
    config = json.load(f)

# Extract instruments and TIEMPO from the configuration
instruments = config["instruments"]
TIEMPO = config["tiempo"]
images_dict = {
    48: '/home/angel/images/three.jpg',
    49: '/home/angel/images/two.jpg',
    50: '/home/angel/images/one.jpg',
    51: '/home/angel/images/go.jpg',
}

#Inicializamos puertos GPIO
def init_gpio():
    # Set up GPIO
    GPIO.setmode(GPIO.BCM)

    # Set up each pin from the JSON configuration
    for pin in instruments.values():
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)

def initialize_csv(filename):
    """Initialize CSV file with headers if it doesn't exist."""
    if os.path.exists(filename):
        os.unlink(filename)
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["timestamp_sent", "note", "timestamp_received"])

async def activate_instrumento(ins):
    GPIO.output(ins, GPIO.HIGH)
    await asyncio.sleep(TIEMPO)
    GPIO.output(ins, GPIO.LOW)

async def handle_event(reader):
    while True:
        try:
            data = await reader.readline()
            if not data:
                logger.info("Connection closed by the server")
                break
            
            data = data.strip()
            
            logger.info(data)
            cleaned_data = re.sub(r'[^0-9,]', '', data.decode('utf-8'))
            
            # Validate the cleaned data
            try:
                sent_timestamp, note = cleaned_data.strip().split(',')
                sent_timestamp = int(sent_timestamp)
                current_timestamp = int(datetime.now().timestamp() * 1000)
            except ValueError:
                logger.error("Received malformed data, skipping row")
                continue
            sent_timestamp, note  = data.decode('utf-8').strip().split(',')
            sent_timestamp = int(sent_timestamp)
            current_timestamp = int(datetime.now().timestamp() * 1000)
            
            note = int(note)
            print(f"recievedNote({note})")
            
            if note in instruments:
                asyncio.ensure_future(activate_instrumento(instruments[note]))
            
            
            # Log the received note and timestamps
            if DEBUG_NOTES:
                with open(CSV_FILENAME, mode='a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow([sent_timestamp, note, current_timestamp])
        except Exception as e:
            logger.error(f"Error handling event: {e}")
            break

async def tcp_client(addr, port):
    while True:
        try:
            logger.info(f"Attempting to connect to {addr}:{port}")
            reader, writer = await asyncio.open_connection(addr, port)
            logger.info("Connected to server")
            await handle_event(reader)
        except (ConnectionError, OSError) as e:
            logger.info(f"Connection failed: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.info(f"An unexpected error occurred: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)        

def cleanup():
    logger.info('Cleaning up GPIO')
    GPIO.cleanup()
    # Stop the asyncio event loop
    asyncio.get_event_loop().stop()


async def shutdown(loop, signal=None):
    """Cleanup tasks tied to the service's shutdown."""
    if signal:
        logger.info(f"Received exit signal {signal.name}...")
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    
    [task.cancel() for task in tasks]
    logger.info("Canceling outstanding tasks")
    
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Tasks canceled, stopping loop")
    
    loop.stop()

def setup_signal_handlers(loop):
    """Setup signal handlers for SIGTERM and SIGINT."""
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.ensure_future(shutdown(loop, sig)))

if __name__ == '__main__':
    server_addr = '192.168.0.2'
    server_port = 8888  # Replace with the correct port
    
    init_gpio()
    
    if os.path.exists(TMP_FILE):
        DEBUG_NOTES = True
        os.remove(TMP_FILE)
        logger.info("Debug Mode Initiated")
        initialize_csv(CSV_FILENAME)    
        #save_wifi_quality()
    
    try:
        loop = asyncio.get_event_loop()
        setup_signal_handlers(loop)
        loop.run_until_complete(tcp_client(server_addr, server_port))
    except KeyboardInterrupt:
        logger.error("Program interrupted")
    finally:
        cleanup()