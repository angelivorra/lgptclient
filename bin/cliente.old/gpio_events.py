import RPi.GPIO as GPIO
import asyncio
import logging
import json

logger = logging.getLogger(__name__)

# Load the config to get GPIO instrument pin mapping and time
with open('/home/angel/config.json') as f:
    config = json.load(f)

instruments = config["instruments"]
TIEMPO = config["tiempo"]

def init_gpio():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    for pin in instruments.values():
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)

async def activate_instrumento(ins):
    if isinstance(ins, int):
        ins = [ins]
    
    for pin in ins:
        GPIO.output(pin, GPIO.HIGH)
    
    await asyncio.sleep(TIEMPO)
    
    for pin in ins:
        GPIO.output(pin, GPIO.LOW)
        
def cleanup_gpio():
    logger.info('Cleaning up GPIO')
    GPIO.cleanup()