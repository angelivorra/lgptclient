import asyncio
import pickle
import csv
import os
import socket
import random
from alsa_midi import (
    AsyncSequencerClient,
    READ_PORT,
    WRITE_PORT,
    NoteOnEvent,
    StopEvent,
    StartEvent,
    ControlChangeEvent,
    ClockEvent,
    PortUnsubscribedEvent,
    PortSubscribedEvent
)
try:
    # Algunas versiones usan ProgramChangeEvent
    from alsa_midi import ProgramChangeEvent
except ImportError:
    ProgramChangeEvent = None

import logging
from datetime import datetime
import json

# Constants
MIDI_CLIENT_NAME = 'movida'
MIDI_PORT = "inout"
# Puerto fuente (cliente:puerto) que queremos escuchar; se puede sobreescribir con env MIDI_SRC e.g. "130:0"
DEFAULT_SRC = os.environ.get("MIDI_SRC", "130:0")
TCP_PORT = 8888  # Define the port to listen on
CSV_FILENAME = '/home/angel/midi_notes_log_server.csv'
UNIX_SOCKET_PATH = '/tmp/copilot.sock'

# Logging configuration
logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.DEBUG,  # subir a DEBUG para ver eventos crudos
    datefmt='%Y-%m-%d %H:%M:%S'
)

clients = []

def initialize_csv(filename):
    """Initialize CSV file with headers if it doesn't exist."""
    if os.path.exists(filename):
        os.unlink(filename)
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["timestamp_sent", "note", "channel", "velocity"])


async def handle_local_client(reader, writer):
    try:
        data = await reader.read(1024)
        if data:
            message = data.decode().strip()
            if message.startswith("generate-data"):
                parts = message.split(',')
                if len(parts) == 2 and parts[0] == "generate-data":
                    try:
                        count = int(parts[1])
                        initialize_csv(CSV_FILENAME)
                        await send_data(count=count, channels=[3, 4, 5], persecond=10)
                    except ValueError:
                        logger.error("Invalid count value for generate-data command")
    except Exception as e:
        logger.error(f"Error in local client handler: {e}")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except:
            pass

async def handle_client(reader, writer):
    # Get client address info
    addr = writer.get_extra_info('peername')
    client_ip, client_port = addr
    
    sock = writer.get_extra_info('socket')
    if sock:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    
    # Log connection
    logger.info(f"New client connected from {client_ip}:{client_port}")
    clients.append(writer)
    logger.info(f"Total connected clients: {len(clients)}")

    with open('/home/angel/lgptclient/bin/config.json') as f:
        config = json.load(f)
    
    config_message = f"CONFIG,{config['delay']},{config['debug']},{config['ruido']}\n"
    writer.write(config_message.encode())
    await writer.drain()
    
    try:
        while True:
            data = await reader.read(100)
            if not data:
                break
    except asyncio.CancelledError:
        pass
    finally:
        clients.remove(writer)
        logger.info(f"Client disconnected from {client_ip}:{client_port}")
        logger.info(f"Total connected clients: {len(clients)}")
        writer.close()
        await writer.wait_closed()

async def send_data(count, channels, persecond):
    """Send random NoteOnEvent data to clients."""
    interval = 1.0 / persecond  # Time between each note per channel
    for _ in range(count):
        timestamp = int(datetime.now().timestamp() * 1000)
        for channel in channels:
            note = random.randint(1, 150)
            velocity = random.randint(1, 150)
            message = f"{timestamp},{note},{channel},{velocity}\n"
            for client in clients:
                client.write(message.encode())
                await client.drain()
            await log_event_to_csv(note, timestamp, channel, velocity)
            timestamp = timestamp + 1
        await asyncio.sleep(interval)  # Delay for persecond rate
    logger.info(f"Send data completed")

