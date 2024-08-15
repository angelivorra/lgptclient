import asyncio
import pickle
from alsa_midi import AsyncSequencerClient, WRITE_PORT, NoteOnEvent
import logging
import bluetooth
import subprocess

MIDI_CLIENT_NAME = 'movida'
MIDI_PORT = "inout"

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)
# Add console logging

# Bluetooth settings
BT_PORT = 3  # Arbitrary non-privileged port
BT_BACKLOG = 1

def get_bluetooth_mac():
    try:
        result = subprocess.run(['hcitool', 'dev'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout.decode('utf-8')
        lines = output.split('\n')
        for line in lines:
            if '\t' in line:
                parts = line.split('\t')
                if len(parts) > 2:
                    return parts[2].strip()
    except Exception as e:
        logger.error(f"Failed to get Bluetooth MAC address: {e}")
    return None

async def bluetooth_server():
    server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
    server_sock.bind(("", BT_PORT))
    server_sock.listen(BT_BACKLOG)
    
    local_mac = get_bluetooth_mac()
    if local_mac:
        logger.info(f"Bluetooth server started and listening on {local_mac}")
    else:
        logger.warning("Failed to get the Bluetooth MAC address")

    clients = []

    def accept_clients():
        while True:
            client_sock, address = server_sock.accept()
            logger.info(f"Accepted connection from {address}")
            clients.append(client_sock)

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, accept_clients)

    return clients

async def send_event_to_client(client_sock, event):
    try:
        logger.info(str(event))
        client_sock.send(str(event).encode('utf-8'))
    except Exception as e:
        logger.error(f"Failed to send event to client: {e}")
        return client_sock
    return None

async def broadcast_event(clients, event):
    tasks = [send_event_to_client(client_sock, event) for client_sock in clients]
    results = await asyncio.gather(*tasks)

    # Remove clients that failed to receive the message
    for result in results:
        if result is not None:
            clients.remove(result)

async def main():
    clients = await bluetooth_server()

    client = AsyncSequencerClient(MIDI_CLIENT_NAME)
    port = client.create_port(MIDI_PORT, WRITE_PORT) 
    
    logger.info("MIDI client and port created")

    while True:
        event = await client.event_input()
        if isinstance(event, NoteOnEvent):
            logger.debug(f"Received NoteOnEvent: {event.note}")
            await broadcast_event(clients, event.note)

if __name__ == '__main__':
    asyncio.run(main())