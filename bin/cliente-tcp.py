import asyncio
import pickle
import RPi.GPIO as GPIO
import time
import logging
import signal

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s:%(message)s',
)

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
            print(f"Received note - {note}")
            if note == "60":
                asyncio.ensure_future(activate_instrumento(BOMBO))
            elif note == "61":
                asyncio.ensure_future(activate_instrumento(CAJA1))
            elif note == "62":
                asyncio.ensure_future(activate_instrumento(CAJA2))
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
    server_addr = '192.168.100.1'
    server_port = 8888  # Replace with the correct port

    try:
        signal.signal(signal.SIGTERM, lambda signum, frame: cleanup())
        asyncio.run(tcp_client(server_addr, server_port))
    except KeyboardInterrupt:
        logger.error("Program interrupted")
    finally:
        cleanup()
