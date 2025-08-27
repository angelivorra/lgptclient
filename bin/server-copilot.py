import asyncio
import pickle
import csv
import os
import socket
import random
import time
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
    global LEAD_NS
    addr = writer.get_extra_info('peername')
    client_ip, client_port = addr
    sock = writer.get_extra_info('socket')
    if sock:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    logger.info(f"New client connected from {client_ip}:{client_port}")
    clients.append(writer)
    logger.info(f"Total connected clients: {len(clients)}")
    # Cargar config y enviar base temporal
    try:
        with open('/home/angel/lgptclient/bin/config.json') as f:
            config = json.load(f)
        writer.write(f"CONFIG,{config['delay']},{config['debug']},{config['ruido']}\n".encode())
    except Exception as e_cfg:
        logger.warning(f"No se pudo cargar/enviar config inicial: {e_cfg}")
    try:
        writer.write(f"TIME_BASE,{time.monotonic_ns()}\n".encode())
        writer.write(f"LEAD,{LEAD_NS}\n".encode())
        await writer.drain()
    except Exception as e_init:
        logger.warning(f"Fallo envío TIME_BASE/LEAD: {e_init}")
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            msg = line.decode(errors='ignore').strip()
            if not msg:
                continue
            if msg.startswith('SYNC1'):
                parts = msg.split(',')
                if len(parts) == 2:
                    try:
                        c_send = int(parts[1])
                        s_now = time.monotonic_ns()
                        writer.write(f"SYNC2,{c_send},{s_now}\n".encode())
                        await writer.drain()
                    except ValueError:
                        logger.debug(f"SYNC1 mal formado: {msg}")
            elif msg.startswith('SET_LEAD'):
                parts = msg.split(',')
                if len(parts) == 2:
                    try:
                        new_ms = int(parts[1])
                        if 5 <= new_ms <= 2000:
                            LEAD_NS = new_ms * 1_000_000
                            writer.write(f"LEAD,{LEAD_NS}\n".encode())
                            await writer.drain()
                            logger.info(f"LEAD ajustado a {new_ms}ms via {client_ip}")
                    except ValueError:
                        pass
            # otros comandos ignorados
    except asyncio.CancelledError:
        pass
    finally:
        if writer in clients:
            clients.remove(writer)
        logger.info(f"Client disconnected from {client_ip}:{client_port}")
        logger.info(f"Total connected clients: {len(clients)}")
        try:
            writer.close()
            await writer.wait_closed()
        except:
            pass

async def send_data(count, channels, persecond):
    """Send random NoteOnEvent data to clients."""
    interval = 1.0 / persecond  # Time between each note per channel
    start_ns = time.monotonic_ns()
    for i in range(count):
        # timestamp relativo basado en monotonic (ms)
        base_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        timestamp = base_ms
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

SEQ = 0
LEAD_NS = 120_000_000  # 120 ms

# Protocolo sincronizado con tiempo de reproducción futuro (monotonic_ns)
# Eventos:
#   NOTA,<seq>,<play_ns>,<note>,<channel>,<velocity>
#   CC,<seq>,<play_ns>,<channel>,<controller>,<value>
# Control inicial a cada cliente: TIME_BASE,<server_monotonic_ns> y LEAD,<lead_ns>
# Sync ida/vuelta: SYNC1,<client_send_ns> -> SYNC2,<client_send_ns>,<server_time_ns>

async def broadcast_event(event, debug_mode):
    global SEQ
    play_ns = time.monotonic_ns() + LEAD_NS
    SEQ += 1
    message = None
    if isinstance(event, NoteOnEvent):
        message = f"NOTA,{SEQ},{play_ns},{event.note},{event.channel},{event.velocity}\n"
        if debug_mode:
            await log_event_to_csv(event.note, play_ns, event.channel, event.velocity)
    elif isinstance(event, ControlChangeEvent):
        message = f"CC,{SEQ},{play_ns},{event.channel},{event.param},{event.value}\n"
    if message and debug_mode:
        logger.debug(f"TX {message.strip()}")
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
                
            if isinstance(event,(PortSubscribedEvent, PortUnsubscribedEvent, StartEvent, StopEvent)):
                # ignorar estos eventos para protocolo reducido
                continue
            allowed_types = [NoteOnEvent, ControlChangeEvent]
            if isinstance(event, tuple(allowed_types)):
                await broadcast_event(event, debug_mode)
                continue

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
