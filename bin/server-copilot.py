import asyncio
import pickle
import csv
import os
import socket
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

# Logging configuration
logger = logging.getLogger(__name__)
logging.basicConfig(
    #format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
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
        writer.writerow(["timestamp_sent", "note"])

async def handle_client(reader, writer):
    sock = writer.get_extra_info('socket')
    if sock:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    clients.append(writer)
    try:
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

async def log_event_to_csv(note, timestamp):
    """Log the note and timestamp to a CSV file."""    
    with open(CSV_FILENAME, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([timestamp, note])

async def broadcast_event(event, timestamp):
    message = f"{timestamp},{event.note},{event.channel},{event.\n"
    if DEBUG_NOTES:                    
        logger.info(f"Received NoteOnEvent: {event.note} at {timestamp} ms")
        await log_event_to_csv(event.note, timestamp)

    for client in clients:
        client.write(message.encode())
        await client.drain()

async def main():
    # Initialize CSV logging
    if DEBUG_NOTES:
        initialize_csv(CSV_FILENAME)    
    
    # Initialize MIDI client and port
    client = AsyncSequencerClient(MIDI_CLIENT_NAME)
    port = client.create_port(MIDI_PORT, WRITE_PORT)
    logger.info("MIDI client and port created")

    # Start TCP server
    server = await asyncio.start_server(handle_client, '0.0.0.0', TCP_PORT)
    logger.info(f"TCP server started on port {TCP_PORT}")

    async with server:
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