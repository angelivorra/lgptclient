import asyncio
import csv
import traceback
from datetime import datetime
import os
import json
import signal
import logging
import socket
import time
from gpio_events import init_gpio, activate_instrumento, cleanup_gpio
import concurrent.futures

logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.WARNING,
    datefmt='%Y-%m-%d %H:%M:%S'
)

CSV_FILENAME = '/home/angel/midi_notes_log.csv'
TIMING_CSV = '/home/angel/timing_analysis.csv'
MECHANICAL_DELAY = 0

with open('/home/angel/config.json') as f:
    config = json.load(f)

instruments = config["instruments"]
PINES = config["pines"]


def sinchronize_time():
    os.system('sudo ntpdate 192.168.0.2')

def initialize_timing_csv():
    if os.path.exists(TIMING_CSV) == False:
        with open(TIMING_CSV, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['expected_timestamp', 'executed_timestamp'])

def initialize_csv(filename):
    if os.path.exists(filename) == False:
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

async def handle_event(reader):
    config_line = (await reader.readline()).decode().strip()
    success, delay, debug_mode, ruido = parse_config(config_line)
    if not success:
        logger.error("Failed to parse initial configuration")
        return
    if debug_mode:
        initialize_csv(CSV_FILENAME)
        initialize_timing_csv()
    sinchronize_time()
    #await send_message_to_socket("IMG,0,1,1", 0)
    while True:
        try:
            data = await reader.readline()
            if not data:
                logger.info("Connection closed by the server")
                #await send_message_to_socket("IMG,0,1,0", 0)
                break

            data = data.strip().decode('utf-8')
            logger.info(f"Received line: {data}")
            if data.startswith("NOTA,"):
                cleaned_data = data.split(',')
                _, timestamp, note = cleaned_data
                sent_timestamp, note  = map(int, [timestamp, note])                
                if debug_mode:
                    logger.info(f"Received event: {note}")
                current_timestamp = int(datetime.now().timestamp() * 1000)
                expected_timestamp = sent_timestamp + delay  # delay is the network/processing delay            
                
                if debug_mode:
                    with open(CSV_FILENAME, mode='a', newline='') as file:
                        writer = csv.writer(file)
                        writer.writerow([sent_timestamp, note, current_timestamp])
                
                strnote = str(note)
                if strnote in instruments:
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
            elif data.startswith("START"):
                if debug_mode:
                    logger.info("Received START message")
            elif data.startswith("END"):                
                if debug_mode:
                    logger.info("Received END message")                    
            elif data.startswith("IMG,"):
                logger.info(f"Received IMG message: {data}")
                # Handle IMG message
                parts = data.split(',')
                if len(parts) == 4:
                    _, timestamp, channel, img_id = parts
                    img_id = int(img_id)
                    timestamp = int(timestamp)
                    channel = int(channel)
                    current_timestamp = int(datetime.now().timestamp() * 1000)
                    expected_timestamp = timestamp + delay
                    asyncio.create_task(
                        send_message_to_socket(f"IMG,{expected_timestamp},{channel},{img_id}", delay)
                    ) 
                    logger.info(f"Received IMG message with ID: {img_id}")
            
        except Exception as e:
            logger.error(f"Error handling event: {e}")
            logger.error("Full traceback:\n" + traceback.format_exc())
            #await display_manager.set_state("off")  # Mostrar "off" en caso de error
            #await send_message_to_socket("IMG,0,0,1")
            break

async def tcp_client(addr, port):
    while True:
        try:
            #await display_manager.set_state("connecting")  # Mostrar "off" cuando la conexión falla            
            logger.info(f"Attempting to connect to {addr}:{port}")
            reader, writer = await asyncio.open_connection(addr, port)
            logger.info("ConnectedXX to server")
            #await send_message_to_socket("IMG,0,1,1")
            await handle_event(reader)            
        except (ConnectionError, OSError) as e:
            logger.info(f"Connection failed: {e}. Retrying in 5 seconds...")
            #await display_manager.set_state("connecting")  # Mostrar "off" cuando la conexión falla
            #await send_message_to_socket("IMG,0,0,1")
            await asyncio.sleep(5)
        except Exception as e:
            logger.info(f"An unexpected error occurred: {e}. Retrying in 5 seconds...")
            #await send_message_to_socket("IMG,0,0,1")
            await asyncio.sleep(5)

async def shutdown(loop, signal=None):
    if signal:
        logger.info(f"Received exit signal {signal.name}...")
    #await send_message_to_socket("IMG,0,1,2")
    #if display_manager:
    #    await display_manager.set_state("off")  # Mostrar "off" durante el apagado
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
    #for sig in (signal.SIGINT, signal.SIGTERM):
    #    loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(loop, sig, display_manager)))
    pass

async def send_to_unix_socket(message):
    server_address = '/tmp/display.sock'
    
    try:
        # Connect to the UNIX socket
        reader, writer = await asyncio.open_unix_connection(server_address)
        logger.info(f"Connected to {server_address}")

        # Send the message
        writer.write(message.encode('utf-8'))
        await writer.drain()  # Ensure the data is sent
        logger.info(f"Message sent: {message}")

        # Optionally, wait for a response from the server
        response = await reader.read(100)  # Adjust buffer size as needed
        logger.info(f"Server response: {response.decode()}")

        # Close the connection
        writer.close()
        await writer.wait_closed()
        logger.info("Connection closed")

        return {"status": "ok", "response": response.decode()}
    except Exception as e:
        return {"error": str(e)}

async def send_message_to_socket(message, delay = 0): 
    logger.info(f"Sending message to socket: {message}")
    if delay > 0:
            await asyncio.sleep(delay / 1000)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)            
    server_address = '/tmp/display.sock'
    try:
        sock.connect(server_address)
        sock.sendall(message.encode('utf-8'))
        # Wait briefly to ensure message is sent
        await asyncio.sleep(0.1)
    except Exception as e:
        logger.error(f"Error sending message to socket: {e}")
    finally:
        sock.close()


async def main():
    server_addr = '192.168.0.2'
    server_port = 8888
    
    loop = asyncio.get_running_loop()
    loop.set_default_executor(
        concurrent.futures.ThreadPoolExecutor(max_workers=4)
    )

    logger.info("Starting client application...")
    init_gpio()

    # Initialize Framebuffer and DisplayManager
    loop = asyncio.get_event_loop()
    
    try:
        await tcp_client(server_addr, server_port)
    except asyncio.CancelledError:
        logger.info("Main task cancelled")
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
    finally:
        logger.info("Cleaning up before exit")
        cleanup_gpio()

if __name__ == '__main__':
    asyncio.run(main())