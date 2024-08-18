import asyncio
import pickle
from alsa_midi import AsyncSequencerClient, WRITE_PORT, NoteOnEvent
import logging

MIDI_CLIENT_NAME = 'movida'
MIDI_PORT = "inout"

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')

# TCP Server settings
TCP_PORT = 8888  # Define the port to listen on
TCP_BACKLOG = 5  # Number of unaccepted connections that the system will allow before refusing new connections

clients = []  # Move clients to the global scope for easier management

async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    logger.info(f"Connected to {addr}")
    clients.append((reader, writer))

    # Keep the connection alive for this client
    try:
        while True:
            data = await reader.read(100)
            if not data:
                break
            logger.debug(f"Received data from {addr}: {data.decode()}")
    except Exception as e:
        logger.error(f"Connection error with {addr}: {e}")
    finally:
        logger.info(f"Closing connection to {addr}")
        clients.remove((reader, writer))
        writer.close()
        await writer.wait_closed()

async def tcp_server():
    server = await asyncio.start_server(handle_client, host='0.0.0.0', port=TCP_PORT, backlog=TCP_BACKLOG)
    addr = server.sockets[0].getsockname()
    logger.info(f"Serving on {addr}")

    async with server:
        await server.serve_forever()

async def send_event_to_client(writer, event):
    try:
        message = str(event).encode('utf-8')
        writer.write(message)
        await writer.drain()
    except Exception as e:
        logger.error(f"Failed to send event to client: {e}")
        return writer
    return None

async def broadcast_event(event):
    logger.info(str(event))
    tasks = [send_event_to_client(writer, event) for reader, writer in clients]
    results = await asyncio.gather(*tasks)
    # Remove clients that failed to receive the message
    for result in results:
        if result is not None:
            clients.remove(result)

async def main():
    asyncio.create_task(tcp_server())

    client = AsyncSequencerClient(MIDI_CLIENT_NAME)
    port = client.create_port(MIDI_PORT, WRITE_PORT) 
    
    logger.info("MIDI client and port created")

    while True:
        event = await client.event_input()
        if isinstance(event, NoteOnEvent):
            logger.debug(f"Received NoteOnEvent: {event.note}")
            await broadcast_event(event.note)

if __name__ == '__main__':
    asyncio.run(main())
