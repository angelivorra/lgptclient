import asyncio
import pickle
import csv
import os
from alsa_midi import AsyncSequencerClient, WRITE_PORT, NoteOnEvent
import logging
from datetime import datetime

# Constants
MIDI_CLIENT_NAME = 'movida'
MIDI_PORT = "inout"
TCP_PORT = 8888  # Define the port to listen on
TCP_BACKLOG = 5  # Number of unaccepted connections
CSV_FILENAME = '/home/angel/midi_notes_log.csv'

# Logging configuration
logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)

clients = []  # Connected TCP clients

def initialize_csv(filename):
    """Initialize CSV file with headers if it doesn't exist."""
    if os.path.exists(filename):
        os.path.remove(filename)
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)        

async def handle_client(reader, writer):
    """Handle TCP client connections."""
    addr = writer.get_extra_info('peername')
    logger.info(f"Connected to {addr}")
    clients.append((reader, writer))

    try:
        while True:
            data = await reader.read(100)
            if not data:
                break
            
            # Client sends back a confirmation with the timestamp when it received the event
            received_timestamp = datetime.utcnow().timestamp()
            original_timestamp = float(data.decode('utf-8'))
            delay = received_timestamp - original_timestamp
            logger.info(f"Round-trip delay to {addr}: {delay:.6f} seconds")
            
    except Exception as e:
        logger.error(f"Connection error with {addr}: {e}")
    finally:
        logger.info(f"Closing connection to {addr}")
        clients.remove((reader, writer))
        writer.close()
        await writer.wait_closed()

async def tcp_server():
    """Start TCP server to accept incoming connections."""
    server = await asyncio.start_server(handle_client, host='0.0.0.0', port=TCP_PORT, backlog=TCP_BACKLOG)
    addr = server.sockets[0].getsockname()
    logger.info(f"Serving on {addr}")

    async with server:
        await server.serve_forever()

async def broadcast_event(event):
    """Broadcast a MIDI event to all connected TCP clients."""
    message = f"{event.note},{timestamp}"
    tasks = [writer.write(message.encode('utf-8')) for _, writer in clients]
    await asyncio.gather(*tasks)
    for writer in clients:
        await writer.drain()  # Ensure data is sent immediately

async def log_event_to_csv(note):
    """Log the note and timestamp to a CSV file."""
    timestamp_ms = int(datetime.now().timestamp() * 1000)
    with open(CSV_FILENAME, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([timestamp_ms, note])

async def main():
    # Initialize CSV logging
    initialize_csv(CSV_FILENAME)
    
    # Start TCP server
    asyncio.create_task(tcp_server())

    # Initialize MIDI client and port
    client = AsyncSequencerClient(MIDI_CLIENT_NAME)
    port = client.create_port(MIDI_PORT, WRITE_PORT)
    logger.info("MIDI client and port created")

    # Listen for MIDI events
    while True:
        event = await client.event_input()
        if isinstance(event, NoteOnEvent):
            logger.debug(f"Received NoteOnEvent: {event.note}")
            await broadcast_event(event)

if __name__ == '__main__':
    asyncio.run(main())
