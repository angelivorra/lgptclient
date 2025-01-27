import asyncio
import pickle
import csv
import os
import socket
import random
from alsa_midi import AsyncSequencerClient, WRITE_PORT, NoteOnEvent
import logging
from datetime import datetime

# Constants
MIDI_CLIENT_NAME = 'movida'
MIDI_PORT = "inout"
TCP_PORT = 8888  # Define the port to listen on
CSV_FILENAME = '/home/angel/midi_notes_log.csv'
DEBUG_NOTES = False
TMP_FILE = '/tmp/debug_notes.tmp'
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
        while True:
            data = await reader.read(1024)
            if not data:
                break
            # Process incoming command here
            response = f"Received: {data.decode()}"
            writer.write(response.encode())
            await writer.drain()
    except asyncio.CancelledError:
        pass
    finally:
        writer.close()
        await writer.wait_closed()

async def handle_client(reader, writer):
    sock = writer.get_extra_info('socket')
    if sock:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    clients.append(writer)
    try:
        # if DEBUG_NOTES:
        #     await asyncio.sleep(5)  # Wait for 5 seconds after connection
        #     # Start sending test data after 5 seconds
        #     await send_data(count=2000, channels=[1, 2], persecond=20)
        #     await send_data(count=2000, channels=[3, 4], persecond=30)
        while True:
            data = await reader.read(100)
            if not data:
                break
    except asyncio.CancelledError:
        pass
    finally:
        clients.remove(writer)
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

async def log_event_to_csv(note, timestamp, channel, velocity):
    """Log the note and timestamp to a CSV file."""    
    with open(CSV_FILENAME, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([timestamp, note, channel, velocity])

async def broadcast_event(event, timestamp):
    message = f"{timestamp},{event.note},{event.channel},{event.velocity}\n"
    for client in clients:
        client.write(message.encode())
        await client.drain()
    if DEBUG_NOTES:
        await log_event_to_csv(event.note, timestamp, event.channel, event.velocity)
        

async def main():
    # Initialize CSV logging
    if DEBUG_NOTES:
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
                await broadcast_event(event, timestamp)

if __name__ == '__main__':
    if os.path.exists(TMP_FILE):
        DEBUG_NOTES = True
        os.remove(TMP_FILE)
        logger.info("Debug Mode Initiated")
    asyncio.run(main())
