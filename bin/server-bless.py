import asyncio
import pickle
import logging
from alsa_midi import AsyncSequencerClient, WRITE_PORT, NoteOnEvent
from bless import (
    BlessServer,
    GATTCharacteristicProperties,
    GATTAttributePermissions
)

MIDI_CLIENT_NAME = 'movida'
MIDI_PORT = "inout"

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# Define BLE service and characteristic UUIDs
SERVICE_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID = "00002a29-0000-1000-8000-00805f9b34fb"

class CustomBLEServer(BlessServer):
    def __init__(self):
        super().__init__("Movida")
        self.connected_clients = []

    async def start(self):
        await self.add_new_service(SERVICE_UUID)
               
        char_flags = (
            GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify
        )
        permissions = GATTAttributePermissions.readable | GATTAttributePermissions.writeable
        
        await self.add_new_characteristic(
            SERVICE_UUID,
            CHARACTERISTIC_UUID,
            char_flags,
            None,
            permissions
        )
                    
        # Set up client connection and disconnection callbacks
        self.on_connect = self.handle_connect
        self.on_disconnect = self.handle_disconnect
        
        logger.info("BLE server started")

    async def handle_connect(self, client_address):
        logger.info(f"Client {client_address} connected.")
        self.connected_clients.append(client_address)

    async def handle_disconnect(self, client_address):
        logger.info(f"Client {client_address} disconnected.")
        if client_address in self.connected_clients:
            self.connected_clients.remove(client_address)

    async def notify_clients(self, data):
        try:
            # Notify all connected clients
            await self.characteristic.notify(data)
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

async def main():
    server = CustomBLEServer()
    await server.start()

    client = AsyncSequencerClient(MIDI_CLIENT_NAME)
    port = client.create_port(MIDI_PORT, WRITE_PORT)

    logger.info("MIDI client and port created")

    while True:
        event = await client.event_input()
        if isinstance(event, NoteOnEvent):
            logger.debug(f"Received NoteOnEvent: {event.note}")
            data = pickle.dumps(event.note)
            await server.notify_clients(data)

if __name__ == '__main__':
    asyncio.run(main())
