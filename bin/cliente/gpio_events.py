import csv
from datetime import datetime
import RPi.GPIO as GPIO
import asyncio
import logging
import json

TIMING_CSV = '/home/angel/timing_analysis.csv'

logger = logging.getLogger(__name__)

# Load the config to get GPIO instrument pin mapping and time
with open('/home/angel/config.json') as f:
    config = json.load(f)

instruments = config["instruments"]
PINES = config["pines"]

def init_gpio():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    for pin in instruments.values():
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)

async def activate_instrumento(pin, scheduled_time, debug=False, ruido=False):
    if scheduled_time:
        # Calculate wait time
        now = datetime.now().timestamp() * 1000
        wait_ms = max(0, scheduled_time - now)
        if wait_ms > 0:
            await asyncio.sleep(wait_ms / 1000)
    
    if debug:
        with open(TIMING_CSV, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([scheduled_time, int(datetime.now().timestamp() * 1000)])
              
    if ruido:
        GPIO.output(pin, GPIO.HIGH)
        await asyncio.sleep(PINES[str(pin)].get('tiempo', 0))
        GPIO.output(pin, GPIO.LOW)

def cleanup_gpio():
    logger.info('Cleaning up GPIO')
    GPIO.cleanup()
    logger.info('GPIO cleanup complete')