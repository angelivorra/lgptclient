import asyncio
import pickle
import RPi.GPIO as GPIO
import time
import bluetooth
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
    #logger.debug(f'activate {ins}')
    #return
    GPIO.output(ins, GPIO.HIGH)
    await asyncio.sleep(TIEMPO)
    GPIO.output(ins, GPIO.LOW)

async def handle_event(sock):
    loop = asyncio.get_running_loop()
    while True:
        try:
            data = await loop.run_in_executor(None, sock.recv, 1024)
            if not data:
                logger.info("Connection closed by the server")
                break
            note = data.decode('utf-8')
            #note = int.from_bytes(data)
            print(f"nota - {note}")
            if note == "60":
                asyncio.ensure_future(activate_instrumento(BOMBO))
            elif note == "61":
                asyncio.ensure_future(activate_instrumento(CAJA1))
            elif note == "62":
                asyncio.ensure_future(activate_instrumento(CAJA2))
            #    asyncio.ensure_future(activate_instrumento(BOMBO))asyncio.ensure_future(activate_instrumento(BOMBO))
            #elif event['note'] == 62:
            #    asyncio.ensure_future(activate_instrumento(CAJA))
            #else:
            #    pass
        except Exception as e:
            logger.error(f"Error handling event: {e}")
            break

async def bluetooth_client(addr, port):
    while True:
        try:
            logger.info(f"Attempting to connect to {addr}:{port}")
            sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            sock.connect((addr, port))
            logger.info("Connected to server")
            await handle_event(sock)
        except (bluetooth.btcommon.BluetoothError, OSError) as e:
            logger.info(f"Connection failed: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.info(f"An unexpected error occurred: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)
        finally:
            sock.close()

def cleanup():
    logger.info('Cleaning up GPIO')
    GPIO.cleanup()

if __name__ == '__main__':
    server_addr = 'D8:3A:DD:37:76:B9'  # Replace with the Bluetooth address of your server
    server_port = 3  # Replace with the correct port

    try:
        signal.signal(signal.SIGTERM, lambda signum, frame: cleanup())
        asyncio.run(bluetooth_client(server_addr, server_port))
    except KeyboardInterrupt:
        logger.error("Program interrupted")
    finally:
        cleanup()
