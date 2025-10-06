#!/usr/bin/env python3
"""
Cliente sincronizado para recibir eventos del servidor MIDI.

Protocolo de líneas (ASCII, \n):
    CONFIG,<delay_ms>,<debug>,<ruido>,<pantalla>
  SYNC,<server_ts_ms>
  NOTA,<server_ts_ms>,<note>,<channel>,<velocity>
  CC,<server_ts_ms>,<value>,<channel>,<controller>
  START,<server_ts_ms>
  END,<server_ts_ms>

Objetivo: ejecutar cada evento en el instante local equivalente a
 (server_ts_ms - offset_ms) + delay_ms

Donde offset_ms = server_time_ms - local_time_ms (estimado mediante heartbeats SYNC).
Se aplica un suavizado exponencial para estabilidad.

Raspberry Pi 3 considerations:
- Uso de asyncio y heap para scheduling eficiente (~15 eventos/s, picos simultáneos).
- Sleep granular 10ms -> refina a 2ms para reducir carga CPU.
- Si un evento llega tarde se ejecuta inmediatamente y se registra la latencia.

Ajustes por entorno:
  SERVER_HOST (default 127.0.0.1)
  SERVER_PORT (default 8888)
  OFFSET_ALPHA (default 0.2)
  MAX_LATE_MS (default 200) -> advertencia si se supera
"""
import asyncio
import os
import time
import heapq
import logging
import json
from dataclasses import dataclass, field
from typing import List, Optional
import RPi.GPIO as GPIO

# Manejo flexible de imports (ejecución directa o como paquete)
try:
    from .display_executor import get_display
    from .media_cache import get_cache
except ImportError:  # ejecución directa
    import sys
    sys.path.append(os.path.dirname(__file__))
    from display_executor import get_display  # type: ignore
    from media_cache import get_cache  # type: ignore

SERVER_HOST = os.environ.get("SERVER_HOST", "192.168.0.2")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "8888"))
OFFSET_ALPHA = float(os.environ.get("OFFSET_ALPHA", "0.2"))
MAX_LATE_MS = int(os.environ.get("MAX_LATE_MS", "200"))
RECONNECT_BASE_DELAY = 1.5
RECONNECT_MAX_DELAY = 15
EVENT_LATE_WARN_MS = int(os.environ.get("EVENT_LATE_WARN_MS", "25"))

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s.%(msecs)03d %(levelname)-7s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("cliented")

# Cargar configuración para GPIO
try:
    with open('/home/angel/config.json') as f:
        config = json.load(f)
    instruments = config["instruments"]
    PINES = config["pines"]
    logger.info(f"Configuración GPIO cargada: {len(instruments)} instrumentos")
except Exception as e:
    logger.error(f"Error cargando config.json: {e}")
    instruments = {}
    PINES = {}

def init_gpio():
    """Inicializa los pines GPIO para los instrumentos"""
    try:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        for instrument_name, pin in instruments.items():
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)
            logger.info(f"GPIO pin {pin} configurado para {instrument_name}")
        logger.info("GPIO inicializado correctamente")
    except Exception as e:
        logger.error(f"Error inicializando GPIO: {e}")

def cleanup_gpio():
    """Limpia los pines GPIO"""
    try:
        logger.info('Cleaning up GPIO')
        GPIO.cleanup()
        logger.info('GPIO cleanup complete')
    except Exception as e:
        logger.error(f"Error en GPIO cleanup: {e}")

def sinchronize_time():
    try:
        logger.info("Attempting to synchronize time with NTP server 192.168.0.2")
        result = os.system('sudo ntpdate 192.168.0.2')
        if result == 0:
            logger.info("Time synchronization successful")
        else:
            logger.error(f"Time synchronization failed with exit code: {result}")
            logger.error("Please check if ntpdate is installed and NTP server is accessible")
    except Exception as e:
        logger.error(f"Error during time synchronization: {e}")
        logger.error("Time synchronization failed - continuing without sync")

@dataclass(order=True)
class ScheduledEvent:
    due_mono: float
    seq: int = field(compare=False)
    kind: str = field(compare=False)
    server_ts_ms: int = field(compare=False)
    payload: tuple = field(compare=False)
    scheduled_local_wall_ms: int = field(compare=False)

class TimeSync:
    def __init__(self, alpha: float):
        self.alpha = alpha
        self.offset_ms: Optional[float] = None  # server - local
        self.samples = 0

    def update(self, server_ts_ms: int):
        """Actualiza offset filtrado y devuelve (muestra_bruta, offset_filtrado, primera_vez)."""
        local_ts_ms = int(time.time() * 1000)
        sample = server_ts_ms - local_ts_ms
        first = self.offset_ms is None
        if first:
            self.offset_ms = sample
        else:
            self.offset_ms += self.alpha * (sample - self.offset_ms)
        self.samples += 1
        return sample, self.offset_ms, first

    def get_offset(self) -> float:
        return self.offset_ms if self.offset_ms is not None else 0.0

