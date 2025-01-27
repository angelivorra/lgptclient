import asyncio
import csv
from datetime import datetime
import os
import json
import signal
import logging
from gpio_events import init_gpio, activate_instrumento
from image_events import activate_image, handle_image

# Logger setup
logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)

DEBUG_NOTES = False
CSV_FILENAME = '/home/angel/midi_notes_log.csv'
TMP_FILE = '/tmp/debug_notes.tmp'

with open('/home/angel/config.json') as f:
    config = json.load(f)

instruments = config["instruments"]
print(instruments)
TIEMPO = config["tiempo"]

def initialize_csv(filename):
    """Initialize CSV file with headers if it doesn't exist."""
    if os.path.exists(filename):
        os.unlink(filename)
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["timestamp_sent", "note", "timestamp_received"])


async def handle_event(reader):
    while True:
        try:
            data = await reader.readline()
            if not data:
                logger.info("Connection closed by the server")
                break

            data = data.strip()
            logger.debug(data)
            cleaned_data = data.decode('utf-8').strip().split(',')

            try:
                sent_timestamp, note, channel, velocity = map(int, cleaned_data)
                current_timestamp = int(datetime.now().timestamp() * 1000)
                if DEBUG_NOTES:
                    with open(CSV_FILENAME, mode='a', newline='') as file:
                        writer = csv.writer(file)
                        writer.writerow([sent_timestamp, note, current_timestamp])
                
            except ValueError:
                logger.error("Received malformed data, skipping row")
                continue            
            
            strnote = str(note)
            if channel == 0 and strnote in instruments:
                logger.debug(f"activate_instrumento{instruments[strnote]}")
                asyncio.ensure_future(activate_instrumento(instruments[strnote]))                        
            elif channel == 1:
                asyncio.ensure_future(activate_image(note, velocity))
            
        except Exception as e:
            logger.error(f"Error handling event: {e}")
            break

async def tcp_client(addr, port):
    while True:
        try:
            logger.info(f"Attempting to connect to {addr}:{port}")
            reader, writer = await asyncio.open_connection(addr, port)
            logger.info("Connected to server")
            #asyncio.ensure_future(handle_image(1, loop=6, delay=100))
            await handle_event(reader)            
        except (ConnectionError, OSError) as e:
            logger.info(f"Connection failed: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.info(f"An unexpected error occurred: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)

async def shutdown(loop, signal=None):
    if signal:
        logger.info(f"Received exit signal {signal.name}...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    logger.info("Canceling outstanding tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Tasks canceled, stopping loop")
    loop.stop()

def setup_signal_handlers(loop):
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

    try:
        loop = asyncio.get_event_loop()
        setup_signal_handlers(loop)
        loop.run_until_complete(tcp_client(server_addr, server_port))
    except KeyboardInterrupt:
        logger.error("Program interrupted")
    finally:
        logger.info("Cleaning up before exit")
