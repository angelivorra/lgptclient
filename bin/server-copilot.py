import asyncio
import pickle
import csv
import os
import socket
import random
from alsa_midi import AsyncSequencerClient, WRITE_PORT, NoteOnEvent
import logging
from datetime import datetime
import json

# Constants
MIDI_CLIENT_NAME = 'movida'
MIDI_PORT = "inout"
TCP_PORT = 8888  # Define the port to listen on
CSV_FILENAME = '/home/angel/midi_notes_log_server.csv'
UNIX_SOCKET_PATH = '/tmp/copilot.sock'

# Logging configuration
logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
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
            logger.info(f"Received local message: {message}")
            if message == "generate-data":
                # Handle generate-data command
                await send_data(count=500, channels=[3,4,5], persecond=10)
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
    
    config_message = f"CONFIG,{config['delay']},{config['debug']}\n"
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

async def broadcast_event(event, timestamp, debug_mode):
    message = f"{timestamp},{event.note},{event.channel},{event.velocity}\n"
    for client in clients:
        client.write(message.encode())
        await client.drain()
    if debug_mode:
        await log_event_to_csv(event.note, timestamp, event.channel, event.velocity)
        

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
    port = client.create_port(MIDI_PORT, WRITE_PORT)
    logger.info("MIDI client and port created")
    
    # Start a UNIX domain socket server
    server_local = await asyncio.start_unix_server(handle_local_client, path=UNIX_SOCKET_PATH)
    os.chmod(UNIX_SOCKET_PATH, 0o777)
    logger.info(f"Local UNIX socket server started on {UNIX_SOCKET_PATH}")

    # Start TCP server
    server = await asyncio.start_server(handle_client, '0.0.0.0', TCP_PORT)
    logger.info(f"TCP server started on port {TCP_PORT}")

    async with server, server_local:
        # Listen for MIDI events
        while True:
            event = await client.event_input()
            if isinstance(event, NoteOnEvent):
                timestamp = int(datetime.now().timestamp() * 1000)
                await broadcast_event(event, timestamp, debug_mode)

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