class EventScheduler:
    def __init__(self):
        self._heap: List[ScheduledEvent] = []
        self._seq = 0
        self._new_event = asyncio.Event()
        self._running = True
        self.delay_ms = 0
        self.debug = False
        self.ruido = False

    def set_delay(self, delay_ms: int):
        self.delay_ms = delay_ms
        logger.info(f"Delay configurado a {delay_ms} ms")
    
    def set_flags(self, debug: bool, ruido: bool):
        self.debug = debug
        self.ruido = ruido
        logger.info(f"Flags configurados: debug={debug}, ruido={ruido}")

    def schedule(self, kind: str, server_ts_ms: int, offset_ms: float, payload: tuple):
        # Calcula tiempo local wall donde debe ejecutarse
        local_wall_ms = server_ts_ms - offset_ms + self.delay_ms
        now_wall_ms = time.time() * 1000
        # Convertir a monotonic para evitar saltos de reloj
        now_mono = time.monotonic()
        delta_ms = local_wall_ms - now_wall_ms
        due_mono = now_mono + max(delta_ms / 1000.0, 0)  # si ya pasó, ejecutar pronto
        self._seq += 1
        ev = ScheduledEvent(due_mono=due_mono,
                             seq=self._seq,
                             kind=kind,
                             server_ts_ms=server_ts_ms,
                             payload=payload,
                             scheduled_local_wall_ms=int(local_wall_ms))
        heapq.heappush(self._heap, ev)
        logger.info(f"SCHEDULED {kind} seq={self._seq} delta_ms={delta_ms:.1f} wait_s={delta_ms/1000:.3f} heap_size={len(self._heap)}")
        self._new_event.set()

    async def run(self):
        """Loop que espera y ejecuta eventos en orden"""
        logger.info("EventScheduler.run() iniciado")
        while self._running:
            if not self._heap:
                # Esperar a que haya algo
                logger.debug("Heap vacío, esperando eventos...")
                self._new_event.clear()
                await self._new_event.wait()
                logger.debug("Nuevo evento detectado, continuando loop")
                continue
            ev = self._heap[0]
            wait_s = ev.due_mono - time.monotonic()
            if wait_s > 0.010:
                # dormir a grano grueso
                logger.debug(f"Esperando {wait_s:.3f}s para evento {ev.kind} seq={ev.seq}")
                await asyncio.sleep(min(wait_s, 0.050))
                continue
            elif wait_s > 0:
                # refino (busy-sleep ligero)
                await asyncio.sleep(wait_s)
            # Ejecutar
            heapq.heappop(self._heap)
            logger.info(f"EJECUTANDO evento {ev.kind} seq={ev.seq} heap_restante={len(self._heap)}")
            self.execute(ev)

    def execute(self, ev: ScheduledEvent):
        now_wall_ms = int(time.time() * 1000)
        lateness = now_wall_ms - ev.scheduled_local_wall_ms
        # Log único a nivel INFO siempre que se ejecute un evento (facilita ver sincronización)
        # Formato: EXEC,<tipo>,server_ts,lat_ms,<datos>
        base_prefix = f"EXEC,{ev.kind},{ev.server_ts_ms},{lateness}ms"
        if lateness > EVENT_LATE_WARN_MS:
            logger.warning(f"LATE_EVENT kind={ev.kind} server_ts={ev.server_ts_ms} lateness={lateness}ms thr={EVENT_LATE_WARN_MS}ms")
        if ev.kind == 'NOTA':
            note, channel, velocity = ev.payload
            logger.info(f"{base_prefix},note={note},ch={channel},vel={velocity}")
            
            # Activar GPIO para el instrumento correspondiente
            try:
                instrument_name = str(note)  # El nombre del instrumento es la nota
                if instrument_name in instruments:
                    pin = instruments[instrument_name]
                    logger.info(f"Activando GPIO pin {pin} para instrumento {instrument_name}")
                    
                    if self.ruido:
                        GPIO.output(pin, GPIO.HIGH)
                        # Obtener tiempo de activación del pin
                        tiempo_activacion = PINES.get(str(pin), {}).get('tiempo', 0.050)
                        time.sleep(tiempo_activacion)
                        GPIO.output(pin, GPIO.LOW)
                        logger.info(f"GPIO pin {pin} desactivado después de {tiempo_activacion}s")
                    else:
                        logger.info(f"Ruido desactivado, no se activa GPIO pin {pin}")
                else:
                    logger.warning(f"Instrumento {instrument_name} (nota {note}) no encontrado en config")
            except Exception as e:
                logger.error(f"Error activando GPIO para nota {note}: {e}")
            
        elif ev.kind == 'CC':
            value, channel, controller = ev.payload
            logger.info(f"{base_prefix},cc={controller},val={value},ch={channel}")
            try:
                get_display().handle_cc(controller, value)
                logger.info(f"handle_cc ejecutado exitosamente para ctrl={controller} val={value}")
            except Exception as e:
                logger.warning(f"Fallo handle_cc ctrl={controller} val={value}: {e}")
        elif ev.kind == 'START':
            logger.info(f"{base_prefix}")
        elif ev.kind == 'END':
            logger.info(f"{base_prefix}")
        else:
            logger.info(f"{base_prefix},payload={ev.payload}")

    def stop(self):
        self._running = False
        self._new_event.set()

