import asyncio
import contextlib
import pickle
import csv
import os
import socket
import random
import time
from collections import deque
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
import subprocess
import re

# Constants
MIDI_CLIENT_NAME = 'movida'
MIDI_PORT = "inout"
# Puerto fuente (cliente:puerto) que queremos escuchar; se puede sobreescribir con env MIDI_SRC e.g. "130:0"
MIDI_SRC_NAME = os.environ.get("MIDI_SRC_NAME", "").strip()
# Ahora permitimos que MIDI_SRC sea o bien "num:num", o "Nombre", o "Nombre:puerto"
DEFAULT_SRC   = os.environ.get("MIDI_SRC", "Midi Through")  # sin :0 para evitar parsing numérico
TCP_PORT = 8888  # Define the port to listen on
CSV_FILENAME = '/home/angel/midi_notes_log_server.csv'
UNIX_SOCKET_PATH = '/tmp/copilot.sock'
HEARTBEAT_INTERVAL = float(os.environ.get("HEARTBEAT_INTERVAL", "5.0"))  # segundos (puedes ajustar a 1.0 si quieres más precisión)

# Logging configuration
logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)

clients = []

# BPM tracking desde MIDI Clock (24 pulsos = 1 negra).
# Medimos la duración de cada negra COMPLETA (24 pulsos): el groove/swing de LGPT
# es periódico dentro de la negra, así que una negra entera dura siempre lo mismo
# y el groove se anula. La negra suelta aún tiene jitter (±2 BPM), así que:
#   1) suavizamos con un filtro EMA,
#   2) si el cambio supera JUMP_THRESHOLD adoptamos el valor al instante,
#   3) reportamos un entero con histéresis para que no oscile ±1.
PULSES_PER_BEAT = 24
EMA_ALPHA = 0.2           # 0..1; menor = más suave pero más lento
JUMP_THRESHOLD_BPM = 7.0  # salto mayor a esto → adopción inmediata
HYSTERESIS_BPM = 0.75     # margen para cambiar el entero reportado
_clock_times: deque = deque(maxlen=PULSES_PER_BEAT + 1)
_pulse_count: int = 0
_bpm_ema: float = 0.0     # estimación suavizada interna
_last_bpm: float = 0.0    # último entero difundido


def _process_clock_pulse() -> float | None:
    """Registra un pulso de MIDI Clock y devuelve el BPM a difundir, o None.

    Solo evalúa al completar una negra (24 pulsos). Aplica EMA + adopción rápida
    ante saltos e histéresis sobre el entero; devuelve el valor cuando cambia.
    """
    global _pulse_count, _bpm_ema, _last_bpm
    _clock_times.append(time.monotonic())
    _pulse_count += 1

    if _pulse_count % PULSES_PER_BEAT != 0:
        return None
    if len(_clock_times) <= PULSES_PER_BEAT:
        return None

    beat_dur = _clock_times[-1] - _clock_times[-1 - PULSES_PER_BEAT]
    if beat_dur <= 0:
        return None
    beat_bpm = 60.0 / beat_dur

    # 1) EMA, con adopción inmediata si el salto es grande (cambio de tempo)
    if _bpm_ema == 0.0 or abs(beat_bpm - _bpm_ema) > JUMP_THRESHOLD_BPM:
        _bpm_ema = beat_bpm
    else:
        _bpm_ema += EMA_ALPHA * (beat_bpm - _bpm_ema)

    # 2) Entero con histéresis: difundir solo cuando cambia el tempo redondeado
    if _last_bpm == 0.0 or abs(_bpm_ema - _last_bpm) >= HYSTERESIS_BPM:
        new_bpm = float(round(_bpm_ema))
        if new_bpm != _last_bpm:
            _last_bpm = new_bpm
            return new_bpm
    return None

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
    
    config_message = f"CONFIG,{config['delay']},{config['debug']},{config['ruido']},{config['pantalla']}\n"
    writer.write(config_message.encode())
    logger.info(f"{config_message.strip()}")
    # Enviar un SYNC inmediato para que el cliente pueda calibrar offset al inicio
    initial_sync_ts = int(datetime.now().timestamp() * 1000)
    writer.write(f"SYNC,{initial_sync_ts}\n".encode())
    await writer.drain()
    
    try:
        while True:
            data = await reader.read(100)
            if not data:
                break
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    finally:
        if writer in clients:
            clients.remove(writer)
        logger.info(f"Client disconnected from {client_ip}:{client_port}")
        logger.info(f"Total connected clients: {len(clients)}")
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

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


