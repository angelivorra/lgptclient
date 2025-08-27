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
from dataclasses import dataclass, field
from typing import List, Optional

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)-7s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("cliented")

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

    def set_delay(self, delay_ms: int):
        self.delay_ms = delay_ms
        logger.info(f"Delay configurado a {delay_ms} ms")

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
        self._new_event.set()

    async def run(self):
        """Loop que espera y ejecuta eventos en orden"""
        while self._running:
            if not self._heap:
                # Esperar a que haya algo
                self._new_event.clear()
                await self._new_event.wait()
                continue
            ev = self._heap[0]
            wait_s = ev.due_mono - time.monotonic()
            if wait_s > 0.010:
                # dormir a grano grueso
                await asyncio.sleep(min(wait_s, 0.050))
                continue
            elif wait_s > 0:
                # refino (busy-sleep ligero)
                await asyncio.sleep(wait_s)
            # Ejecutar
            heapq.heappop(self._heap)
            self.execute(ev)

    def execute(self, ev: ScheduledEvent):
        now_wall_ms = int(time.time() * 1000)
        lateness = now_wall_ms - ev.scheduled_local_wall_ms
        # Log único a nivel INFO siempre que se ejecute un evento (facilita ver sincronización)
        # Formato: EXEC,<tipo>,server_ts,lat_ms,<datos>
        base_prefix = f"EXEC,{ev.kind},{ev.server_ts_ms},{lateness}ms"
        if ev.kind == 'NOTA':
            note, channel, velocity = ev.payload
            logger.info(f"{base_prefix},note={note},ch={channel},vel={velocity}")
        elif ev.kind == 'CC':
            value, channel, controller = ev.payload
            logger.info(f"{base_prefix},cc={controller},val={value},ch={channel}")
            try:
                get_display().handle_cc(controller, value)
            except Exception as e:
                logger.warning(f"Fallo handle_cc ctrl={controller} val={value}: {e}")
        elif ev.kind == 'START':
            logger.info(f"{base_prefix}")
        elif ev.kind == 'END':
            logger.info(f"{base_prefix}")
        else:
            logger.info(f"{base_prefix}")

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
    asyncio.create_task(sched.run())
    backoff = RECONNECT_BASE_DELAY
    while True:
        try:
            logger.info(f"Conectando a {SERVER_HOST}:{SERVER_PORT} ...")
            reader, writer = await asyncio.open_connection(SERVER_HOST, SERVER_PORT)
            logger.info("Conectado")
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
    try:
        await run_client()
    except asyncio.CancelledError:
        pass

if __name__ == '__main__':
    import contextlib
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Abortado por usuario")
