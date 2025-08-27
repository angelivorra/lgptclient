"""Servidor bridge TCP <-> MIDI para LGPT con lógica MIDI simplificada.

Objetivos:
 - Crear un puerto ALSA (lectura) que reciba los eventos que LGPT emite.
 - Opcionalmente auto-conectar a la salida de LGPT por nombre o por client:port.
 - Reemitir a clientes TCP en un formato de texto (NOTA, CC, START, END, SYNC).
 - Mantener heartbeats de sincronización.

Modo de uso rápido:
 1. Arranca este servidor.
 2. En LGPT selecciona como destino MIDI el puerto mostrado en el log:
             <CLIENT_NAME>:<PORT_NAME>   (por defecto movida:in)
        Si activas autoconexión el servidor intentará engancharse solo.

Variables de entorno relevantes:
    - MIDI_CLIENT_NAME (default 'movida')      Nombre del cliente ALSA que crea el servidor.
    - MIDI_PORT_NAME (default 'in')            Nombre del puerto.
    - LGPT_MIDI_SOURCE                         Especifica client:port numérico (ej. 128:0) para autoconectar.
    - LGPT_MIDI_PATTERN                        Patrón (substring case-insensitive) para buscar un puerto de salida.
    - LGPT_MIDI_AUTOCONNECT=1                 Habilita autoconexión (cliente -> nuestro puerto) usando SOURCE o PATTERN.
    - CSV_LOG=1                                Activa volcado de notas a CSV.
    - HEARTBEAT_INTERVAL (segundos, default 5)
    - LOG_CLOCK=1                              Log de ClockEvent.

Respuesta a: "¿Qué puerto le pongo a LGPT?"
    Simplemente selecciona el puerto ALSA que crea este servidor: 'movida:in' (o el que definas
    con MIDI_CLIENT_NAME / MIDI_PORT_NAME). Si no puedes seleccionarlo directamente, exporta
    LGPT_MIDI_AUTOCONNECT=1 y define LGPT_MIDI_SOURCE=client:port (o LGPT_MIDI_PATTERN=patrón)
    para que el servidor se conecte automáticamente a la salida de LGPT.
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import os
import socket
import logging
from datetime import datetime
import json
import re
import subprocess

from alsa_midi import (
    AsyncSequencerClient,
    READ_PORT,
    WRITE_PORT,
    NoteOnEvent,
    StopEvent,
    StartEvent,
    ControlChangeEvent,
    ClockEvent,
    PortSubscribedEvent,
    PortUnsubscribedEvent,
)

MIDI_CLIENT_NAME = os.environ.get("MIDI_CLIENT_NAME", "movida")
MIDI_PORT_NAME   = os.environ.get("MIDI_PORT_NAME", "in")

# Autoconexión (opcional)
LGPT_MIDI_SOURCE      = os.environ.get("LGPT_MIDI_SOURCE", "").strip()      # formato "client:port" numérico
LGPT_MIDI_PATTERN     = os.environ.get("LGPT_MIDI_PATTERN", "").strip()     # substring nombre
LGPT_MIDI_AUTOCONNECT = os.environ.get("LGPT_MIDI_AUTOCONNECT", "1") == "1"

TCP_PORT = 8888
CSV_FILENAME = '/home/angel/midi_notes_log_server.csv'
UNIX_SOCKET_PATH = '/tmp/copilot.sock'
HEARTBEAT_INTERVAL = float(os.environ.get("HEARTBEAT_INTERVAL", "5.0"))
CSV_LOG = os.environ.get("CSV_LOG", "0") == "1"

# Logging configuration
logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)

clients: list[asyncio.StreamWriter] = []

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

async def send_data(count, channels, persecond):  # Conservamos para pruebas locales
    import random
    interval = 1.0 / persecond
    for _ in range(count):
        base_ts = int(datetime.now().timestamp() * 1000)
        for ch in channels:
            note = random.randint(30, 90)
            vel = random.randint(10, 120)
            msg = f"NOTA,{base_ts},{note},{ch},{vel}\n"
            for c in clients:
                c.write(msg.encode())
                await c.drain()
            if CSV_LOG:
                await log_event_to_csv(note, base_ts, ch, vel)
            base_ts += 1
        await asyncio.sleep(interval)

async def log_event_to_csv(note, timestamp, channel, velocity):
    """Log the note and timestamp to a CSV file."""    
    with open(CSV_FILENAME, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([timestamp, note, channel, velocity])


def list_midi_sources():
    """Devuelve lista de (client_id, port_id, client_name, port_name) de aconnect -l"""
    try:
        out = subprocess.check_output(["aconnect", "-l"], text=True, stderr=subprocess.DEVNULL)
    except Exception as e:
        logger.warning(f"No se pudo ejecutar aconnect -l: {e}")
        return []
    res = []
    cur_client_id = None
    cur_client_name = None
    re_client = re.compile(r"^client\s+(\d+):\s+'([^']+)'")
    re_port   = re.compile(r"^\s+(\d+)\s+'([^']+)'")
    for line in out.splitlines():
        m_c = re_client.match(line)
        if m_c:
            cur_client_id = int(m_c.group(1))
            cur_client_name = m_c.group(2)
            continue
        m_p = re_port.match(line)
        if m_p and cur_client_id is not None:
            port_id = int(m_p.group(1))
            port_name = m_p.group(2)
            res.append((cur_client_id, port_id, cur_client_name, port_name))
    return res

def find_source(pattern: str) -> tuple[int,int] | None:
    if not pattern:
        return None
    pattern = pattern.lower()
    for cid, pid, cname, pname in list_midi_sources():
        if pattern in cname.lower() or pattern in pname.lower():
            return cid, pid
    return None

def auto_connect_source(port):
    """Intenta autoconectar si se ha solicitado."""
    if not LGPT_MIDI_AUTOCONNECT:
        logger.info("Autoconnect desactivado (LGPT_MIDI_AUTOCONNECT!=1)")
        return
    # Prioridad: LGPT_MIDI_SOURCE numérico, luego patrón
    if LGPT_MIDI_SOURCE:
        if ':' in LGPT_MIDI_SOURCE:
            a, b = LGPT_MIDI_SOURCE.split(':',1)
            if a.isdigit() and b.isdigit():
                try:
                    port.connect_from((int(a), int(b)))
                    logger.info(f"Autoconectado por SOURCE {a}:{b} -> {MIDI_CLIENT_NAME}:{MIDI_PORT_NAME}")
                    return
                except Exception as e:
                    logger.warning(f"Fallo autoconexión SOURCE {LGPT_MIDI_SOURCE}: {e}")
            else:
                logger.warning("LGPT_MIDI_SOURCE no es numerico client:port, ignorando")
    if LGPT_MIDI_PATTERN:
        t = find_source(LGPT_MIDI_PATTERN)
        if t:
            try:
                port.connect_from(t)
                logger.info(f"Autoconectado por PATTERN '{LGPT_MIDI_PATTERN}' -> {t[0]}:{t[1]}")
                return
            except Exception as e:
                logger.warning(f"Fallo autoconexión pattern {t}: {e}")
        else:
            logger.warning(f"Sin coincidencias para patrón '{LGPT_MIDI_PATTERN}'")
    # Fallback automático a 'Midi Through' si nada configurado
    fallback = find_source('Midi Through')
    if fallback:
        try:
            port.connect_from(fallback)
            logger.info(f"Autoconectado por FALLBACK 'Midi Through' -> {fallback[0]}:{fallback[1]}")
            logger.info("Configura LGPT para enviar a 'Midi Through' si no ve el puerto movida.")
            return
        except Exception as e:
            logger.warning(f"Fallo autoconexión fallback Midi Through: {e}")
    logger.info("No se realizó autoconexión (sin source, pattern ni fallback válido)")

async def broadcast_event(event):
    ts = int(datetime.now().timestamp() * 1000)
    msg = None
    if isinstance(event, NoteOnEvent):
        msg = f"NOTA,{ts},{event.note},{event.channel},{event.velocity}\n"
        if CSV_LOG:
            await log_event_to_csv(event.note, ts, event.channel, event.velocity)
    elif isinstance(event, ControlChangeEvent):        
        if event.param != 7:
            msg = f"CC,{ts},{event.value},{event.channel},{event.param}\n"  # valor, canal, controlador
    elif isinstance(event, StartEvent):
        msg = f"START,{ts}\n"
    elif isinstance(event, StopEvent):
        msg = f"END,{ts}\n"
    if not msg:
        return
    logger.info(f"TX {msg.strip()}")
    dead = []
    for c in clients:
        try:
            c.write(msg.encode())
            await c.drain()
        except Exception:
            dead.append(c)
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
    if CSV_LOG:
        initialize_csv(CSV_FILENAME)

    # Limpia socket UNIX si existe
    if os.path.exists(UNIX_SOCKET_PATH):
        os.remove(UNIX_SOCKET_PATH)

    # Crea cliente y puerto MIDI (usamos READ_PORT|WRITE_PORT para que otros lo vean y conecten sin restricciones)
    client = AsyncSequencerClient(MIDI_CLIENT_NAME)
    port = client.create_port(MIDI_PORT_NAME, READ_PORT | WRITE_PORT)
    try:
        client_id = client.client_id  # atributo expuesto por alsa_midi
    except Exception:
        client_id = '?'
    logger.info(f"Puerto MIDI creado: {MIDI_CLIENT_NAME}:{MIDI_PORT_NAME} (client id {client_id})")
    logger.info("Si LGPT no lo muestra todavía, refresca la lista de dispositivos o vuelve al menú de configuración MIDI.")

    # Lista fuentes disponibles (solo log para facilitar selección manual)
    fuentes = list_midi_sources()
    if fuentes:
        logger.info("Fuentes MIDI disponibles (client:port nombre_client -> nombre_port):")
        for cid, pid, cname, pname in fuentes:
            logger.info(f"  {cid}:{pid} {cname} -> {pname}")
    else:
        logger.warning("No se listaron fuentes (¿aconnect instalado?)")

    # Autoconexión opcional
    auto_connect_source(port)
    logger.info("Si no hay autoconexión, selecciona en LGPT el destino: '%s:%s'" % (MIDI_CLIENT_NAME, MIDI_PORT_NAME))

    # Servidor UNIX local (para comandos de prueba)
    server_local = await asyncio.start_unix_server(handle_local_client, path=UNIX_SOCKET_PATH)
    os.chmod(UNIX_SOCKET_PATH, 0o777)
    logger.info(f"Socket UNIX listo en {UNIX_SOCKET_PATH}")

    # Servidor TCP para clientes externos
    server = await asyncio.start_server(handle_client, '0.0.0.0', TCP_PORT)
    logger.info(f"Servidor TCP en puerto {TCP_PORT}")

    async with server, server_local:
        hb = asyncio.create_task(heartbeat_task(HEARTBEAT_INTERVAL))
        try:
            while True:
                event = await client.event_input()
                # Eventos de reloj
                if isinstance(event, ClockEvent):
                    if os.environ.get("LOG_CLOCK") == "1":
                        logger.debug(f"ClockEvent")
                    continue
                # Solo log útil
                logger.debug(f"RX {event.__class__.__name__}: {event!r}")

                if isinstance(event, (NoteOnEvent, ControlChangeEvent, StartEvent, StopEvent)):
                    await broadcast_event(event)
        finally:
            hb.cancel()
            with contextlib.suppress(Exception):
                await hb

def load_config(config_path='/home/angel/lgptclient/bin/config.json'):
    # Se conserva por compatibilidad con clientes que esperan CONFIG
    try:
        with open(config_path) as f:
            return json.load(f)
    except Exception:
        return {"delay": 900, "debug": False, "ruido": 0, "pantalla": 1}

if __name__ == '__main__':    
    asyncio.run(main())