_pending_image_high = 0       # buffer para imagen extendida

def _encode_image_id(high7: int, low7: int) -> int:
    return (high7 << 7) | low7

async def broadcast_event(event, timestamp, csv_logging):
    global _pending_image_high
    message = None
    if isinstance(event, NoteOnEvent):
        # NOTA,<ts>,<note>
        message = f"NOTA,{timestamp},{event.note},{event.channel},{event.velocity}\n"
        if csv_logging:
            await log_event_to_csv(event.note, timestamp, event.channel, event.velocity)
    elif isinstance(event, ControlChangeEvent):
        ctrl = event.param  # número de controlador
        val = event.value   # 0-127
        ch = event.channel  # canal MIDI 0-15
        message = f"CC,{timestamp},{val},{ch},{ctrl}\n"
    elif isinstance(event, StartEvent):
        message = f"START,{timestamp}\n"
    elif isinstance(event, StopEvent):
        message = f"END,{timestamp}\n"

    if message:
        logger.info(f"Broadcast TX: {message.strip()}")

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
    
async def broadcast_bpm(timestamp: int, bpm: float):
    message = f"BPM,{timestamp},{bpm:.2f}\n"
    logger.info(f"Broadcast TX: {message.strip()}")
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

async def heartbeat_task(interval: float):
    """Envia periódicamente un latido de sincronización de reloj a todos los clientes."""
    while True:
        ts_ms = int(datetime.now().timestamp() * 1000)
        message = f"SYNC,{ts_ms}\n"
        dead = []
        for c in clients:
            try:
                c.write(message.encode())
            except Exception:
                dead.append(c)
        # Limpieza de clientes muertos
        for d in dead:
            if d in clients:
                clients.remove(d)
        # Drain (hacerlo una sola vez para eficiencia)
        for c in clients:
            try:
                await c.drain()
            except Exception:
                pass
        
        logger.info(f"Heartbeat SYNC enviado ({ts_ms}) a {len(clients)} clientes")
        await asyncio.sleep(interval)

async def main():
    # Initialize CSV logging
    config = load_config()
    csv_logging = config.get("debug", True)
    if csv_logging:
        initialize_csv(CSV_FILENAME)

    # Remove socket if it already exists
    if os.path.exists(UNIX_SOCKET_PATH):
        os.remove(UNIX_SOCKET_PATH)
    
    # Initialize MIDI client and port
    client = AsyncSequencerClient(MIDI_CLIENT_NAME)
    # Habilitar recepción y (opcional) emisión: READ_PORT | WRITE_PORT
    port = client.create_port(MIDI_PORT, READ_PORT | WRITE_PORT)
    logger.info("MIDI client and port created")    
    
    connected = connect_source_once(client, port)
    if not connected:
        logger.warning("Sin fuente MIDI enlazada (no habrá eventos)")

    # Start a UNIX domain socket server
    server_local = await asyncio.start_unix_server(handle_local_client, path=UNIX_SOCKET_PATH)
    os.chmod(UNIX_SOCKET_PATH, 0o777)
    logger.info(f"Local UNIX socket server started on {UNIX_SOCKET_PATH}")

    # Start TCP server
    server = await asyncio.start_server(handle_client, '0.0.0.0', TCP_PORT)
    logger.info(f"TCP server started on port {TCP_PORT}")

    async with server, server_local:
        # Lanzar tarea heartbeat
        hb = asyncio.create_task(heartbeat_task(HEARTBEAT_INTERVAL))
        try:
            while True:
                event = await client.event_input()
                # Log crudo para inspección (omitimos ClockEvent salvo que LOG_CLOCK=1)
                
                # Log de todos los eventos crudos (ClockEvent opcional)
                if isinstance(event, ClockEvent):
                    bpm = _process_clock_pulse()
                    if bpm is not None:
                        ts = int(datetime.now().timestamp() * 1000)
                        await broadcast_bpm(ts, bpm)
                    continue
                else:
                    logger.info(f"RAW event type={event.__class__.__name__} repr={event!r}")
                
                if isinstance(event,(StartEvent,StopEvent, PortSubscribedEvent, PortUnsubscribedEvent)):
                    continue
                    
                allowed_types = [NoteOnEvent, StartEvent, StopEvent, ControlChangeEvent]

                if isinstance(event, tuple(allowed_types)):
                    timestamp = int(datetime.now().timestamp() * 1000)
                    await broadcast_event(event, timestamp, csv_logging)
                    continue
        finally:
            hb.cancel()
            with contextlib.suppress(Exception):
                await hb

