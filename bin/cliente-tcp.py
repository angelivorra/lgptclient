import asyncio
import pickle
import RPi.GPIO as GPIO
import time
import logging
import signal
import json

logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)

with open('/home/angel/config.json') as f:
    config = json.load(f)

# Extract instruments and TIEMPO from the configuration
instruments = config["instruments"]

# Set up GPIO
GPIO.setmode(GPIO.BCM)

# Set up each pin from the JSON configuration
for pin in instruments.values():
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)

async def activate_instrumento(ins):
    GPIO.output(ins, GPIO.HIGH)
    await asyncio.sleep(TIEMPO)
    GPIO.output(ins, GPIO.LOW)

async def handle_event(reader):
    while True:
        try:
            data = await reader.read(1024)
            if not data:
                logger.info("Connection closed by the server")
                break
            note = data.decode('utf-8').strip()
            #logger.info(f"Received note - {note}")
            if note in instruments:
                asyncio.ensure_future(activate_instrumento(instruments[note]))
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
        finally:
            writer.close()
            await writer.wait_closed()

def cleanup():
    logger.info('Cleaning up GPIO')
    GPIO.cleanup()

if __name__ == '__main__':
    server_addr = '10.42.0.1'
    server_port = 8888  # Replace with the correct port

    try:
        signal.signal(signal.SIGTERM, lambda signum, frame: cleanup())
        asyncio.run(tcp_client(server_addr, server_port))
    except KeyboardInterrupt:
        logger.error("Program interrupted")
    finally:
        cleanup()
