import asyncio
import pickle
import RPi.GPIO as GPIO
import logging
import signal
from bleak import BleakClient

# Logging configuration
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s:%(message)s',
)

# GPIO Pins configuration
BOMBO = 17
CAJA1 = 27
CAJA2 = 22
TIEMPO = 0.05

# Set up GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(BOMBO, GPIO.OUT)
GPIO.setup(CAJA2, GPIO.OUT)
GPIO.setup(CAJA1, GPIO.OUT)
GPIO.output(CAJA1, GPIO.LOW)
GPIO.output(CAJA2, GPIO.LOW)
GPIO.output(BOMBO, GPIO.LOW)

# BLE characteristic UUIDs
SERVICE_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID = "00002a29-0000-1000-8000-00805f9b34fb"

async def activate_instrument(ins):
    GPIO.output(ins, GPIO.HIGH)
    await asyncio.sleep(TIEMPO)
    GPIO.output(ins, GPIO.LOW)

async def handle_notification(sender, data):
    try:
        note = pickle.loads(data)
        logger.debug(f"Received note: {note}")
        
        if note == 60:
            await activate_instrument(BOMBO)
        elif note == 61:
            await activate_instrument(CAJA1)
        elif note == 62:
            await activate_instrument(CAJA2)
    except Exception as e:
        logger.error(f"Error processing notification: {e}")

async def ble_client(server_address):
    async with BleakClient(server_address) as client:
        logger.info("Connected to BLE server")

        # Subscribe to notifications
        await client.start_notify(CHARACTERISTIC_UUID, handle_notification)

        logger.info("Subscribed to BLE notifications. Listening for events...")
        while True:
            await asyncio.sleep(1)  # Keep the connection alive

def cleanup():
    logger.info('Cleaning up GPIO')
    GPIO.cleanup()

if __name__ == '__main__':
    server_addr = "D8:3A:DD:37:76:B9"  # Replace with your BLE server's address

    try:
        signal.signal(signal.SIGTERM, lambda signum, frame: cleanup())
        asyncio.run(ble_client(server_addr))
    except KeyboardInterrupt:
        logger.error("Program interrupted")
    finally:
        cleanup()
