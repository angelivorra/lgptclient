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

# Logging configuration
logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)

async def main():

    # Initialize MIDI client and port
    client = AsyncSequencerClient(MIDI_CLIENT_NAME)
    port = client.create_port(MIDI_PORT, WRITE_PORT)
    logger.info("MIDI client and port created")

    # Listen for MIDI events
    while True:
        event = await client.event_input()
        if isinstance(event, NoteOnEvent):
            logger.debug(f"Received NoteOnEvent: {event.note}")

if __name__ == '__main__':
    asyncio.run(main())
