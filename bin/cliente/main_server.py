import asyncio
import csv
from datetime import datetime
import os
import json
import signal
import logging
from gpio_events import init_gpio, activate_instrumento, cleanup_gpio
from frame_buffer import Framebuffer
from display_manager import DisplayManager

logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.DEBUG,
    datefmt='%Y-%m-%d %H:%M:%S'
)

CSV_FILENAME = '/home/angel/midi_notes_log.csv'
TIMING_CSV = '/home/angel/timing_analysis.csv'
MECHANICAL_DELAY = 0

with open('/home/angel/config.json') as f:
    config = json.load(f)

instruments = config["instruments"]
PINES = config["pines"]

def initialize_timing_csv():
    with open(TIMING_CSV, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['expected_timestamp', 'executed_timestamp'])

def initialize_csv(filename):
    if os.path.exists(filename):
        os.unlink(filename)
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["timestamp_sent", "note", "timestamp_received"])

def parse_config(config_line):
    try:
        cmd, delay, debug, ruido = config_line.split(',')
        if cmd != 'CONFIG':
            raise ValueError("Invalid config format")        
        delay = int(delay)
        debug_mode = debug.lower() == 'true'
        ruido = ruido.lower() == 'true'
        logger.info(f"Configuration set: delay={delay}ms, debug={debug_mode}, ruido={ruido}")
        return True, delay, debug_mode, ruido
    except Exception as e:
        logger.error(f"Error parsing config: {e}")
        return False, 0, False, False

async def handle_event(reader, display_manager):
    config_line = (await reader.readline()).decode().strip()
    success, delay, debug_mode, ruido = parse_config(config_line)
    if not success:
        logger.error("Failed to parse initial configuration")
        return
    # if debug_mode:
    #     initialize_csv(CSV_FILENAME)
    #     initialize_timing_csv()
    
    while True:
        try:
            data = await reader.readline()
            if not data:
                logger.info("Connection closed by the server")
                await display_manager.set_state("off")  # Mostrar "off" cuando se cierra la conexión
                break

            data = data.strip()
                       
            cleaned_data = data.decode('utf-8').strip().split(',')

            try:
                sent_timestamp, note, channel, velocity = map(int, cleaned_data)
                current_timestamp = int(datetime.now().timestamp() * 1000)
                expected_timestamp = sent_timestamp + delay  # delay is the network/processing delay            
                
                if debug_mode:
                    with open(CSV_FILENAME, mode='a', newline='') as file:
                        writer = csv.writer(file)
                        writer.writerow([sent_timestamp, note, current_timestamp])
                
                strnote = str(note)
                if channel == 0 and strnote in instruments:
                    ins = instruments[strnote]
                    if isinstance(ins, int):
                        ins = [ins]
                    for pin in ins:
                        expected_timestamp = expected_timestamp - PINES[str(pin)].get('delay', 0)
                        asyncio.create_task(
                            activate_instrumento(
                                pin,
                                scheduled_time=expected_timestamp,
                                debug=debug_mode,
                                ruido=ruido
                            )
                        )
                elif channel == 1:
                    await display_manager.set_state("image", image_id=note)

            except ValueError:
                logger.error("Received malformed data, skipping row")
                continue
            
        except Exception as e:
            logger.error(f"Error handling event: {e}")
            await display_manager.set_state("off")  # Mostrar "off" en caso de error
            break

async def tcp_client(addr, port, display_manager):
    while True:
        try:
            await display_manager.set_state("connecting")  # Mostrar "off" cuando la conexión falla
            logger.info(f"Attempting to connect to {addr}:{port}")
            reader, writer = await asyncio.open_connection(addr, port)
            logger.info("Connected to server")
            await display_manager.set_state("connected")  # Mostrar "connected" cuando la conexión es exitosa
            await handle_event(reader, display_manager)            
        except (ConnectionError, OSError) as e:
            logger.info(f"Connection failed: {e}. Retrying in 5 seconds...")
            await display_manager.set_state("connecting")  # Mostrar "off" cuando la conexión falla
            await asyncio.sleep(5)
        except Exception as e:
            logger.info(f"An unexpected error occurred: {e}. Retrying in 5 seconds...")
            await display_manager.set_state("connecting")  # Mostrar "off" en caso de error inesperado
            await asyncio.sleep(5)

async def shutdown(loop, signal=None, display_manager=None):
    if signal:
        logger.info(f"Received exit signal {signal.name}...")
    
    if display_manager:
        await display_manager.set_state("off")  # Mostrar "off" durante el apagado
    await asyncio.sleep(1)
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    logger.info(f"Canceling {len(tasks)} outstanding tasks")
    
    for task in tasks:
        task.cancel()
    
    # Wait for tasks to be canceled
    await asyncio.sleep(1)
    
    # Gather canceled tasks
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Task raised an exception: {result}")
    
    logger.info("Tasks canceled, stopping loop")

    loop.stop()

def setup_signal_handlers(loop, display_manager):
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(loop, sig, display_manager)))

async def main():
    server_addr = '192.168.0.2'
    server_port = 8888
    
    logger.info("Starting client application...")
    init_gpio()

    # Initialize Framebuffer and DisplayManager
    fb = Framebuffer()
    fb.open()
    display_manager = DisplayManager(fb)

    loop = asyncio.get_event_loop()
    setup_signal_handlers(loop, display_manager)
    
    try:
        await tcp_client(server_addr, server_port, display_manager)
    except asyncio.CancelledError:
        logger.info("Main task cancelled")
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
    finally:
        logger.info("Cleaning up before exit")
        cleanup_gpio()
        fb.close()

if __name__ == '__main__':
    asyncio.run(main())