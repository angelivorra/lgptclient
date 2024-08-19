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

# Logging configuration
logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)

clients = []  # Connected TCP clients

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
    for client in clients:
        try:
            client_writer = client[1]
            client_writer.write(pickle.dumps(event))
            await client_writer.drain()
        except Exception as e:
            logger.error(f"Error broadcasting event to client: {e}")


async def main():
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