def load_config(config_path='/home/angel/lgptclient/bin/config.json'):
    """Load configuration from JSON file"""
    try:
        with open(config_path) as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {"delay": 900, "debug": False}  # default values

ACONNECT_CLIENT_RE = re.compile(r"^client\s+(\d+):\s+'([^']+)'")
ACONNECT_PORT_RE   = re.compile(r"^\s+(\d+)\s+'([^']+)'")

def find_midi_port_by_name(pattern: str, desired_port: str | None = None):
    """
    Busca primer puerto cuyo nombre de cliente o de puerto contenga `pattern`
    (case-insensitive). Si desired_port es numérico, filtra por ese port id.
    Devuelve (client_id, port_id) o None.
    """
    if not pattern:
        return None
    pat = pattern.lower()
    try:
        out = subprocess.check_output(["aconnect", "-l"], text=True, stderr=subprocess.DEVNULL)
    except Exception as e:
        logger.warning(f"No se pudo ejecutar aconnect -l: {e}")
        return None

    current_client_id = None
    current_client_name = None
    for line in out.splitlines():
        m_client = ACONNECT_CLIENT_RE.match(line)
        if m_client:
            current_client_id = int(m_client.group(1))
            current_client_name = m_client.group(2)
            continue
        m_port = ACONNECT_PORT_RE.match(line)
        if m_port and current_client_id is not None:
            port_id = int(m_port.group(1))
            port_name = m_port.group(2)
            # Coincidencia
            if (pat in current_client_name.lower()) or (pat in port_name.lower()):
                if desired_port is not None and desired_port.isdigit():
                    if str(port_id) != desired_port:
                        continue
                return (current_client_id, port_id)
    return None

def connect_source_once(client, port):
    """
    Orden:
      1) MIDI_SRC_NAME (solo nombre o nombre:port)
      2) DEFAULT_SRC (nombre o nombre:port o id:id)
    """
    # Helper interno
    def try_name_spec(spec: str):
        if ':' in spec:
            left, right = spec.split(':', 1)
            return find_midi_port_by_name(left, right)
        else:
            return find_midi_port_by_name(spec)

    # 1) MIDI_SRC_NAME explícito
    if MIDI_SRC_NAME:
        t = try_name_spec(MIDI_SRC_NAME)
        if t:
            try:
                port.connect_from(t)
                logger.info(f"Fuente enlazada por nombre (MIDI_SRC_NAME): {t[0]}:{t[1]}")
                return True
            except Exception as e:
                logger.warning(f"Fallo enlace nombre (MIDI_SRC_NAME) {t}: {e}")
        else:
            logger.warning(f"No se encontró puerto que coincida con '{MIDI_SRC_NAME}'")

    # 2) DEFAULT_SRC
    if DEFAULT_SRC:
        spec = DEFAULT_SRC.strip()
        if ':' in spec:
            left, right = spec.split(':', 1)
            if left.isdigit() and right.isdigit():
                # Interpretar como IDs numéricos directos
                try:
                    t = (int(left), int(right))
                    port.connect_from(t)
                    logger.info(f"Fuente enlazada por ID: {t[0]}:{t[1]}")
                    return True
                except Exception as e:
                    logger.warning(f"Fallo enlace ID {spec}: {e}")
            # Si no son ambos dígitos, tratar como nombre:puerto
            t = try_name_spec(spec)
            if t:
                try:
                    port.connect_from(t)
                    logger.info(f"Fuente enlazada por nombre DEFAULT_SRC '{spec}' → {t[0]}:{t[1]}")
                    return True
                except Exception as e:
                    logger.warning(f"Fallo enlace nombre DEFAULT_SRC {t}: {e}")
            else:
                logger.warning(f"No coincidencia para patrón '{spec}' (DEFAULT_SRC)")
        else:
            # Solo nombre
            t = try_name_spec(spec)
            if t:
                try:
                    port.connect_from(t)
                    logger.info(f"Fuente enlazada por nombre DEFAULT_SRC '{spec}' → {t[0]}:{t[1]}")
                    return True
                except Exception as e:
                    logger.warning(f"Fallo enlace nombre DEFAULT_SRC {t}: {e}")
            else:
                logger.warning(f"No coincidencia para patrón '{spec}' (DEFAULT_SRC)")
    return False

# Elimina las funciones antiguas resolve_source_by_name y la versión anterior de connect_source_once.

if __name__ == '__main__':    
    asyncio.run(main())