async def reader_loop(reader: asyncio.StreamReader, tsync: TimeSync, sched: EventScheduler, debug: bool):
    cache = get_cache()
    while True:
        line = await reader.readline()
        if not line:
            raise ConnectionError("Servidor cerró conexión")
        try:
            text = line.decode().strip()
        except Exception:
            continue
        if not text:
            continue
        parts = text.split(',')
        tag = parts[0]
        logger.debug(f"RECIBIDO: {text}")
        if tag == 'CONFIG' and len(parts) >= 5:
            try:
                delay_ms = int(parts[1])
            except ValueError:
                delay_ms = 0
            def _parse_bool(v:str)->bool:
                return v.lower() in ('1','true','t','yes','y')
            debug_flag    = _parse_bool(parts[2])
            ruido_flag    = _parse_bool(parts[3])
            pantalla_flag = _parse_bool(parts[4])
            sched.set_delay(delay_ms)
            sched.set_flags(debug_flag, ruido_flag)
            # if debug_flag:
            #     logger.setLevel(logging.DEBUG)
            get_display().set_pantalla(pantalla_flag)
            logger.info(f"CONFIG recibido delay={delay_ms} debug={debug_flag} ruido={ruido_flag} pantalla={pantalla_flag}")
            if debug:
                logger.debug(f"Recibido CONFIG raw: {parts}")
        elif tag == 'SYNC' and len(parts) >= 2:
            try:
                server_ts_ms = int(parts[1])
            except ValueError:
                continue
            sample, filt, first = tsync.update(server_ts_ms)
            logger.debug(("PRIMERA " if first else "") + f"SYNC offset_sample={sample}ms offset_filtrado={filt:.2f}ms samples={tsync.samples}")
        elif tag == 'NOTA' and len(parts) >= 5:
            try:
                server_ts_ms = int(parts[1])
                note = int(parts[2])
                channel = int(parts[3])
                velocity = int(parts[4])
            except ValueError:
                continue
            sched.schedule('NOTA', server_ts_ms, tsync.get_offset(), (note, channel, velocity))
            logger.info(f"NOTA recibido note={note} ch={channel} vel={velocity}, ts={server_ts_ms}")
        elif tag == 'CC' and len(parts) >= 5:
            try:
                server_ts_ms = int(parts[1])
                value = int(parts[2])
                channel = int(parts[3])
                controller = int(parts[4])
            except ValueError:
                continue
            try:
                cache.ensure_loaded(controller, value)
            except Exception as e:
                logger.debug(f"Preload fallo ctrl={controller} val={value}: {e}")
            sched.schedule('CC', server_ts_ms, tsync.get_offset(), (value, channel, controller))
            logger.info(f"CC recibido value={value} ch={channel} ctrl={controller} (preload no implementado)")
        elif tag == 'START' and len(parts) >= 2:
            try:
                server_ts_ms = int(parts[1])
            except ValueError:
                continue
            sched.schedule('START', server_ts_ms, tsync.get_offset(), tuple())
        elif tag == 'END' and len(parts) >= 2:
            try:
                server_ts_ms = int(parts[1])
            except ValueError:
                continue
            sched.schedule('END', server_ts_ms, tsync.get_offset(), tuple())
        else:
            logger.debug(f"Ignorado: {text}")

async def run_client():
    tsync = TimeSync(OFFSET_ALPHA)
    sched = EventScheduler()
    debug_env = os.environ.get('CLIENT_DEBUG', '0')
    debug = debug_env in ('1', 'true', 'yes', 'y')
    logger.info("Creando task para EventScheduler...")
    scheduler_task = asyncio.create_task(sched.run())
    logger.info(f"Scheduler task creado: {scheduler_task}")
    backoff = RECONNECT_BASE_DELAY
    while True:
        try:
            logger.info(f"Conectando a {SERVER_HOST}:{SERVER_PORT} ...")
            reader, writer = await asyncio.open_connection(SERVER_HOST, SERVER_PORT)
            logger.info("Conectado")
            sinchronize_time()
            backoff = RECONNECT_BASE_DELAY
            try:
                await reader_loop(reader, tsync, sched, debug)
            except ConnectionError as e:
                logger.warning(f"Loop lector terminó: {e}")
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Conexión perdida: {e}. Reintentando en {backoff:.1f}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 1.7, RECONNECT_MAX_DELAY)

async def main():
    # Inicializar GPIO al arrancar
    init_gpio()
    try:
        await run_client()
    except asyncio.CancelledError:
        pass
    finally:
        cleanup_gpio()

if __name__ == '__main__':
    import contextlib
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Abortado por usuario")
        cleanup_gpio()