async def log_event_to_csv(note, timestamp, channel, velocity):
    """Log the note and timestamp to a CSV file."""    
    with open(CSV_FILENAME, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([timestamp, note, channel, velocity])

IMAGE_CC_DIRECT = 20          # CC para imagen directa 0-127 (canal 0)
ANIM_CC_DIRECT = 21           # CC para animación directa 0-127 (canal 1)

_pending_image_high = 0       # buffer para imagen extendida

def _encode_image_id(high7: int, low7: int) -> int:
    return (high7 << 7) | low7

async def broadcast_event(event, timestamp, debug_mode):
    global _pending_image_high
    message = None
    if isinstance(event, NoteOnEvent):
        # NOTA,<ts>,<note>
        message = f"NOTA,{timestamp},{event.note}\n"
        if debug_mode:
            await log_event_to_csv(event.note, timestamp, event.channel, event.velocity)
    elif isinstance(event, ControlChangeEvent):
        ctrl = event.param  # número de controlador
        val = event.value   # 0-127
        ch = event.channel  # canal MIDI 0-15
        # Protocolo:
        # Canal 0 => imágenes
        #   CC20 valor -> imagen directa valor        
        # Canal 1 => animaciones
        #   CC21 valor -> animación directa valor
        if ch == 0:
            if ctrl == IMAGE_CC_DIRECT:
                image_id = val
                message = f"IMG,{timestamp},{IMAGE_CC_DIRECT},{image_id}\n"
        elif ch == 1:
            if ctrl == ANIM_CC_DIRECT:
                anim_id = val
                message = f"ANIM,{timestamp},1,{anim_id}\n"
        # Otros canales ignorados por ahora
    elif isinstance(event, StartEvent):
        message = f"START,{timestamp}\n"
    elif isinstance(event, StopEvent):
        message = f"END,{timestamp}\n"

    if message and debug_mode:
        logger.info(f"Broadcasting event: {message.strip()}")

    if message:
        dead = []
        for client in clients:
            try:
                client.write(message.encode())
                await client.drain()
            except Exception:
                dead.append(client)
        for d in dead:
            if d in clients:
                clients.remove(d)
    
async def main():
    # Initialize CSV logging
    config = load_config()
    debug_mode = config.get("debug", False)
    if debug_mode:
        initialize_csv(CSV_FILENAME)

    # Remove socket if it already exists
    if os.path.exists(UNIX_SOCKET_PATH):
        os.remove(UNIX_SOCKET_PATH)
    
    # Initialize MIDI client and port
    client = AsyncSequencerClient(MIDI_CLIENT_NAME)
    # Habilitar recepción y (opcional) emisión: READ_PORT | WRITE_PORT
    port = client.create_port(MIDI_PORT, READ_PORT | WRITE_PORT)
    logger.info("MIDI client and port created")    
    
    # Conectar automáticamente (suscripción) desde el emisor conocido hacia este puerto
    # AsyncSequencerClient no expone connect_ports; usamos port.connect_from
    try:
        src_client_str, src_port_str = DEFAULT_SRC.split(":", 1)
        SRC_CLIENT = int(src_client_str)
        SRC_PORT = int(src_port_str)
        port.connect_from((SRC_CLIENT, SRC_PORT))
        logger.info(f"Suscripción creada: {SRC_CLIENT}:{SRC_PORT} -> {MIDI_CLIENT_NAME}:{MIDI_PORT}")
    except Exception as e:
        logger.warning(f"No se pudo crear suscripción automática desde {DEFAULT_SRC}: {e}")

    # Start a UNIX domain socket server
    server_local = await asyncio.start_unix_server(handle_local_client, path=UNIX_SOCKET_PATH)
    os.chmod(UNIX_SOCKET_PATH, 0o777)
    if debug_mode:
        logger.info(f"Local UNIX socket server started on {UNIX_SOCKET_PATH}")

    # Start TCP server
    server = await asyncio.start_server(handle_client, '0.0.0.0', TCP_PORT)
    if debug_mode:
        logger.info(f"TCP server started on port {TCP_PORT}")

    async with server, server_local:
        # Listen for MIDI events
        while True:
            event = await client.event_input()
            # Log crudo para inspección (omitimos ClockEvent salvo que LOG_CLOCK=1)
            
            if debug_mode:
                if isinstance(event, ClockEvent):
                    if os.environ.get("LOG_CLOCK") == "1":
                        logger.debug(f"RAW event type={event.__class__.__name__} repr={event!r}")
                    continue
                else:                    
                    logger.debug(f"RAW event type={event.__class__.__name__} repr={event!r}")
                
            if isinstance(event,(StartEvent,StopEvent, PortSubscribedEvent, PortUnsubscribedEvent)):
                continue
                
            allowed_types = [NoteOnEvent, StartEvent, StopEvent, ControlChangeEvent]

            if isinstance(event, tuple(allowed_types)):
                timestamp = int(datetime.now().timestamp() * 1000)
                await broadcast_event(event, timestamp, debug_mode)
                continue

            # # Fallback: si tiene atributos tipo control/value (probable CC en nombre distinto)
            # if hasattr(event, 'control') and hasattr(event, 'value'):
            #     timestamp = int(datetime.now().timestamp() * 1000)
            #     await broadcast_event(event, timestamp, debug_mode)
            #     logger.debug("Evento tratado vía fallback control/value (probable ControlChange)")
            # else:
            #     # Último recurso: mostrar atributos disponibles para depurar tipos no tratados
            #     logger.debug(f"Evento ignorado. Atributos: {dir(event)}")

def load_config(config_path='/home/angel/lgptclient/bin/config.json'):
    """Load configuration from JSON file"""
    try:
        with open(config_path) as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {"delay": 900, "debug": False}  # default values

if __name__ == '__main__':    
    asyncio.run(main())
